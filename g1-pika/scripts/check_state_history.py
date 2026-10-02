import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from state_history import validate_history


class Tests(unittest.TestCase):
    def frames(self):
        return [dict(q=[0]*35, dq=[0]*35, quaternion=[1,0,0,0], gyroscope=[0]*3,
                     tick=i, receive_monotonic_s=i*.02) for i in range(10)]

    def test_good(self):
        frames = self.frames()
        saved = copy.deepcopy(frames)
        self.assertEqual(validate_history(frames), saved)
        self.assertEqual(frames, saved)

    def test_count(self):
        with self.assertRaises(ValueError): validate_history(self.frames()[:9])

    def test_cadence_and_tick(self):
        for field, value in [('receive_monotonic_s', .3), ('tick', 3)]:
            frames = self.frames()
            frames[4][field] = value
            with self.assertRaises(ValueError): validate_history(frames)

    def test_values(self):
        for field, value in [('q', [0]*34), ('quaternion', [0]*4), ('gyroscope', [float('nan')]*3)]:
            frames = self.frames()
            frames[3][field] = value
            with self.assertRaises(ValueError): validate_history(frames)

    def test_tick_wrap_and_reversal(self):
        frames=self.frames()
        for i,frame in enumerate(frames): frame['tick']=(0xffffffff-4+i)&0xffffffff
        validate_history(frames)
        frames=self.frames(); frames[4]['tick']=2
        with self.assertRaises(ValueError): validate_history(frames)

    def test_boolean_is_not_measurement(self):
        for field,value in [('tick',True),('receive_monotonic_s',True),('q',[True]*35)]:
            frames=self.frames(); frames[0][field]=value
            with self.assertRaises(ValueError): validate_history(frames)


if __name__ == '__main__': unittest.main()
