"""Deterministic contract tests; no simulation, network or hardware."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teacher_trajectory import TeacherTrajectory, decode_rotation, integrate_action
from dataset_contract import relative_observation, inspect_episode


class TeacherTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((Path(__file__).resolve().parents[1] / "assets/trajectories/episode0.json").read_text())
        self.teacher = TeacherTrajectory(self.payload)

    def test_layouts(self):
        rotation = Rotation.from_euler("xyz", [0.3, -0.5, 0.7]).as_matrix()
        for layout, values in (("rows", rotation[:, :2].reshape(-1)),
                               ("columns", rotation[:, :2].T.reshape(-1))):
            np.testing.assert_allclose(decode_rotation(values, layout), rotation, atol=1e-12)
        with self.assertRaises(ValueError):
            decode_rotation([1, 0, 0, 0, 1, 0], "rows")

    def test_local_noncommuting_composition(self):
        pose = np.eye(4)
        pose[:3, :3] = Rotation.from_euler("x", 0.7).as_matrix()
        pose[:3, 3] = [0.2, 0.3, 0.4]
        delta = np.eye(4)
        delta[:3, :3] = Rotation.from_euler("z", 0.4).as_matrix()
        delta[:3, 3] = [0.01, -0.02, 0.03]
        alignment = np.asarray(self.payload["tracker_to_tcp_rotation"])
        transform = np.eye(4)
        transform[:3, :3] = alignment
        action = np.r_[delta[:3, 3], delta[:3, :2].T.reshape(-1), 0.02]
        actual = integrate_action(pose, action, alignment, "columns")
        np.testing.assert_allclose(actual, pose @ transform @ delta @ transform.T, atol=1e-12)

    def test_resampling_is_stateless_and_complete(self):
        origin = np.eye(4)
        origin[:3, :3] = Rotation.from_euler("xyz", [0.2, 0.3, -0.1]).as_matrix()
        origin[:3, 3] = [0.3, -0.2, 0.1]
        np.testing.assert_allclose(self.teacher.target(0, origin), origin, atol=1e-12)
        for hz in (30, 50, 200):
            for t in np.arange(0, self.teacher.required_seconds, 1 / hz):
                self.teacher.target(t, origin)
            np.testing.assert_allclose(self.teacher.target(self.teacher.required_seconds, origin),
                                       origin @ self.teacher.poses[-1], atol=1e-12)
        np.testing.assert_allclose(self.teacher.target(4, origin), self.teacher.target(4, origin))
        slow = TeacherTrajectory(self.payload, 0.5)
        np.testing.assert_allclose(slow.target(6, origin), self.teacher.target(4, origin), atol=1e-12)
        self.assertFalse(self.teacher.metrics(3)["teacher_completed"])
        self.assertTrue(self.teacher.metrics(self.teacher.required_seconds)["teacher_completed"])

    def test_reject_invalid(self):
        self.payload["frames"][0]["action"][0] = float("nan")
        with self.assertRaises(ValueError):
            TeacherTrajectory(self.payload)

    def test_relative_state_is_not_an_absolute_pose(self):
        rows = [
            {"frame_index": 0, "observation.state": relative_observation(0.02),
             "action": [0.01, 0, 0, 1, 0, 0, 0, 1, 0, 0.03]},
            {"frame_index": 1, "observation.state": relative_observation(0.03),
             "action": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0.03]},
        ]
        report = inspect_episode(rows, "columns")
        self.assertTrue(report["state_contract_passed"])
        self.assertEqual(report["gripper_h1_mismatch_count"], 0)
        self.assertFalse(report["absolute_pose_trajectory_verified"])
        self.assertNotIn("local_translation_residual_max_m", report)
        rows[0]["action"][9] = 0.04
        report = inspect_episode(rows, "columns")
        self.assertEqual(report["gripper_h1_mismatch_frames"], [0])
        rows[0]["observation.state"][0] = 0.01
        self.assertFalse(inspect_episode(rows, "columns")["state_contract_passed"])

    def test_relative_observation_layout(self):
        for layout in ("columns", "rows"):
            state = relative_observation(0.04, layout)
            np.testing.assert_allclose(decode_rotation(state[3:9], layout), np.eye(3))
        with self.assertRaises(ValueError):
            relative_observation(float("nan"))


if __name__ == "__main__":
    unittest.main()
