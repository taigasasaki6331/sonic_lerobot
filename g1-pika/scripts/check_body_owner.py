"""SDK-free complete owner lifecycle and injected transport failures."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

class Tests(unittest.TestCase):
    def test_owner_start_stop_recovery_and_failures(self):
        source=Path(__file__).with_suffix('.cpp')
        with tempfile.TemporaryDirectory(prefix='g1-owner-') as tmp:
            binary=Path(tmp)/'owner'
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread',str(source),'-o',str(binary)],
                           check=True,timeout=30)
            report=json.loads(subprocess.check_output([str(binary)],timeout=5))
        self.assertEqual(report['fake_owner_checks'],18)
        self.assertFalse(report['robot_commands_sent']); self.assertFalse(report['physical_stop_confirmed'])

if __name__=='__main__': unittest.main()
