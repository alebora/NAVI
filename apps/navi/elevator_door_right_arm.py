#!/usr/bin/env python3
# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "bbos",
#   "numpy<3",
#   "opencv-python-headless>=4.10,<5",
#   "posix-ipc",
#   "pyyaml",
# ]
#
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/bbos", editable = true }
# ///
"""Experimental right-arm elevator-door targeting.

This file is intentionally separate from assistant.py and the working robot
behaviors. By default it only reads the right wrist camera, runs a YOLO-style
ONNX detector, and prints a movement plan. It only sends arm commands when
started with --execute.

The controller is deliberately limited to right-arm joints 0, 3, and 6:

* J0: vertical stage, used to move the claw camera up/down.
* J3: elbow, used as a conservative approach/retreat adjustment.
* J6: claw/wrist turn, used to aim left/right at the button.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


DOF = 8
J0_VERTICAL = 0
J3_ELBOW = 3
J6_CLAW_TURN = 6
DEFAULT_CAMERA_TOPIC = "camera.right.jpeg"
DEFAULT_TARGET_CLASSES = (
    "elevator_button",
    "door_button",
    "elevator_door_button",
    "door_handle",
    "button",
)
DEFAULT_PRESET_FILE = Path(__file__).with_name("elevator_button_preset.json")


@dataclass
class Detection:
    label: str
    confidence: float
    bbox_xywh: tuple[float, float, float, float]
    center_xy: tuple[float, float]
    area_px: float
    distance_m: float | None = None


@dataclass
class Plan:
    status: str
    reason: str
    j0_delta_turns: float = 0.0
    j3_delta_turns: float = 0.0
    j6_delta_turns: float = 0.0
    vertical_error_px: float = 0.0
    horizontal_error_px: float = 0.0
    target: Detection | None = None


def load_labels(path: Path | None) -> list[str]:
    if path is None:
        return []
    labels = []
    for raw in path.read_text().splitlines():
        label = raw.strip()
        if label and not label.startswith("#"):
            labels.append(label)
    return labels


def _enter_many(*objects):
    handles = []
    try:
        for obj in objects:
            obj.__enter__()
            handles.append(obj)
        return handles
    except Exception:
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)
        raise


def read_wrist_frame(topic: str, timeout_s: float):
    from bbos import Reader

    reader = Reader(topic, keeptime=False)
    handles = _enter_many(reader)
    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            reader.ready()
            if reader.readable and reader.data is not None:
                data = reader.data
                jpeg_len = int(data["jpeg_len"])
                if jpeg_len > 0:
                    jpeg = np.asarray(data["jpeg"][:jpeg_len], dtype=np.uint8)
                    image = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
                    if image is not None:
                        return image
            time.sleep(0.03)
    finally:
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)
    raise TimeoutError(f"No JPEG frame arrived on {topic!r} within {timeout_s:.1f}s")


def load_yolo_model(model_path: Path | None):
    if model_path is None:
        return None
    cv2.setNumThreads(2)
    return cv2.dnn.readNetFromONNX(str(model_path))


def _normalize_yolo_output(output: np.ndarray) -> np.ndarray:
    arr = np.asarray(output)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim != 2:
        raise ValueError(f"Unsupported YOLO output shape: {arr.shape}")
    # YOLOv8 exports are often (classes + 4, anchors); YOLOv5 exports are
    # usually (anchors, classes + 5). Keep rows as candidate detections.
    if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 256:
        arr = arr.T
    return arr.astype(np.float32, copy=False)


def detect_yolo(
    image_bgr: np.ndarray,
    net,
    labels: list[str],
    confidence_threshold: float,
    nms_threshold: float,
    input_size: int,
    target_classes: set[str],
    focal_px: float | None,
    target_width_m: float | None,
) -> list[Detection]:
    height, width = image_bgr.shape[:2]
    scale = input_size / max(height, width)
    resized_w = max(1, round(width * scale))
    resized_h = max(1, round(height * scale))
    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    resized = cv2.resize(image_bgr, (resized_w, resized_h))
    canvas[:resized_h, :resized_w] = resized

    blob = cv2.dnn.blobFromImage(canvas, scalefactor=1 / 255.0, size=(input_size, input_size), swapRB=True)
    net.setInput(blob)
    rows = _normalize_yolo_output(net.forward())

    boxes: list[list[float]] = []
    scores: list[float] = []
    chosen_labels: list[str] = []
    for row in rows:
        if row.shape[0] < 6:
            continue

        cx, cy, bw, bh = (float(v) for v in row[:4])
        if row.shape[0] == 6:
            class_id = int(row[5])
            score = float(row[4])
        else:
            class_scores = row[5:] * float(row[4]) if row.shape[0] > 85 else row[4:]
            class_id = int(np.argmax(class_scores))
            score = float(class_scores[class_id])

        if score < confidence_threshold:
            continue
        label = labels[class_id] if 0 <= class_id < len(labels) else str(class_id)
        if target_classes and label not in target_classes:
            continue

        x = (cx - bw / 2) / scale
        y = (cy - bh / 2) / scale
        box_w = bw / scale
        box_h = bh / scale
        if box_w < 4 or box_h < 4:
            continue
        boxes.append([x, y, box_w, box_h])
        scores.append(score)
        chosen_labels.append(label)

    if not boxes:
        return []

    ids = cv2.dnn.NMSBoxes(boxes, scores, confidence_threshold, nms_threshold)
    detections: list[Detection] = []
    for idx in np.asarray(ids).ravel():
        x, y, box_w, box_h = boxes[int(idx)]
        distance_m = None
        if focal_px and target_width_m and box_w > 1:
            distance_m = float((focal_px * target_width_m) / box_w)
        detections.append(
            Detection(
                label=chosen_labels[int(idx)],
                confidence=float(scores[int(idx)]),
                bbox_xywh=(float(x), float(y), float(box_w), float(box_h)),
                center_xy=(float(x + box_w / 2), float(y + box_h / 2)),
                area_px=float(box_w * box_h),
                distance_m=distance_m,
            )
        )
    return sorted(detections, key=lambda det: (det.confidence, det.area_px), reverse=True)


def plan_from_detection(image_shape, target: Detection | None, args) -> Plan:
    if target is None:
        return Plan(status="no_target", reason="No configured elevator-door target was detected.")

    height, width = image_shape[:2]
    center_x, center_y = target.center_xy
    horizontal_error = center_x - width / 2
    vertical_error = center_y - height / 2

    j0_delta = -vertical_error * args.j0_gain
    j0_delta = float(np.clip(j0_delta, -args.max_j0_step, args.max_j0_step))

    j6_delta = -horizontal_error * args.j6_gain
    j6_delta = float(np.clip(j6_delta, -args.max_j6_step, args.max_j6_step))

    j3_delta = 0.0
    reason = "Plan uses J0 for vertical centering and J6 for left/right claw aim. J3 is held unless distance data is configured."
    if target.distance_m is not None and args.desired_distance_m is not None:
        distance_error = target.distance_m - args.desired_distance_m
        j3_delta = distance_error * args.j3_distance_gain
        j3_delta = float(np.clip(j3_delta, -args.max_j3_step, args.max_j3_step))
        reason = "Plan uses J0 for vertical centering and J3 for distance/approach adjustment."

    return Plan(
        status="planned",
        reason=reason,
        j0_delta_turns=j0_delta,
        j3_delta_turns=j3_delta,
        j6_delta_turns=j6_delta,
        vertical_error_px=float(vertical_error),
        horizontal_error_px=float(horizontal_error),
        target=target,
    )


def _read_arm_pos(reader, timeout_s: float) -> np.ndarray:
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


def execute_plan(plan: Plan, move_duration_s: float, state_timeout_s: float):
    if plan.status != "planned":
        return {"status": "skipped", "reason": plan.reason}
    if plan.j0_delta_turns == 0.0 and plan.j3_delta_turns == 0.0 and plan.j6_delta_turns == 0.0:
        return {"status": "skipped", "reason": "Planned movement is zero."}

    from bbos import Reader, Type, Writer

    state = Reader("arm_right.state", keeptime=False)
    ctrl = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
    torque = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
    handles = _enter_many(state, ctrl, torque)
    torque_mask = np.zeros(DOF, dtype=np.bool_)
    torque_mask[J0_VERTICAL] = True
    torque_mask[J3_ELBOW] = True
    torque_mask[J6_CLAW_TURN] = True
    try:
        start = _read_arm_pos(state, state_timeout_s)
        goal = start.copy()
        goal[J0_VERTICAL] += plan.j0_delta_turns
        goal[J3_ELBOW] += plan.j3_delta_turns
        goal[J6_CLAW_TURN] += plan.j6_delta_turns

        ctrl["pos"] = start
        time.sleep(0.05)
        torque["enable"] = torque_mask
        time.sleep(0.05)
        _smooth_write(ctrl, start, goal, move_duration_s)
        return {
            "status": "moved",
            "j0_delta_turns": plan.j0_delta_turns,
            "j3_delta_turns": plan.j3_delta_turns,
            "j6_delta_turns": plan.j6_delta_turns,
            "goal": goal.tolist(),
        }
    finally:
        with contextlib.suppress(Exception):
            torque["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)


def read_right_arm_position(state_timeout_s: float) -> list[float]:
    from bbos import Reader

    state = Reader("arm_right.state", keeptime=False)
    handles = _enter_many(state)
    try:
        return _read_arm_pos(state, state_timeout_s).tolist()
    finally:
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)


def load_preset(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Use --action save-preset at the calibrated button pose first.")
    data = json.loads(path.read_text())
    joints = data.get("right_arm_pos")
    if not isinstance(joints, list) or len(joints) != DOF:
        raise ValueError(f"{path} must contain right_arm_pos with {DOF} joint values.")
    return data


def save_preset(path: Path, state_timeout_s: float):
    joints = read_right_arm_position(state_timeout_s)
    payload = {
        "right_arm_pos": joints,
        "active_joints": [J0_VERTICAL, J3_ELBOW, J6_CLAW_TURN],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "Calibrated elevator button pose for the right arm. Only joints 0, 3, and 6 are torqued by fixed modes.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def move_to_fixed_button_pose(preset_path: Path, move_duration_s: float, state_timeout_s: float):
    from bbos import Reader, Type, Writer

    preset = load_preset(preset_path)
    target = np.asarray(preset["right_arm_pos"], dtype=np.float32)

    state = Reader("arm_right.state", keeptime=False)
    ctrl = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
    torque = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
    handles = _enter_many(state, ctrl, torque)
    torque_mask = np.zeros(DOF, dtype=np.bool_)
    torque_mask[J0_VERTICAL] = True
    torque_mask[J3_ELBOW] = True
    torque_mask[J6_CLAW_TURN] = True
    try:
        start = _read_arm_pos(state, state_timeout_s)
        goal = start.copy()
        for joint in (J0_VERTICAL, J3_ELBOW, J6_CLAW_TURN):
            goal[joint] = target[joint]
        ctrl["pos"] = start
        time.sleep(0.05)
        torque["enable"] = torque_mask
        time.sleep(0.05)
        _smooth_write(ctrl, start, goal, move_duration_s)
        return {
            "status": "moved_to_fixed_button_pose",
            "preset": str(preset_path),
            "active_joints": [J0_VERTICAL, J3_ELBOW, J6_CLAW_TURN],
            "goal": goal.tolist(),
        }
    finally:
        with contextlib.suppress(Exception):
            torque["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)


def press_button(press_delta_turns: float, hold_s: float, move_duration_s: float, state_timeout_s: float):
    """Small elbow press-and-return motion. Requires an intentional action flag."""
    from bbos import Reader, Type, Writer

    state = Reader("arm_right.state", keeptime=False)
    ctrl = Writer("arm_right.ctrl", Type("arm_ctrl"), keeptime=False)
    torque = Writer("arm_right.torque", Type("arm_torque"), keeptime=False)
    handles = _enter_many(state, ctrl, torque)
    torque_mask = np.zeros(DOF, dtype=np.bool_)
    torque_mask[J3_ELBOW] = True
    try:
        start = _read_arm_pos(state, state_timeout_s)
        pressed = start.copy()
        pressed[J3_ELBOW] += press_delta_turns
        ctrl["pos"] = start
        time.sleep(0.05)
        torque["enable"] = torque_mask
        time.sleep(0.05)
        _smooth_write(ctrl, start, pressed, move_duration_s)
        time.sleep(max(0.0, hold_s))
        _smooth_write(ctrl, pressed, start, move_duration_s)
        return {"status": "pressed", "j3_delta_turns": press_delta_turns}
    finally:
        with contextlib.suppress(Exception):
            torque["enable"] = np.zeros(DOF, dtype=np.bool_)
        for obj in reversed(handles):
            with contextlib.suppress(Exception):
                obj.__exit__(None, None, None)


def read_pose(timeout_s: float):
    from bbos import Reader

    with Reader("slam.pose", keeptime=False) as poses:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if poses.ready() and poses.data is not None:
                pose = poses.data
                yaw = 2.0 * math.atan2(float(pose["quat"][2]), float(pose["quat"][3]))
                return float(pose["pos"][0]), float(pose["pos"][1]), yaw
            time.sleep(0.02)
    raise TimeoutError("No slam.pose frame arrived.")


def load_place(path: Path, name: str):
    import yaml

    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    places = yaml.safe_load(path.read_text()) or {}
    if name not in places:
        raise KeyError(f"Unknown place {name!r}; known places: {', '.join(places) or 'none'}")
    place = places[name]
    return float(place["x"]), float(place["y"]), place.get("yaw")


def check_elevator_place(args):
    if not args.elevator_place:
        return {"status": "not_checked", "reason": "No --elevator-place was provided."}
    x, y, yaw = read_pose(args.timeout_s)
    px, py, _ = load_place(args.places_file, args.elevator_place)
    distance = math.hypot(x - px, y - py)
    ok = distance <= args.elevator_radius_m
    return {
        "status": "at_elevator" if ok else "not_at_elevator",
        "place": args.elevator_place,
        "distance_m": distance,
        "radius_m": args.elevator_radius_m,
        "pose": [x, y, yaw],
    }


def _write_nav_goal(writer, goal, enabled: bool):
    with writer.buf() as command:
        command["enabled"] = enabled
        command["waypoints"].fill(np.nan)
        command["num_waypoints"] = 1 if goal else 0
        if goal:
            command["waypoints"][0] = (goal[0], goal[1], goal[2])
        command["loop"] = False
        command["global_goal"] = False


def enter_elevator(args):
    """Drive a simple relative left-plus-forward route after the button press."""
    from bbos import Reader, Type, Writer

    x, y, yaw = read_pose(args.timeout_s)
    forward = np.array([math.cos(yaw), math.sin(yaw)], dtype=float)
    left = np.array([-math.sin(yaw), math.cos(yaw)], dtype=float)
    target_xy = np.array([x, y], dtype=float) + left * args.enter_left_m + forward * args.enter_forward_m
    goal = (float(target_xy[0]), float(target_xy[1]), yaw)

    writer = Writer("nav.command", Type("nav_command"), keeptime=False)
    writer.__enter__()
    sent_at = time.time_ns()
    try:
        _write_nav_goal(writer, goal, True)
        with Reader("nav.state", keeptime=False) as states:
            deadline = time.time() + args.enter_timeout_s
            last = None
            while time.time() < deadline:
                if states.ready() and int(states.data["timestamp"]) > sent_at:
                    status = states.data["state"].decode()
                    reason = states.data["reason"].decode()
                    last = {"state": status, "reason": reason}
                    if status in ("reached", "failed"):
                        return {"status": status, "reason": reason, "goal": goal}
                time.sleep(0.05)
            return {"status": "timed_out", "last": last, "goal": goal}
    finally:
        with contextlib.suppress(Exception):
            _write_nav_goal(writer, None, False)
        with contextlib.suppress(Exception):
            writer.__exit__(None, None, None)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect an elevator-door target with the right wrist camera, align the right arm, optionally press, then optionally enter."
    )
    parser.add_argument(
        "--action",
        choices=("plan", "align", "press", "enter", "full", "save-preset", "fixed-align", "fixed-full"),
        default="plan",
        help="plan=dry detection plan, align=vision servo, press=J3 button press, enter=left/forward nav, full=vision align + press + enter, save-preset=store current arm pose, fixed-align/fixed-full=use calibrated pose.",
    )
    parser.add_argument("--model", type=Path, help="YOLO/ONNX model path. Required for detection.")
    parser.add_argument("--labels", type=Path, help="Labels file with one class name per line.")
    parser.add_argument("--target-class", action="append", dest="target_classes", help="Class to target. May be repeated.")
    parser.add_argument("--topic", default=DEFAULT_CAMERA_TOPIC, help=f"Camera JPEG topic. Default: {DEFAULT_CAMERA_TOPIC}")
    parser.add_argument("--confidence", type=float, default=0.45, help="Detection confidence threshold.")
    parser.add_argument("--nms", type=float, default=0.45, help="Non-max suppression threshold.")
    parser.add_argument("--input-size", type=int, default=640, help="YOLO input size in pixels.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of observe/plan cycles.")
    parser.add_argument("--interval-s", type=float, default=0.25, help="Delay between cycles.")
    parser.add_argument("--timeout-s", type=float, default=2.0, help="Camera/state frame timeout.")
    parser.add_argument("--save-frame", type=Path, help="Optional path to save the latest wrist-camera frame.")
    parser.add_argument("--execute", action="store_true", help="Actually command the arm/nav stages. Without this, the tool is dry-run only.")
    parser.add_argument("--j0-gain", type=float, default=0.00010, help="J0 turns per vertical pixel error.")
    parser.add_argument("--j6-gain", type=float, default=0.00008, help="J6 turns per horizontal pixel error.")
    parser.add_argument("--max-j0-step", type=float, default=0.020, help="Maximum J0 turns per cycle.")
    parser.add_argument("--max-j3-step", type=float, default=0.015, help="Maximum J3 turns per cycle.")
    parser.add_argument("--max-j6-step", type=float, default=0.015, help="Maximum J6 turns per cycle.")
    parser.add_argument("--desired-distance-m", type=float, help="Desired target distance; requires --target-width-m and --focal-px.")
    parser.add_argument("--target-width-m", type=float, help="Physical target width for monocular distance estimate.")
    parser.add_argument("--focal-px", type=float, help="Camera focal length in pixels for distance estimate.")
    parser.add_argument("--j3-distance-gain", type=float, default=0.015, help="J3 turns per meter of distance error.")
    parser.add_argument("--align-tolerance-px", type=float, default=24.0, help="Target is aligned when horizontal and vertical pixel errors are within this.")
    parser.add_argument("--move-duration-s", type=float, default=0.45, help="Smoothing time for each executed adjustment.")
    parser.add_argument("--press-delta-turns", type=float, default=0.030, help="Small J3 press delta used by --action press/full.")
    parser.add_argument("--press-hold-s", type=float, default=0.35, help="How long to hold the press before retracting.")
    parser.add_argument("--preset-file", type=Path, default=DEFAULT_PRESET_FILE, help="Saved fixed button pose for save-preset/fixed modes.")
    parser.add_argument("--enter-left-m", type=float, default=0.35, help="Relative left move after pressing.")
    parser.add_argument("--enter-forward-m", type=float, default=0.90, help="Relative forward move after the left offset.")
    parser.add_argument("--enter-timeout-s", type=float, default=30.0, help="Timeout for the entry navigation command.")
    parser.add_argument("--elevator-place", help="Optional place name that marks the elevator approach point.")
    parser.add_argument(
        "--places-file",
        type=Path,
        default=Path(__file__).with_name("places.yaml"),
        help="places.yaml path used by --elevator-place.",
    )
    parser.add_argument("--elevator-radius-m", type=float, default=0.85, help="Maximum distance from --elevator-place for --action full.")
    parser.add_argument("--skip-place-check", action="store_true", help="Allow --action full even if --elevator-place is not checked.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON lines.")
    return parser


def print_result(payload: dict, as_json: bool):
    if as_json:
        print(json.dumps(payload, default=str), flush=True)
        return
    print(json.dumps(payload, indent=2, default=str), flush=True)


def main() -> int:
    args = build_arg_parser().parse_args()
    target_classes = set(args.target_classes or DEFAULT_TARGET_CLASSES)
    labels = load_labels(args.labels)

    if args.action == "save-preset":
        payload = {"action": "save-preset", "preset_file": str(args.preset_file)}
        if args.execute:
            payload["preset"] = save_preset(args.preset_file, args.timeout_s)
        else:
            payload["safe_default"] = "No file was written because --execute was not provided."
            payload["detail"] = "Move the arm to the correct button pose, then rerun with --execute to save it."
        print_result(payload, args.json)
        return 0

    if args.action in ("fixed-align", "fixed-full"):
        payload = {
            "action": args.action,
            "preset_file": str(args.preset_file),
            "mode": "execute" if args.execute else "dry_run",
        }
        if args.execute:
            payload["alignment_execution"] = move_to_fixed_button_pose(args.preset_file, args.move_duration_s, args.timeout_s)
        else:
            payload["plan"] = {
                "detail": "Would move motors 0, 3, and 6 to the saved elevator button preset.",
                "active_joints": [J0_VERTICAL, J3_ELBOW, J6_CLAW_TURN],
            }
        if args.action == "fixed-full":
            payload["press"] = {"j3_delta_turns": args.press_delta_turns, "hold_s": args.press_hold_s}
            payload["enter"] = {"left_m": args.enter_left_m, "forward_m": args.enter_forward_m}
            if args.execute:
                payload["press_execution"] = press_button(args.press_delta_turns, args.press_hold_s, args.move_duration_s, args.timeout_s)
                payload["enter_execution"] = enter_elevator(args)
        print_result(payload, args.json)
        return 0

    if args.action == "press":
        payload = {"action": "press", "mode": "execute" if args.execute else "dry_run"}
        if args.execute:
            payload["execution"] = press_button(args.press_delta_turns, args.press_hold_s, args.move_duration_s, args.timeout_s)
        else:
            payload["plan"] = {"j3_delta_turns": args.press_delta_turns, "hold_s": args.press_hold_s}
        print_result(payload, args.json)
        return 0

    if args.action == "enter":
        payload = {
            "action": "enter",
            "mode": "execute" if args.execute else "dry_run",
            "enter_left_m": args.enter_left_m,
            "enter_forward_m": args.enter_forward_m,
        }
        if args.execute:
            payload["execution"] = enter_elevator(args)
        print_result(payload, args.json)
        return 0

    if args.action == "full" and not args.skip_place_check:
        place_check = check_elevator_place(args)
        print_result({"action": "place_check", **place_check}, args.json)
        if place_check["status"] != "at_elevator":
            return 3

    if args.model is None:
        print_result(
            {
                "status": "needs_model",
                "detail": "Pass --model with a YOLO/ONNX detector trained for elevator buttons, door handles, or the target object.",
                "default_target_classes": sorted(target_classes),
                "safe_default": "No arm movement was attempted.",
            },
            args.json,
        )
        return 2

    net = load_yolo_model(args.model)
    aligned = False
    for i in range(args.iterations):
        image = read_wrist_frame(args.topic, args.timeout_s)
        if args.save_frame:
            args.save_frame.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.save_frame), image)

        detections = detect_yolo(
            image,
            net,
            labels,
            args.confidence,
            args.nms,
            args.input_size,
            target_classes,
            args.focal_px,
            args.target_width_m,
        )
        target = detections[0] if detections else None
        plan = plan_from_detection(image.shape, target, args)
        payload = {
            "cycle": i + 1,
            "image_shape": list(image.shape),
            "target_classes": sorted(target_classes),
            "detections": [asdict(det) for det in detections[:5]],
            "plan": asdict(plan),
            "mode": "execute" if args.execute else "dry_run",
        }
        aligned = (
            plan.status == "planned"
            and abs(plan.vertical_error_px) <= args.align_tolerance_px
            and abs(plan.horizontal_error_px) <= args.align_tolerance_px
        )
        payload["aligned"] = aligned
        if args.action in ("align", "full") and args.execute and not aligned:
            payload["execution"] = execute_plan(plan, args.move_duration_s, args.timeout_s)
        print_result(payload, args.json)
        if aligned and args.action in ("align", "full"):
            break
        if i + 1 < args.iterations:
            time.sleep(args.interval_s)

    if args.action == "full":
        if not aligned:
            print_result(
                {
                    "action": "full",
                    "status": "not_aligned",
                    "detail": "Button target did not reach alignment tolerance; press/enter were skipped.",
                    "safe_default": "No button press or entry navigation was attempted.",
                },
                args.json,
            )
            return 4
        payload = {
            "action": "full_press_and_enter",
            "mode": "execute" if args.execute else "dry_run",
            "press": {"j3_delta_turns": args.press_delta_turns, "hold_s": args.press_hold_s},
            "enter": {"left_m": args.enter_left_m, "forward_m": args.enter_forward_m},
        }
        if args.execute:
            payload["press_execution"] = press_button(args.press_delta_turns, args.press_hold_s, args.move_duration_s, args.timeout_s)
            payload["enter_execution"] = enter_elevator(args)
        print_result(payload, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
