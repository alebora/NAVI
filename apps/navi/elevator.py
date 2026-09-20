"""Elevator button action helpers for NAVI.

This module is intentionally small: navigation decides where the robot is, and
the calibrated arm routine only runs after a saved-place proximity/orientation
check passes.
"""

from __future__ import annotations

import argparse
import math

import numpy as np


DEFAULT_PLACE_NAMES = (
    "elevator button",
    "elevator_button",
    "elevator",
)
MAX_DISTANCE_M = 0.40
MAX_YAW_ERROR_DEG = 15.0


def _wrap_angle(rad: float) -> float:
    return (rad + math.pi) % (2.0 * math.pi) - math.pi


def _pose_yaw(pose) -> float:
    q = pose["quat"]
    return 2.0 * math.atan2(float(q[2]), float(q[3]))


def _find_place(controller, requested: str | None):
    names = []
    if requested:
        names.append(requested)
    names.extend(DEFAULT_PLACE_NAMES)
    seen = set()
    for name in names:
        key = " ".join(str(name or "").strip().lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        resolved, location, saved = controller.resolve_place(key)
        if location is not None:
            return resolved, location, saved
    return None, None, controller.places()


def check_at_elevator_button(controller, place_name: str | None = None):
    resolved, location, saved = _find_place(controller, place_name)
    if location is None:
        return {
            "ok": False,
            "status": "unknown_place",
            "detail": (
                "Teach the elevator button spot first, while lined up with the panel: "
                'say "remember here as elevator button".'
            ),
            "known_places": sorted(saved),
        }

    snapshot = controller.ready(wait_s=5.0)
    pose = snapshot.get("slam.pose")
    if pose is None:
        return {"ok": False, "status": "no_pose", "detail": "SLAM pose is unavailable."}

    try:
        epoch = controller.robot.epoch()
    except RuntimeError:
        epoch = None
    if location.get("slam_epoch") != epoch:
        return {
            "ok": False,
            "status": "stale_place",
            "place": resolved,
            "detail": f'"{resolved}" belongs to an older map. Re-save the elevator button spot.',
        }

    current_xy = np.asarray(pose["pos"][:2], dtype=float)
    target_xy = np.asarray([float(location["x"]), float(location["y"])], dtype=float)
    distance_m = float(np.linalg.norm(current_xy - target_xy))
    if distance_m > MAX_DISTANCE_M:
        return {
            "ok": False,
            "status": "too_far",
            "place": resolved,
            "distance_m": distance_m,
            "max_distance_m": MAX_DISTANCE_M,
            "detail": f'Navigate to "{resolved}" first, then try the elevator button.',
        }

    current_yaw = _pose_yaw(pose)
    saved_yaw = location.get("yaw")
    yaw_error_deg = None
    if saved_yaw is None:
        return {
            "ok": False,
            "status": "missing_orientation",
            "place": resolved,
            "distance_m": distance_m,
            "detail": (
                f'"{resolved}" has no saved orientation. Stand lined up with the panel and '
                'save it again as "elevator button".'
            ),
        }
    yaw_error_deg = abs(math.degrees(_wrap_angle(current_yaw - float(saved_yaw))))
    if yaw_error_deg > MAX_YAW_ERROR_DEG:
        return {
            "ok": False,
            "status": "wrong_orientation",
            "place": resolved,
            "distance_m": distance_m,
            "yaw_error_deg": yaw_error_deg,
            "max_yaw_error_deg": MAX_YAW_ERROR_DEG,
            "detail": "Navi is near the elevator spot but not facing the calibrated direction.",
        }

    return {
        "ok": True,
        "status": "ready",
        "place": resolved,
        "distance_m": distance_m,
        "yaw_error_deg": yaw_error_deg,
        "detail": "At calibrated elevator button spot.",
    }


def press_elevator_button(controller, place_name: str | None = None):
    """Run the calibrated button press if the saved-place gate passes."""
    with controller.lock:
        if controller.mode != "idle":
            return {
                "status": "busy",
                "detail": "Stop current navigation or exploration before pressing the elevator button.",
            }
        if not controller.enabled:
            return {
                "status": "movement_disabled",
                "detail": "Restart with --enable-motion before pressing elevator buttons.",
            }
        controller.badge_check()
        gate = check_at_elevator_button(controller, place_name)
        if not gate.get("ok"):
            return gate

    from elevator_button_push_routine import run_routine

    args = argparse.Namespace(
        execute=True,
        include_gripper=False,
        timeout_s=2.0,
        ready_duration_s=1.20,
        ready_hold_s=0.20,
        approach_duration_s=0.90,
        approach_hold_s=0.10,
        press_duration_s=0.65,
        press_hold_s=0.55,
        release_duration_s=0.55,
        release_hold_s=0.10,
        retract_duration_s=0.80,
        retract_hold_s=0.0,
        json=False,
    )
    result = run_routine(args)
    return {
        "status": "pressed",
        "place": gate.get("place"),
        "gate": gate,
        "routine": result,
    }
