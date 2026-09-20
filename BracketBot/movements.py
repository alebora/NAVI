"""Play greeter arm trajectories (wave, hug, …) for NAVI tool calls."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path

import numpy as np

MOVEMENTS_DIR = Path.home() / "bbapps/greeter/movements"
DOF = 8

_lock = threading.Lock()
_cache: dict[str, list] = {}
_playing = threading.Event()
_cancel = threading.Event()


def list_movements():
    _ensure_loaded()
    return sorted(_cache)


def _ensure_loaded():
    with _lock:
        if _cache:
            return
        if not MOVEMENTS_DIR.is_dir():
            return
        for path in MOVEMENTS_DIR.glob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                _cache[path.stem] = json.loads(path.read_text())
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

    _playing.set()
    _cancel.clear()
    stop = stop_event or threading.Event()
    handles = []
    w_tl = w_tr = None
    try:
        r_l = Reader("arm_left.state", keeptime=False)
        r_r = Reader("arm_right.state", keeptime=False)
        w_l = Writer("arm_left.ctrl", Type("arm_ctrl"), keeptime=False)
        w_r = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
        w_tl = Writer("arm_left.torque", Type("arm_torque"), keeptime=False)
        w_tr = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
        for obj in (r_l, r_r, w_l, w_r, w_tl, w_tr):
            obj.__enter__()
            handles.append(obj)

        w_l["pos"] = np.array(traj[0]["left"], dtype=np.float32)
        w_r["pos"] = np.array(traj[0]["right"], dtype=np.float32)
        time.sleep(0.1)
        w_tl["enable"] = np.ones(DOF, dtype=np.bool_)
        w_tr["enable"] = np.ones(DOF, dtype=np.bool_)
        time.sleep(0.1)

        t0 = time.time()
        for frame in traj:
            if stop.is_set() or _cancel.is_set():
                break
            time.sleep(max(0.0, t0 + float(frame["t"]) - time.time()))
            w_l["pos"] = np.array(frame["left"], dtype=np.float32)
            w_r["pos"] = np.array(frame["right"], dtype=np.float32)

        print(f"[arm] played '{key}' ({len(traj)} frames)", flush=True)
        return {"status": "played", "movement": key, "frames": len(traj)}
    except RuntimeError as exc:
        print(f"[arm] unavailable: {exc}", flush=True)
        return {"error": f"Arms busy or unavailable: {exc}"}
    except Exception as exc:
        print(f"[arm] failed: {type(exc).__name__}: {exc}", flush=True)
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        for torque in (w_tl, w_tr):
            if torque is not None:
                with contextlib.suppress(Exception):
                    torque["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in handles:
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)
        _playing.clear()


def cancel_movement():
    _cancel.set()
