#!/usr/bin/env python3
# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "bbos",
#   "numpy<3",
#   "posix-ipc",
# ]
#
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/bbos", editable = true }
# ///
"""Print live arm motor state without commanding motion.

This is a calibration/debugging helper. It only opens BBOS readers for the arm
state topics and prints the values it sees.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any

import numpy as np


DOF = 8
JOINT_NAMES = {
    "left": ["lj0", "lj1", "lj2", "lj3", "lj4", "lj5", "lj6", "left_gripper"],
    "right": ["rj0", "rj1", "rj2", "rj3", "rj4", "rj5", "rj6", "right_gripper"],
}


def _as_plain(value: Any):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode(errors="replace").rstrip("\x00")
    return value


def _summarize_extra_fields(record, skip: set[str]):
    extras = {}
    if record is None:
        return extras
    for key in record.dtype.names or ():
        if key in skip:
            continue
        value = _as_plain(record[key])
        if isinstance(value, list):
            arr = np.asarray(value)
            if arr.size <= 16 and np.issubdtype(arr.dtype, np.number):
                extras[key] = value
            elif np.issubdtype(arr.dtype, np.number):
                extras[key] = {
                    "shape": list(arr.shape),
                    "min": float(np.nanmin(arr)),
                    "max": float(np.nanmax(arr)),
                    "mean": float(np.nanmean(arr)),
                }
            else:
                extras[key] = value[:8]
        else:
            extras[key] = value
    return extras


def _format_joint_table(side: str, pos_turns: np.ndarray) -> list[dict]:
    names = JOINT_NAMES.get(side, [f"j{i}" for i in range(len(pos_turns))])
    rows = []
    for idx, turns in enumerate(pos_turns):
        turns_f = float(turns)
        rows.append(
            {
                "idx": idx,
                "name": names[idx] if idx < len(names) else f"j{idx}",
                "turns": turns_f,
                "deg": turns_f * 360.0,
                "rad": turns_f * 2.0 * math.pi,
            }
        )
    return rows


def read_arm_snapshot(readers):
    snapshot = {}
    for side, reader in readers.items():
        reader.ready()
        if not reader.readable or reader.data is None:
            snapshot[side] = {"readable": False}
            continue
        record = reader.data
        pos = np.asarray(record["pos"], dtype=np.float64).reshape(-1)
        snapshot[side] = {
            "readable": True,
            "joints": _format_joint_table(side, pos),
            "pos_turns": pos.tolist(),
            "extra": _summarize_extra_fields(record, {"pos"}),
        }
    return snapshot


def print_human(cycle: int, elapsed_s: float, snapshot: dict):
    print(f"\ncycle={cycle} elapsed_s={elapsed_s:.3f}")
    for side in ("left", "right"):
        arm = snapshot.get(side, {})
        print(f"{side.upper()} ARM readable={arm.get('readable', False)}")
        if not arm.get("readable"):
            continue
        for joint in arm["joints"]:
            print(
                "  "
                f"{joint['idx']:>1} {joint['name']:<14} "
                f"turns={joint['turns']:+.6f} "
                f"deg={joint['deg']:+8.3f} "
                f"rad={joint['rad']:+8.4f}"
            )
        if arm.get("extra"):
            print(f"  extra={json.dumps(arm['extra'], default=str)}")
    print("", flush=True)


def build_parser():
    parser = argparse.ArgumentParser(description="Print live BBOS arm motor states. Read-only; does not command motors.")
    parser.add_argument("--side", choices=("left", "right", "both"), default="both", help="Which arm state topic to watch.")
    parser.add_argument("--interval-s", type=float, default=0.25, help="Seconds between print cycles.")
    parser.add_argument("--cycles", type=int, default=0, help="Number of cycles to print; 0 means forever.")
    parser.add_argument("--json", action="store_true", help="Print one JSON object per cycle instead of a human table.")
    return parser


def main() -> int:
    from bbos import Reader

    args = build_parser().parse_args()
    sides = ("left", "right") if args.side == "both" else (args.side,)
    readers = {side: Reader(f"arm_{side}.state", keeptime=False) for side in sides}
    entered = []
    try:
        for reader in readers.values():
            reader.__enter__()
            entered.append(reader)
        t0 = time.time()
        cycle = 0
        while args.cycles <= 0 or cycle < args.cycles:
            cycle += 1
            elapsed = time.time() - t0
            snapshot = read_arm_snapshot(readers)
            payload = {"cycle": cycle, "elapsed_s": elapsed, "arms": snapshot}
            if args.json:
                print(json.dumps(payload, default=str), flush=True)
            else:
                print_human(cycle, elapsed, snapshot)
            time.sleep(max(0.0, args.interval_s))
    finally:
        for reader in reversed(entered):
            reader.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
