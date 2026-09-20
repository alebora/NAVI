"""Play greeter arm trajectories (wave, hug, …) for NAVI tool calls.

One-arm gestures (wave, handshake, fist bump) only torque and command the arm
that actually moves in the recording. The idle arm is left alone so it cannot
collide with the waving arm or fight a stale recorded rest pose.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path

import numpy as np

MOVEMENTS_DIR = Path.home() / "bbapps/greeter/movements"
DOF = 8
# Joint travel (turns) below this → that arm is considered idle in the clip.
_IDLE_TRAVEL = 0.08
_BLEND_S = 0.45

_lock = threading.Lock()
_cache: dict[str, list] = {}
_cache_mtime: dict[str, float] = {}
_playing = threading.Event()
_cancel = threading.Event()


def list_movements():
    _ensure_loaded()
    return sorted(_cache)


def _ensure_loaded():
    with _lock:
        if not MOVEMENTS_DIR.is_dir():
            return
        for path in MOVEMENTS_DIR.glob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            stem = path.stem
            if stem in _cache and _cache_mtime.get(stem) == mtime:
                continue
            try:
                _cache[stem] = json.loads(path.read_text())
                _cache_mtime[stem] = mtime
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[arm] skip {path.name}: {exc}", flush=True)


def _resolve(name: str):
    _ensure_loaded()
    key = " ".join(str(name or "").strip().lower().split())
    if key in _cache:
        return key, _cache[key]
    for stem, data in _cache.items():
        if stem.lower() == key or stem.lower().replace("_", " ") == key:
            return stem, data
    return key, None


def _side_travel(traj, side: str) -> float:
    arr = np.asarray([frame[side] for frame in traj], dtype=np.float64)
    if len(arr) < 2:
        return 0.0
    return float(np.abs(np.diff(arr, axis=0)).sum())


def _active_sides(traj):
    """Which arms have real motion in this clip."""
    left = _side_travel(traj, "left") >= _IDLE_TRAVEL
    right = _side_travel(traj, "right") >= _IDLE_TRAVEL
    if not left and not right:
        # Degenerate recording — drive both so something still happens.
        return True, True
    return left, right


def _read_pos(reader):
    reader.ready()
    if not reader.readable or reader.data is None:
        return None
    return np.asarray(reader.data["pos"], dtype=np.float32).copy()


def _blend_to(writer, start, goal, duration, stop, cancel):
    """Ease from start → goal so we never snap into the first keyframe."""
    start = np.asarray(start, dtype=np.float32)
    goal = np.asarray(goal, dtype=np.float32)
    t0 = time.time()
    while True:
        if stop.is_set() or cancel.is_set():
            return False
        u = min(1.0, (time.time() - t0) / max(duration, 1e-3))
        s = u * u * (3.0 - 2.0 * u)  # smoothstep
        writer["pos"] = (1.0 - s) * start + s * goal
        if u >= 1.0:
            return True
        time.sleep(0.02)


def play_movement(name: str, stop_event: threading.Event | None = None):
    """Blocking playback; safe to run on a daemon thread."""
    from bbos import Reader, Writer, Type

    key, traj = _resolve(name)
    if not traj:
        return {
            "error": f"Unknown movement '{name}'",
            "available": list_movements(),
        }
    if _playing.is_set():
        return {"status": "busy", "detail": "Another arm movement is already playing"}

    use_left = use_right = False
    _playing.set()
    _cancel.clear()
    stop = stop_event or threading.Event()
    handles = []
    w_tl = w_tr = None
    try:
        use_left, use_right = _active_sides(traj)
        r_l = Reader("arm_left.state", keeptime=False)
        r_r = Reader("arm_right.state", keeptime=False)
        w_l = Writer("arm_left.ctrl", Type("arm_ctrl"), keeptime=False)
        w_r = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
        w_tl = Writer("arm_left.torque", Type("arm_torque"), keeptime=False)
        w_tr = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
        for obj in (r_l, r_r, w_l, w_r, w_tl, w_tr):
            obj.__enter__()
            handles.append(obj)

        cur_l = _read_pos(r_l)
        cur_r = _read_pos(r_r)
        goal_l = np.asarray(traj[0]["left"], dtype=np.float32)
        goal_r = np.asarray(traj[0]["right"], dtype=np.float32)

        # Command first targets, then enable torque only on arms that move.
        if use_left:
            w_l["pos"] = cur_l if cur_l is not None else goal_l
        if use_right:
            w_r["pos"] = cur_r if cur_r is not None else goal_r
        time.sleep(0.05)
        if use_left:
            w_tl["enable"] = np.ones(DOF, dtype=np.bool_)
        if use_right:
            w_tr["enable"] = np.ones(DOF, dtype=np.bool_)
        time.sleep(0.05)

        sides = []
        if use_left:
            sides.append("left")
        if use_right:
            sides.append("right")
        print(
            f"[arm] playing '{key}' ({len(traj)} frames, arms={'+'.join(sides) or 'none'})",
            flush=True,
        )

        if use_left and cur_l is not None:
            if not _blend_to(w_l, cur_l, goal_l, _BLEND_S, stop, _cancel):
                return {"status": "cancelled", "movement": key}
        if use_right and cur_r is not None:
            if not _blend_to(w_r, cur_r, goal_r, _BLEND_S, stop, _cancel):
                return {"status": "cancelled", "movement": key}

        t0 = time.time()
        for frame in traj:
            if stop.is_set() or _cancel.is_set():
                break
            time.sleep(max(0.0, t0 + float(frame["t"]) - time.time()))
            if use_left:
                w_l["pos"] = np.asarray(frame["left"], dtype=np.float32)
            if use_right:
                w_r["pos"] = np.asarray(frame["right"], dtype=np.float32)

        print(f"[arm] played '{key}' ({len(traj)} frames)", flush=True)
        return {
            "status": "played",
            "movement": key,
            "frames": len(traj),
            "arms": sides,
        }
    except RuntimeError as exc:
        print(f"[arm] unavailable: {exc}", flush=True)
        return {"error": f"Arms busy or unavailable: {exc}"}
    except Exception as exc:
        print(f"[arm] failed: {type(exc).__name__}: {exc}", flush=True)
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        if use_left and w_tl is not None:
            with contextlib.suppress(Exception):
                w_tl["enable"] = np.zeros(DOF, dtype=np.bool_)
        if use_right and w_tr is not None:
            with contextlib.suppress(Exception):
                w_tr["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in handles:
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)
        _playing.clear()


def cancel_movement():
    _cancel.set()
