"""Offline action delivery checks for the split-controller simulation."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_wbc import DeliveredBridge


class Tests(unittest.TestCase):
    def bridge(self): return DeliveredBridge({'ready': True}, 2)
    def response(self, seq=0):
        return {'seq': seq, 'timestamp': seq / 30, 'action': [0, 0, 0, 1, 0, 0, 0, 1, 0, .04]}
    def test_hold_without_delivery(self):
        bridge = self.bridge()
        np.testing.assert_array_equal(bridge.target(20, np.eye(4), np.eye(4)), np.eye(4))
        self.assertEqual(len(bridge.bridge.events), 0)
    def test_once_only(self):
        bridge = self.bridge()
        bridge.response = self.response()
        for now in [2, 2.02, 2.04]: bridge.target(now, np.eye(4), np.eye(4))
        self.assertEqual(len(bridge.bridge.events), 1)
    def test_sequence_rejection(self):
        bridge = self.bridge()
        bridge.response = self.response(1)
        with self.assertRaises(ValueError): bridge.target(2, np.eye(4), np.eye(4))
        self.assertEqual(len(bridge.bridge.events), 0)
    def test_bad_action(self):
        bridge = self.bridge()
        bridge.response = self.response()
        bridge.response['action'][9] = -1
        with self.assertRaises(ValueError): bridge.target(2, np.eye(4), np.eye(4))
    def test_delayed_sequence_preserves_order(self):
        bridge = self.bridge()
        for seq, now in [(0, 2), (1, 8)]:
            bridge.response = self.response(seq)
            bridge.target(now, np.eye(4), np.eye(4))
        self.assertEqual([r['seq'] for r in bridge.bridge.events], [0, 1])
        self.assertEqual(bridge.bridge.events[-1]['sim_time'], 8)


if __name__ == '__main__': unittest.main()
