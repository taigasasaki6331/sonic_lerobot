"""Offline tests for the explicit simulator state boundary."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wbc_state import WbcState


class Tests(unittest.TestCase):
    def state(self):
        return WbcState(1., tuple('joint_' + str(i) for i in range(29)),
                        np.zeros(29), np.zeros(29), np.array([0, 0, .74, 1, 0, 0, 0]), np.zeros(6))

    def test_copy(self):
        s = self.state()
        q = s.q
        s.validate(s.names)
        q[0] = 1
        self.assertEqual(s.q[0], 0)

    def test_roundtrip(self):
        s = self.state().validate(self.state().names)
        packet = s.packet()
        self.assertEqual(packet.pop('source'), 'simulation_not_G1')
        decoded = WbcState(**packet).validate(s.names)
        np.testing.assert_array_equal(decoded.q, s.q)

    def test_invalid_vectors(self):
        for key, value in [('q', np.zeros(35)), ('dq', [float('nan')] * 29),
                           ('base_pose', [0] * 7), ('base_velocity', [float('inf')] * 6)]:
            with self.subTest(key=key):
                s = self.state()
                setattr(s, key, value)
                with self.assertRaises(ValueError): s.validate(self.state().names)

    def test_order(self):
        s = self.state()
        with self.assertRaises(ValueError): s.validate(s.names[::-1])

    def test_duplicate_names(self):
        s = self.state()
        s.names = ('same',) * 29
        with self.assertRaises(ValueError): s.validate(s.names)

    def test_clock(self):
        for stamp in [-1, float('nan'), float('inf')]:
            s = self.state()
            s.time = stamp
            with self.assertRaises(ValueError): s.validate(s.names)

    def test_unknown_hardware_convention(self):
        s = self.state()
        s.convention = 'unitree_lowstate'
        with self.assertRaises(ValueError): s.validate(s.names)


if __name__ == '__main__': unittest.main()
