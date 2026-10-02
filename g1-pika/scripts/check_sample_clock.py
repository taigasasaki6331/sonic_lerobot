"""Compile/run receive-only sampling-clock assertions without DDS or devices."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class Tests(unittest.TestCase):
    def test_fixed_phase_and_no_fabricated_slots(self):
        source=Path(__file__).resolve().parent/'state_receiver/check_sample_clock.c'
        with tempfile.TemporaryDirectory(prefix='g1-sample-clock-') as folder:
            binary=str(Path(folder)/'check')
            subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(source),'-lm','-o',binary],check=True,timeout=15)
            subprocess.run([binary],check=True,timeout=2)


if __name__=='__main__': unittest.main()
