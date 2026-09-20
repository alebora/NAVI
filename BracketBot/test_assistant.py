"""Pure simulated tests. No BBOS imports, hardware writers, cloud calls or cameras."""

import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import assistant as a


def record(**fields):
    return dict(timestamp=np.datetime64(time.time_ns(), "ns"), **fields)


def healthy():
    return {
        "slam.pose": record(
            pos=np.array([0.0, 0.0, 0.0]),
            quat=np.array([0.0, 0.0, 0.0, 1.0]),
            pgo_count=0,
        ),
        "slam.health": record(
            localized=True, degraded=False, stalled=False, vo_lost=False
        ),
        "nav.state": record(state=b"navigating", reason=b""),
        "mapping.grid2d": record(
            grid=np.ones((300, 300), np.uint8), origin=np.array([-4.5, -4.5])
        ),
        "mapping.reproject": record(reprojecting=False),
        "camera.depth": record(),
    }


class FakeRobot:
    resolution = 0.03

    def __init__(self):
        self.data, self.commands, self.stops = healthy(), [], 0
        self.identity = "123:456"

    def snapshot(self):
        return self.data

    def epoch(self):
        return self.identity

    def send(self, goal, **kwargs):
        self.commands.append(goal)

    def stop(self):
        self.stops += 1


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.robot = FakeRobot()
        self.c = a.Controller(
            self.robot, Path(self.tmp.name) / "places.yaml", enabled=True
        )

    def test_readonly_default_never_commands(self):
        self.c.enabled = False
        self.assertEqual(
            self.c.start("navigate", "anything")["status"], "movement_disabled"
        )
        self.assertEqual(self.robot.commands, [])

    def test_save_navigation_and_arrival(self):
        self.c.save("judging")
        self.assertEqual(
            self.c.start("navigate", "judging")["status"], "goal_submitted"
        )
        self.assertEqual(self.robot.commands, [(0.0, 0.0)])
        self.robot.data["nav.state"] = record(state=b"reached", reason=b"")
        self.c.tick()
        self.assertEqual(self.c.mode, "idle")
        self.assertIn("Arrived", self.c.reason)

    def test_stale_pose_rejects_navigation(self):
        self.robot.data["slam.pose"]["timestamp"] -= np.timedelta64(2, "s")
        with self.assertRaisesRegex(RuntimeError, "slam.pose"):
            self.c.start("follow")
        self.assertEqual(self.robot.commands, [])

    def test_vo_lost_rejects_navigation(self):
        self.robot.data["slam.health"]["vo_lost"] = True
        with self.assertRaisesRegex(RuntimeError, "localized"):
            self.c.start("follow")

    def test_degraded_tracking_still_allows_motion(self):
        self.robot.data["slam.health"]["degraded"] = True
        self.robot.data["slam.health"]["stalled"] = True
        self.assertEqual(self.c.start("explore")["status"], "exploring_frontiers")

    def test_unknown_destination_and_no_hallucinated_coordinates(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.c.start("navigate", "elevator")
        self.assertEqual(self.robot.commands, [])

    def test_invalid_and_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            self.c.save("../bad")
        self.c.save("room")
        with self.assertRaises(ValueError):
            self.c.save("room")

    def test_saved_old_frame_rejected(self):
        self.c.save("room")
        self.robot.identity = "other"
        with self.assertRaisesRegex(RuntimeError, "older SLAM"):
            self.c.start("navigate", "room")

    def test_saved_loop_correction_still_navigable(self):
        self.c.save("room")
        self.robot.data["slam.pose"]["pgo_count"] = 1
        self.assertEqual(self.c.start("navigate", "room")["status"], "goal_submitted")

    def test_map_pin_is_drivable(self):
        self.c.save_at("sponsor bay", 0.6, -0.3)
        self.assertEqual(self.c.places()["sponsor bay"]["x"], 0.6)
        self.assertEqual(
            self.c.start("navigate", "sponsor bay")["status"], "goal_submitted"
        )
        np.testing.assert_allclose(self.robot.commands[-1], [0.6, -0.3])

    def test_blocked_goal_rejected(self):
        self.c.save("room")
        self.robot.data["mapping.grid2d"]["grid"][150, 151] = 2
        with self.assertRaisesRegex(RuntimeError, "clear mapped"):
            self.c.start("navigate", "room")
        self.assertEqual(self.robot.commands, [])

    def acquire(self):
        self.c.start("follow")
        for _ in range(3):
            self.c.observe(a.Target((0.0, 1.8), time.time()), self.c.generation)

    def test_follow_uses_waypoint_not_velocity(self):
        self.acquire()
        self.c.tick()
        self.assertEqual(self.c.mode, "follow")
        np.testing.assert_allclose(self.robot.commands[0], [0.0, 0.6])

    def test_lost_person_stops_without_auto_reacquisition(self):
        self.acquire()
        self.c.tick()
        generation = self.c.generation
        self.c.observe(None, generation)
        self.c.observe(a.Target((0.0, 2.0), time.time()), generation)
        self.assertEqual(self.c.mode, "idle")
        self.assertEqual(len(self.robot.commands), 1)

    def test_stale_target_stops(self):
        self.acquire()
        self.c.target.ts -= 2
        self.c.tick()
        self.assertEqual(self.c.mode, "idle")
        self.assertEqual(self.robot.commands, [])

    def test_approaching_person_holds(self):
        self.acquire()
        self.c.target = a.Target((0.0, 1.0), time.time())
        self.c.tick()
        self.assertEqual(self.robot.commands, [])

    def test_pgo_does_not_stop_live_motion(self):
        self.acquire()
        self.robot.data["slam.pose"]["pgo_count"] = 2
        self.c.tick()
        self.assertEqual(self.c.mode, "follow")

    def test_slam_process_restart_stops(self):
        self.acquire()
        self.robot.identity = "other"
        self.c.tick()
        self.assertEqual(self.c.mode, "idle")

    def test_target_jump_stops(self):
        self.acquire()
        self.c.observe(a.Target((2.0, 1.8), time.time()), self.c.generation)
        self.assertEqual(self.c.mode, "idle")

    def test_watchdog_ignores_brief_map_hitch(self):
        self.acquire()
        self.robot.data["mapping.grid2d"]["timestamp"] -= np.timedelta64(3, "s")
        shutdown = a.threading.Event()
        calls = [False, True]
        with patch.object(shutdown, "wait", side_effect=calls):
            a.watchdog(self.c, shutdown, a.queue.Queue())
        self.assertEqual(self.c.mode, "follow")

    def test_watchdog_stops_when_map_stale_for_seconds(self):
        self.acquire()
        self.robot.data["mapping.grid2d"]["timestamp"] -= np.timedelta64(20, "s")
        shutdown = a.threading.Event()
        calls = [False, True]
        with patch.object(shutdown, "wait", side_effect=calls):
            a.watchdog(self.c, shutdown, a.queue.Queue())
        self.assertEqual(self.c.mode, "idle")

    def test_no_ack_stops(self):
        self.c.save("room")
        self.c.start("navigate", "room")
        self.c.sent -= 4
        self.robot.data["nav.state"]["state"] = b"idle"
        self.c.tick()
        self.assertIn("acknowledge", self.c.reason)

    def test_failed_planner_stops(self):
        self.c.save("room")
        self.c.start("navigate", "room")
        self.robot.data["nav.state"] = record(state=b"failed", reason=b"blocked")
        self.c.tick()
        self.assertEqual(self.c.mode, "idle")

    def test_conflicting_writer_never_claims_started(self):
        self.c.save("room")
        with patch.object(
            self.robot, "send", side_effect=RuntimeError("Writer already exists")
        ):
            result = a.dispatch(self.c, "navigate_to", {"name": "room"}, True)
        self.assertIn("error", result)
        self.assertEqual(self.c.mode, "idle")

    def test_missing_detector_reports_error(self):
        self.assertIn("error", a.dispatch(self.c, "follow_user", {}, False))

    def test_no_registered_badge_blocks(self):
        self.c.require_badge = True
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "badge"):
                self.c.start("follow")

    def test_explore_selects_known_free_frontier(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c.start("explore")
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.assertEqual(len(self.robot.commands), 1)
        goal = np.asarray(self.robot.commands[0])
        self.assertTrue(a.clear_goal(self.robot.data["mapping.grid2d"], goal, 0.03))
        # Identity quat faces +Y (camera forward). Do not pick a behind/side frontier.
        self.assertGreater(goal[1], 0.5)

    def test_explore_ignores_frontiers_behind_the_camera(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[140:161, 140:161] = 1  # free disk around the robot at (0, 0)
        grid[140:161, 40:90] = 1  # unmapped-adjacent free only behind (−Y)
        self.c.start("explore")
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.assertEqual(self.robot.commands, [])

    def test_explore_pin_overrides_camera_forward(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[140:161, 140:161] = 1
        grid[140:161, 40:90] = 1
        self.c._explore_path().write_text("x: 0.0\ny: -2.5\n")
        self.c.start("explore")
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.assertEqual(len(self.robot.commands), 1)
        goal = np.asarray(self.robot.commands[0])
        self.assertLess(goal[1], -0.5)

    def test_explore_pin_in_free_space_is_the_goal(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c._explore_path().write_text("x: 0.0\ny: 2.0\n")
        self.c.start("explore")
        self.c.tick()
        np.testing.assert_allclose(self.robot.commands[0], (0.0, 2.0), atol=0.05)

    def test_idle_explore_pin_resumes_explore(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c._explore_path().write_text("x: 0.0\ny: 2.0\n")
        self.assertEqual(self.c.mode, "idle")
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.c.tick()
        self.assertEqual(len(self.robot.commands), 1)

    def test_explore_skips_holes_in_already_mapped_floor(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        grid[148:153, 90:95] = 0  # small unknown speck behind the robot
        self.c.start("explore")
        self.c.tick()
        goal = np.asarray(self.robot.commands[0])
        self.assertGreater(goal[1], 0.5)

    def test_reaching_explore_pin_clears_it(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c._explore_path().write_text("x: 0.0\ny: 2.0\n")
        self.c.start("explore")
        self.c.tick()
        self.robot.data["slam.pose"]["pos"] = np.array([0.0, 2.0, 0.0])
        self.c.tick()
        self.assertFalse(self.c._explore_path().exists())

    def test_explore_waits_when_no_frontier_exists(self):
        self.c.start("explore")
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.assertEqual(self.robot.commands, [])

    def test_explore_survives_slam_hitch(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c.start("explore")
        self.c.tick()
        self.robot.data["slam.health"]["vo_lost"] = True
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.robot.data["slam.health"]["vo_lost"] = False
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")

    def test_explore_keeps_going_during_map_rebuild(self):
        grid = self.robot.data["mapping.grid2d"]["grid"]
        grid[:] = 0
        grid[40:260, 40:260] = 1
        self.c.start("explore")
        self.c.tick()
        self.assertEqual(len(self.robot.commands), 1)
        self.robot.data["mapping.reproject"]["reprojecting"] = True
        self.robot.data["slam.health"]["vo_lost"] = True
        self.robot.data["slam.health"]["localized"] = False
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")
        self.assertIsNotNone(self.c.last_goal)

    def test_explore_ignores_session_limit(self):
        self.c.start("explore")
        self.c.started -= 200
        self.c.tick()
        self.assertEqual(self.c.mode, "explore")

    def test_explore_rejects_motion_when_disabled(self):
        self.c.enabled = False
        result = self.c.start("explore")
        self.assertEqual(result["status"], "movement_disabled")
        self.assertEqual(self.robot.commands, [])


class IOFailureTests(unittest.TestCase):
    class SuppressingReader:
        def __init__(self, *args, **kwargs):
            pass

        def __exit__(self, *args):
            return True

    def test_reader_cleanup_does_not_hide_failure(self):
        with patch.dict(
            "sys.modules", {"bbos": SimpleNamespace(Reader=self.SuppressingReader)}
        ):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                with a.open_reader("test"):
                    raise RuntimeError("failed")

    def test_speaker_conflict_stops_audio_instead_of_silent_thread_death(self):
        def writer(*args, **kwargs):
            raise RuntimeError("speaker owned by another app")

        bbos = SimpleNamespace(
            Reader=self.SuppressingReader,
            Writer=writer,
            Type=lambda name: name,
            Config=lambda name: object(),
        )
        audio = a.Audio()
        shutdown = a.threading.Event()
        with patch.dict("sys.modules", {"bbos": bbos, "soxr": SimpleNamespace()}):
            audio.run(shutdown)
        self.assertTrue(shutdown.is_set())
        self.assertIn("speaker owned", str(audio.errors.get_nowait()))


class GeometryTests(unittest.TestCase):
    def sample(self):
        pose = record(
            pos=np.array([2.0, 3.0, 0.0]), quat=np.array([0.0, 0.0, 0.0, 1.0])
        )
        rect = record(left=np.zeros((384, 512, 3), np.uint8))
        cloud = record(
            num_points=30,
            idx_2d=np.full(30, 150 * 512 + 200),
            points=np.tile([0.1, 1.7, 1.0], (30, 1)),
        )
        return rect, cloud, pose

    def test_base_to_world(self):
        rect, cloud, pose = self.sample()
        target = a.target_from_points([(150, 50, 100, 300)], rect, cloud, pose)
        np.testing.assert_allclose(target.xy, [2.1, 4.7])

    def test_yaw_rotation(self):
        rect, cloud, pose = self.sample()
        pose["quat"] = np.array(
            [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
        )
        target = a.target_from_points([(150, 50, 100, 300)], rect, cloud, pose)
        np.testing.assert_allclose(target.xy, [0.3, 3.1])

    def test_multiple_people_rejected(self):
        self.assertIsNone(a.target_from_points([(0, 0, 100, 200)] * 2, *self.sample()))

    def test_unsynchronized_points_rejected(self):
        rect, cloud, pose = self.sample()
        cloud["timestamp"] -= np.timedelta64(200, "ms")
        self.assertIsNone(
            a.target_from_points([(150, 50, 100, 300)], rect, cloud, pose)
        )

    def test_missing_depth_rejected(self):
        rect, cloud, pose = self.sample()
        cloud["num_points"] = 0
        self.assertIsNone(
            a.target_from_points([(150, 50, 100, 300)], rect, cloud, pose)
        )

    def test_unknown_and_outside_grid_rejected(self):
        grid = healthy()["mapping.grid2d"]
        self.assertFalse(a.clear_goal(grid, [100, 100], 0.03))
        grid["grid"][150, 150] = 0
        self.assertFalse(a.clear_goal(grid, [0, 0], 0.03))


class MapUiTests(unittest.TestCase):
    def test_map_urls_include_localhost(self):
        urls = a.map_urls(8010)
        self.assertIn("http://127.0.0.1:8010", urls)


if __name__ == "__main__":
    unittest.main()
