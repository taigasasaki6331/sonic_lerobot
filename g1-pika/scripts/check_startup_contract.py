"""Offline tests of saved startup quaternion audit using actual upstream math."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_startup_contract import compare_quaternions, normalized, oracle


def yaw(angle): return [np.cos(angle/2), 0., 0., np.sin(angle/2)]


class Tests(unittest.TestCase):
    def test_heading_alignment_and_orientation_layout(self):
        comparison, values = compare_quaternions([yaw(.8), yaw(.9)], [yaw(.3), yaw(.4)])
        self.assertAlmostEqual(comparison['initial_heading_delta_angle_rad'], .5, places=14)
        np.testing.assert_allclose(values[:, 6:12], [[1.,0.,0.,1.,0.,0.]]*2, atol=2e-15, rtol=0)
        np.testing.assert_allclose(values[0, :6], [np.cos(.5),np.sin(.5),-np.sin(.5),np.cos(.5),0.,0.], atol=2e-15, rtol=0)

    def test_raw_quaternion_normalization_changes_gravity_not_matrix(self):
        body = np.array([[1.001, 0., 0., 0.]])
        reference = np.array([[.999, 0., 0., 0.]])
        snapshot = body.copy(); result, values = compare_quaternions(body, reference)
        self.assertEqual(result['raw_vs_normalized_orientation6_float32_max_abs_difference'], 0.)
        self.assertAlmostEqual(result['raw_vs_normalized_gravity_max_abs_difference'], 2*(1.001**2-1), places=14)
        np.testing.assert_array_equal(body, snapshot)
        np.testing.assert_array_equal(values[:, 12:15], [[0.,0.,-1.]])

    def test_sign_equivalent_quaternions(self):
        result, values = compare_quaternions([yaw(.7), -np.array(yaw(.7))], [yaw(.2), -np.array(yaw(.2))])
        np.testing.assert_allclose(values[0, :15], values[1, :15], atol=2e-15, rtol=0)

    def test_invalid_batches_rejected_without_compiling(self):
        for values in ([[0.,0.,0.,0.]], [[float('nan'),0.,0.,0.]], [[1.,0.,0.]], []):
            with self.assertRaises(ValueError): normalized(values)
        with self.assertRaises(ValueError): oracle([[0.]*16])
        with self.assertRaises(ValueError): compare_quaternions([[1.,0.,0.,0.]], [[1.,0.,0.,0.]]*2)


if __name__ == '__main__': unittest.main()
