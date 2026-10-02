import math
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gripper_observation import legacy_width


class GeometryTests(unittest.TestCase):
    def test_closed(self):
        self.assertEqual(legacy_width(0)['width_m'], 0)
        self.assertFalse(legacy_width(0)['legacy_range_error'])

    def test_legacy_clipping(self):
        self.assertEqual(legacy_width(-.0067)['width_m'], 0)
        self.assertTrue(legacy_width(-.0067)['legacy_range_error'])
        self.assertEqual(legacy_width(2)['width_m'], legacy_width(1.67)['width_m'])
        self.assertTrue(legacy_width(2)['legacy_range_error'])

    def test_monotonic(self):
        widths=[legacy_width(x/100)['width_m'] for x in range(168)]
        self.assertEqual(widths, sorted(widths))
        self.assertTrue(.09 < widths[-1] < .1)

    def test_bad(self):
        for value in (True, None, float('nan'), float('inf')):
            with self.assertRaises(ValueError): legacy_width(value)


if __name__ == '__main__': unittest.main()
