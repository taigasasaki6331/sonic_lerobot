"""Build and run native writer against fake transport ONLY; no SDK linking."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest


def compile_and_run(binary):
    source=Path(__file__).resolve().parent
    subprocess.run(['g++','-std=c++17','-pthread','-O2','-Wall','-Wextra','-Werror',
        str(source/'check_body_writer.cpp'),'-o',str(binary)],check=True,timeout=20)
    report=json.loads(subprocess.check_output([str(binary)],timeout=5))
    if (report.get('writer_checks')!=27 or report.get('robot_commands_sent') is not False or
            report.get('physical_stop_confirmed') is not False or
            report.get('scope')!='SDK_free_fake_transport_artificial_inputs'):
        raise ValueError('Unexpected fake writer report')
    return report


class Tests(unittest.TestCase):
    def test_native_deadlines_admission_watchdogs_threads_and_fake_adapter(self):
        with tempfile.TemporaryDirectory(prefix='g1-body-writer-') as tmp:
            binary=Path(tmp)/'test'
            report=compile_and_run(binary)
        self.assertEqual(report['writer_checks'],27)
        self.assertFalse(report['robot_commands_sent'])
        self.assertFalse(report['physical_stop_confirmed'])
        self.assertEqual(len(report['threaded_runs']),5)
        self.assertEqual(report['threaded_runs'][-1]['reason'],'writer_sink_blocked_past_deadline')
        self.assertGreaterEqual(report['threaded_runs'][-1]['max_sink_call_s'],.025)


if __name__=='__main__': unittest.main()
