from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_tcp_reference import TcpReference
from sonic_observation import ObservationBuilder


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = TcpReference(Path(__file__).resolve().parents[1]/'artifacts/models/g1_pika_closed.urdf')
        cls.defaults = ObservationBuilder().defaults

    def action(self): return np.array([0,0,0,1,0,0,0,1,0,.04], dtype=float)

    def test_identity_with_nonzero_waist(self):
        q = self.defaults.copy()
        q[12:15] = [.1, -.05, .08]
        out = self.builder.candidate(self.action(), q)
        self.assertLess(out['reduced_full_fk_max_abs_error'], 1e-8)
        np.testing.assert_allclose(out['q_reference_hardware'], q, atol=1e-7)
        self.assertTrue(out['kinematic_target_within_diagnostic_tolerance'])
        self.assertEqual(out['measured_outside_upstream_ik_limits'], [])
        self.assertFalse(out['hardware_ready'])

    def test_small_action_holds_lower_body(self):
        action = self.action()
        action[0] = .002
        out = self.builder.candidate(action, self.defaults)
        np.testing.assert_array_equal(out['q_reference_hardware'][:15], self.defaults[:15])
        self.assertAlmostEqual(out['gripper_width_m'], .04)
        self.assertFalse(out['gripper_actuated'])
        self.assertTrue(out['kinematic_target_within_diagnostic_tolerance'])

    def test_measurement_not_clipped(self):
        q = self.defaults.copy()
        q[16] = 0.
        saved = q.copy()
        out = self.builder.candidate(self.action(), q)
        np.testing.assert_array_equal(q, saved)
        self.assertIn('left_shoulder_roll_joint', out['measured_outside_upstream_ik_limits'])
        self.assertGreater(out['numerical_seed_projection_max_rad'], 0)

    def test_invalid(self):
        with self.assertRaises(ValueError): self.builder.candidate(self.action(), [0]*28)
        action = self.action()
        action[9] = -.01
        with self.assertRaises(ValueError): self.builder.candidate(action, self.defaults)

    def test_absolute_teacher_pose_and_validation(self):
        pose = self.builder.tcp_pose(self.defaults)
        pose[0, 3] += .005
        saved = pose.copy()
        out = self.builder.candidate_pose(pose, .04, self.defaults)
        np.testing.assert_array_equal(pose, saved)
        np.testing.assert_array_equal(out['right_tcp_target'], pose)
        self.assertTrue(out['kinematic_target_within_diagnostic_tolerance'])
        np.testing.assert_array_equal(out['q_reference_hardware'][:15], self.defaults[:15])
        pose[0, 0] *= 2
        with self.assertRaises(ValueError): self.builder.candidate_pose(pose, .04, self.defaults)
        with self.assertRaises(ValueError): self.builder.candidate_pose(saved, -.01, self.defaults)


if __name__ == '__main__': unittest.main()
