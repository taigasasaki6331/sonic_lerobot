import unittest
from read_gripper_state import Frames, position, plausible_position


class ParserTests(unittest.TestCase):
    def test_split(self):
        p = Frames()
        self.assertEqual(p.feed(b'noise {"motor":{"Pos'), [])
        self.assertEqual(position(p.feed(b'ition":1.2}}')[0]), 1.2)

    def test_concatenated_and_quoted(self):
        p = Frames()
        self.assertEqual(len(p.feed(b'{"text":"}\\\"{"}{"motor":{"Position":0}}')), 2)

    def test_invalid_nonfinite(self):
        p = Frames()
        self.assertEqual(p.feed(b'{"motor":{"Position":NaN}}'), [])
        self.assertEqual(p.invalid, 1)

    def test_oversize_recovery(self):
        p = Frames()
        p.feed(b'{' + b'x'*5000)
        self.assertEqual(p.feed(b'{"ok":1}'), [{'ok': 1}])
        self.assertEqual(p.invalid, 1)

    def test_position_validation(self):
        for f in ({}, {'motor':None}, {'motor':{'Position':True}}, {'motor':{'Position':'1'}}):
            self.assertIsNone(position(f))

    def test_observed_outlier(self):
        self.assertTrue(plausible_position(-.0067))
        self.assertFalse(plausible_position(2.0))
        self.assertFalse(plausible_position(None))


if __name__ == '__main__':
    unittest.main()
