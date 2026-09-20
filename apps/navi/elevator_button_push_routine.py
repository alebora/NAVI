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
"""Replay a calibrated right-arm elevator button press.

This is separate from assistant.py and does not run unless launched directly.
It is dry-run by default. Add --execute only when the robot is physically in
the calibrated elevator-panel orientation.

The built-in poses came from the pasted arm_motor_watch output where the right
training wheels and arm were lined up with the elevator buttons.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import time
from dataclasses import dataclass

import numpy as np


DOF = 8
RIGHT_JOINT_NAMES = ["rj0", "rj1", "rj2", "rj3", "rj4", "rj5", "rj6", "right_gripper"]
J0_LOWER_TURNS = 0.110
J3_OPEN_TURNS = 10.0 / 360.0

# Cycle 1 from the pasted watcher output: aligned/ready before the press.
READY_POSE = np.array(
    [
        0.429668,
        -0.002190,
        -0.001534,
        -0.005688,
        -0.001221,
        -0.014526,
        -0.029297,
        0.009277,
    ],
    dtype=np.float32,
)
READY_POSE[0] -= J0_LOWER_TURNS
READY_POSE[3] += J3_OPEN_TURNS

# Cycle 8 from the pasted watcher output: near the button, not yet at max press.
APPROACH_POSE = np.array(
    [
        0.436504,
        0.007576,
        0.013603,
        -0.243969,
        -0.013428,
        -0.034546,
        0.042969,
        0.010498,
    ],
    dtype=np.float32,
)
APPROACH_POSE[0] -= J0_LOWER_TURNS
APPROACH_POSE[3] += J3_OPEN_TURNS

# Average of cycles 11-13 from the fuller watcher output: held button-press
# region after the initial motion spike settled.
PRESS_POSE = np.array(
    [
        0.436504,
        -0.009677,
        0.013440,
        -0.316641,
        -0.026774,
        -0.004110,
        -0.058919,
        0.009929,
    ],
    dtype=np.float32,
)
PRESS_POSE[0] -= J0_LOWER_TURNS
PRESS_POSE[3] += J3_OPEN_TURNS

# Use the arm joints, leave the gripper alone unless explicitly requested.
DEFAULT_ACTIVE_JOINTS = (0, 1, 2, 3, 4, 5, 6)


@dataclass
class RoutineStep:
    name: str
    pose: np.ndarray
    duration_s: float
    hold_s: float = 0.0


def _read_pos(reader, timeout_s: float) -> np.ndarray:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        reader.ready()
        if reader.readable and reader.data is not None:
            return np.asarray(reader.data["pos"], dtype=np.float32).copy()
        time.sleep(0.02)
    raise TimeoutError("No right-arm state frame arrived.")


def _smooth_write(writer, start: np.ndarray, goal: np.ndarray, duration_s: float):
    start = np.asarray(start, dtype=np.float32)
    goal = np.asarray(goal, dtype=np.float32)
    t0 = time.time()
    while True:
        u = min(1.0, (time.time() - t0) / max(duration_s, 1e-3))
        s = u * u * (3.0 - 2.0 * u)
        writer["pos"] = (1.0 - s) * start + s * goal
        if u >= 1.0:
            return
        time.sleep(0.02)


def _active_mask(include_gripper: bool) -> np.ndarray:
    active = list(DEFAULT_ACTIVE_JOINTS)
    if include_gripper:
        active.append(7)
    mask = np.zeros(DOF, dtype=np.bool_)
    mask[active] = True
    return mask


def _pose_for_active_joints(current: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    goal = current.copy()
    goal[mask] = target[mask]
    return goal


def pose_summary(pose: np.ndarray):
    rows = []
    for idx, turns in enumerate(pose):
        turns = float(turns)
        rows.append(
            {
                "idx": idx,
                "name": RIGHT_JOINT_NAMES[idx],
                "turns": turns,
                "deg": turns * 360.0,
                "rad": turns * 2.0 * np.pi,
            }
        )
    return rows


def build_routine(args) -> list[RoutineStep]:
    return [
        RoutineStep("ready", READY_POSE, args.ready_duration_s, args.ready_hold_s),
        RoutineStep("approach", APPROACH_POSE, args.approach_duration_s, args.approach_hold_s),
        RoutineStep("press", PRESS_POSE, args.press_duration_s, args.press_hold_s),
        RoutineStep("release", APPROACH_POSE, args.release_duration_s, args.release_hold_s),
        RoutineStep("retract", READY_POSE, args.retract_duration_s, args.retract_hold_s),
    ]


def run_routine(args):
    mask = _active_mask(args.include_gripper)
    routine = build_routine(args)
    if not args.execute:
        return {
            "mode": "dry_run",
            "active_joints": np.nonzero(mask)[0].tolist(),
            "ready_pose": pose_summary(READY_POSE),
            "approach_pose": pose_summary(APPROACH_POSE),
            "press_pose": pose_summary(PRESS_POSE),
            "steps": [
                {"name": step.name, "duration_s": step.duration_s, "hold_s": step.hold_s}
                for step in routine
            ],
        }

    from bbos import Reader, Type, Writer

    state = Reader("arm_right.state", keeptime=False)
    ctrl = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
    torque = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
    handles = []
    try:
        for obj in (state, ctrl, torque):
            obj.__enter__()
            handles.append(obj)

        current = _read_pos(state, args.timeout_s)
        ctrl["pos"] = current
        time.sleep(0.05)
        torque["enable"] = mask
        time.sleep(0.05)

        executed = []
        for step in routine:
            goal = _pose_for_active_joints(current, step.pose, mask)
            _smooth_write(ctrl, current, goal, step.duration_s)
            current = goal
            if step.hold_s > 0:
                time.sleep(step.hold_s)
            executed.append({"name": step.name, "goal": goal.tolist()})
        return {"mode": "execute", "status": "completed", "executed": executed}
    finally:
        with contextlib.suppress(Exception):
            torque["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)


def build_parser():
    parser = argparse.ArgumentParser(description="Replay the calibrated right-arm elevator button press routine.")
    parser.add_argument("--execute", action="store_true", help="Actually command the right arm. Omit for dry-run.")
    parser.add_argument("--include-gripper", action="store_true", help="Also command joint 7/gripper from the captured poses.")
    parser.add_argument("--timeout-s", type=float, default=2.0, help="Right-arm state read timeout.")
    parser.add_argument("--ready-duration-s", type=float, default=1.20, help="Move time into ready pose.")
    parser.add_argument("--ready-hold-s", type=float, default=0.20, help="Hold time at ready pose.")
    parser.add_argument("--approach-duration-s", type=float, default=0.90, help="Move time from ready to approach.")
    parser.add_argument("--approach-hold-s", type=float, default=0.10, help="Hold time before pressing.")
    parser.add_argument("--press-duration-s", type=float, default=0.65, help="Move time from approach to press.")
    parser.add_argument("--press-hold-s", type=float, default=0.55, help="Hold time while pressing.")
    parser.add_argument("--release-duration-s", type=float, default=0.55, help="Move time from press back to approach.")
    parser.add_argument("--release-hold-s", type=float, default=0.10, help="Hold time after releasing the button.")
    parser.add_argument("--retract-duration-s", type=float, default=0.80, help="Move time from press back to ready.")
    parser.add_argument("--retract-hold-s", type=float, default=0.0, help="Hold time after retract.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_routine(args)
    if args.json:
        print(json.dumps(result, default=str), flush=True)
    else:
        print(json.dumps(result, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
