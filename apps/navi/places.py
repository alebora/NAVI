# /// script
# requires-python = ">=3.10"
# dependencies = ["bbos", "numpy", "pyyaml"]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/bbos", editable = true }
# ///
"""NAVI places: save named spots from the live SLAM pose and drive to them.

  uv run places.py where                 # print current pose
  uv run places.py save judging          # save current pose as "judging"
  uv run places.py forget judging
  uv run places.py list
  uv run places.py go judging            # navigate there, wait for reached/failed

Uses the nav daemon's planner via nav.command. Stop the route in the nav web UI
first: only one app can own nav.command at a time.
"""
import difflib
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from bbos import Reader, Type, Writer

PLACES_FILE = Path(__file__).with_name("places.yaml")
GOAL_TIMEOUT_S = 180


def load_places():
    if not PLACES_FILE.exists():
        return {}
    return yaml.safe_load(PLACES_FILE.read_text()) or {}


def read_pose(timeout=3.0):
    """(x, y, yaw) from slam.pose, or raise if SLAM isn't publishing."""
    with Reader("slam.pose", keeptime=False) as poses:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if poses.ready():
                pose = poses.data
                return (float(pose["pos"][0]), float(pose["pos"][1]),
                        2.0 * math.atan2(float(pose["quat"][2]), float(pose["quat"][3])))
            time.sleep(0.02)
    raise RuntimeError("No slam.pose — is the slam daemon running and tracking?")


NAME_OK = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,30}$")


def normalize(name):
    """Spoken names arrive messy: 'The Judging Area!' -> 'judging area'."""
    name = re.sub(r"[^a-z0-9 _-]", "", str(name).strip().lower())
    name = re.sub(r"^(the|a|an) ", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not NAME_OK.match(name):
        raise ValueError(f"'{name}' is not a usable place name")
    return name


def resolve(name, places=None):
    """Best saved place for a spoken name, or None. 'judging' finds 'judging area'."""
    places = load_places() if places is None else places
    name = normalize(name)
    if name in places:
        return name
    partial = [k for k in places if name in k or k in name]
    if len(partial) == 1:
        return partial[0]
    close = difflib.get_close_matches(name, list(places), n=1, cutoff=.6)
    return close[0] if close else None


def save_place(name):
    """Save the robot's current pose under `name`. Returns (name, x, y)."""
    name = normalize(name)
    x, y, yaw = read_pose()
    places = load_places()
    places[name] = {"x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 4)}
    tmp = PLACES_FILE.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(places, sort_keys=True))
    tmp.replace(PLACES_FILE)          # atomic: voice.py may read this mid-write
    return name, x, y


def forget_place(name):
    places = load_places()
    found = resolve(name, places)
    if found is None:
        raise ValueError(f"no place called '{normalize(name)}'")
    places.pop(found)
    name = found
    tmp = PLACES_FILE.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(places, sort_keys=True))
    tmp.replace(PLACES_FILE)
    return name


def write_goal(writer, goal, enabled):
    with writer.buf() as command:
        command["enabled"] = enabled
        command["waypoints"].fill(np.nan)
        command["num_waypoints"] = 1 if goal else 0
        if goal:
            x, y, yaw = goal
            command["waypoints"][0] = (x, y, np.nan if yaw is None else yaw)
        command["loop"] = False
        command["global_goal"] = False


def go(name, cancel=None, on_status=print):
    """Drive to a saved place. Returns True on reached; raises ValueError/RuntimeError
    if the place is unknown or nav.command is owned elsewhere. `cancel` is an optional
    threading.Event that aborts the goal."""
    places = load_places()
    found = resolve(name, places)
    if found is None:
        raise ValueError(f"Unknown place '{normalize(name)}'. Known: {', '.join(places) or 'none'}")
    name = found
    p = places[name]
    goal = (p["x"], p["y"], p.get("yaw"))
    try:
        writer = Writer("nav.command", Type("nav_command"), keeptime=False)
    except RuntimeError as e:
        raise RuntimeError(f"{e} Stop navigation in the nav web UI (it owns nav.command) and retry.")

    sent_at = time.time_ns()
    write_goal(writer, goal, True)
    on_status(f"-> {name} ({goal[0]:.2f}, {goal[1]:.2f})")
    last = None
    try:
        with Reader("nav.state", keeptime=False) as states:
            deadline = time.time() + GOAL_TIMEOUT_S
            while time.time() < deadline:
                if cancel is not None and cancel.is_set():
                    on_status("   cancelled")
                    return False
                if states.ready() and int(states.data["timestamp"]) > sent_at:
                    status = states.data["state"].decode()
                    reason = states.data["reason"].decode()
                    if (status, reason) != last:
                        on_status(f"   {status}{': ' + reason if reason else ''}")
                        last = (status, reason)
                    if status in ("reached", "failed"):
                        return status == "reached"
                time.sleep(0.05)
            on_status("   timed out")
            return False
    finally:
        write_goal(writer, None, False)   # never leave the base with a live goal
        writer.__exit__(None, None, None)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "where":
        x, y, yaw = read_pose()
        print(f"x={x:.3f} y={y:.3f} yaw={math.degrees(yaw):.1f}°")
    elif cmd == "save" and len(argv) >= 3:
        name, x, y = save_place(" ".join(argv[2:]))
        print(f"saved {name}: x={x:.3f} y={y:.3f}")
    elif cmd == "forget" and len(argv) >= 3:
        print(f"forgot {forget_place(' '.join(argv[2:]))}")
    elif cmd == "list":
        for name, p in load_places().items():
            print(f"{name:16s} x={p['x']:.2f} y={p['y']:.2f}")
    elif cmd == "go" and len(argv) == 3:
        try:
            ok = go(argv[2])
        except (ValueError, RuntimeError) as e:
            raise SystemExit(str(e))
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        pass
