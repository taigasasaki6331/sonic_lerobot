import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sonic_history_diagnostic import prepare


class Tests(unittest.TestCase):
    def frames(self):
        return [dict(receive_monotonic_s=i*.02, tick=i, q=[i*.001]*35,
                     dq=[0]*35, quaternion=[1, 0, 0, 0], gyroscope=[0]*3)
                for i in range(11)]

    def encode(self, frames):
        return '\n'.join(json.dumps(f) for f in frames).encode()

    def test_real_history_not_repeated(self):
        result = prepare(self.encode(self.frames()))
        self.assertEqual(len(result['frames']), 2)
        row = result['frames'][0]
        self.assertEqual(len(row['encoder']), 1247)
        self.assertEqual(len(row['decoder_tail']), 930)
        self.assertNotEqual(row['decoder_tail'][30], row['decoder_tail'][30+29])
        self.assertEqual(row['decoder_tail'][610:900], [0]*290)

    def test_sparse_rejected(self):
        frames = self.frames()
        for f in frames:
            f['receive_monotonic_s'] *= 10
        with self.assertRaises(ValueError): prepare(self.encode(frames))

    def test_duplicate_tick_rejected(self):
        frames = self.frames()
        frames[4]['tick'] = frames[3]['tick']
        with self.assertRaises(ValueError): prepare(self.encode(frames))

    def test_bad_quaternion_rejected(self):
        frames = self.frames()
        frames[4]['quaternion'] = [0]*4
        with self.assertRaises(ValueError): prepare(self.encode(frames))


if __name__ == '__main__':
    unittest.main()
