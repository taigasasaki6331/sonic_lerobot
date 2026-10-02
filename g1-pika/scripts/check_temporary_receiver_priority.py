"""No sudo, scheduling changes, device access, or real /proc inspection."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import temporary_receiver_priority as trial


class Tests(unittest.TestCase):
    def test_target_identity_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); proc=root/'123'; proc.mkdir()
            exe='/tmp/g1-pika-online-Ab12Cd/receive_state'
            (proc/'exe').write_bytes(b'read-only-test-binary')
            (proc/'cmdline').write_bytes(exe.encode()+b'\0--stream\0')
            (proc/'stat').write_text('123 (receive_state) '+' '.join(['S']+['0']*18+['1000']))
            with patch.object(trial,'Path',side_effect=lambda _:root),patch.object(trial.os,'readlink',return_value=exe),\
                 patch.object(trial,'EXPECTED_SHA',hashlib.sha256(b'read-only-test-binary').hexdigest()):
                self.assertEqual(trial.identity(123,os.getuid(),999),(123,1000,exe))
                self.assertIsNone(trial.identity(123,os.getuid()+1,999))
                self.assertIsNone(trial.identity(123,os.getuid(),1001))
                (proc/'cmdline').write_bytes(exe.encode()+b'\0--other\0')
                self.assertIsNone(trial.identity(123,os.getuid(),999))
                (proc/'cmdline').write_bytes(exe.encode()+b'\0--stream\0')
                (proc/'exe').write_bytes(b'not-the-approved-binary')
                self.assertIsNone(trial.identity(123,os.getuid(),999))

    def test_approval_required_before_output_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'not-created.json'
            result=subprocess.run([sys.executable,'-I',trial.__file__,'--output',str(output)],capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,2); self.assertFalse(output.exists())


if __name__=='__main__': unittest.main()
