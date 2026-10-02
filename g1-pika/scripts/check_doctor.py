"""Offline tests, no device or network access."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doctor import trt_version


class Tests(unittest.TestCase):
    def test_version(self):
        header = '\n'.join('#define NV_TENSORRT_' + k + ' ' + v for k, v in
                           zip(('MAJOR', 'MINOR', 'PATCH', 'BUILD'), ('10', '13', '0', '35')))
        self.assertEqual(trt_version(header), '192.0.2.2')

    def test_missing(self):
        self.assertIsNone(trt_version('#define NV_TENSORRT_MAJOR 10'))

    def test_symbolic_version(self):
        header = '\n'.join('#define TRT_' + k + '_ENTERPRISE ' + v + '\n#define NV_TENSORRT_' + k + ' TRT_' + k + '_ENTERPRISE'
                           for k, v in zip(('MAJOR', 'MINOR', 'PATCH', 'BUILD'), ('10', '13', '3', '9')))
        self.assertEqual(trt_version(header), '192.0.2.3')

    def test_cycle(self):
        self.assertIsNone(trt_version('#define NV_TENSORRT_MAJOR LOOP\n#define LOOP NV_TENSORRT_MAJOR'))

    def test_comment_not_version(self):
        self.assertIsNone(trt_version('// #define NV_TENSORRT_MAJOR 10'))


if __name__ == '__main__':
    unittest.main()
