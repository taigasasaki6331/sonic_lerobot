"""Compare Python orientation/gravity to actual fixed upstream C++ functions."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_observation import rotation, UPSTREAM


class Tests(unittest.TestCase):
    def test_upstream_math(self):
        include = UPSTREAM/'gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include'
        self.assertEqual(hashlib.sha256((include/'math_utils.hpp').read_bytes()).hexdigest(),
                         'd85de60b9f2c6a4d26b1380264b172b3380200138173998f2a64660310f3c4d5')
        rng = np.random.default_rng(42)
        values = rng.normal(size=(512, 2, 4))
        values /= np.linalg.norm(values, axis=2)[:, :, None]
        with tempfile.TemporaryDirectory(prefix='sonic-math-') as tmp:
            binary = str(Path(tmp)/'oracle')
            subprocess.run(['g++', '-std=c++17', '-O2', '-I'+str(include),
                            str(Path(__file__).with_name('sonic_math_oracle.cpp')), '-o', binary],
                           check=True, timeout=30)
            result = subprocess.run([binary], input='\n'.join(' '.join(map(str, v.ravel())) for v in values),
                                    text=True, capture_output=True, check=True, timeout=10)
        actual = np.array([[float(v) for v in line.split()] for line in result.stdout.splitlines()])
        expected = np.array([np.concatenate(((rotation(b).T@rotation(r))[:, :2].ravel(),
                                            rotation(b).T@[0., 0., -1.])) for b, r in values])
        np.testing.assert_allclose(actual, expected, atol=2e-14, rtol=0)


if __name__ == '__main__': unittest.main()
