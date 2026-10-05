"""Full record-only local worker/native owner rehearsals; no sockets or SDK IO."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_body_runtime import ROOT,build,rehearse_direct

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=ROOT/'artifacts/body-runtime'; base.mkdir(parents=True,exist_ok=True)
        cls.directory=Path(tempfile.mkdtemp(prefix='cloud-check-',dir=base))
        cls.source=build(cls.directory)

    def scenario(self,name):
        directory=self.directory/name; directory.mkdir()
        report=rehearse_direct(directory,self.source,5,name)
        self.assertTrue(report['passed'],str(directory/'outputs/report.json')+': '+str(report.get('error')))
        for key in ('robot_commands_sent','physical_stop_confirmed','hardware_transport_linked'):
            self.assertFalse(report[key])
        diagnostics=report['native_runtime']['writer_timing_diagnostics']
        self.assertTrue(diagnostics['available'])
        self.assertGreaterEqual(diagnostics['max_observed_gap_s'],report['native_runtime']['max_start_gap_s'])
        self.assertGreaterEqual(diagnostics['max_admission_delay_s'],0.)
        return report

    def test_normal(self): self.scenario('normal')
    def test_body_expiry(self): self.scenario('body_expiry')
    def test_recovery(self): self.assertTrue(self.scenario('recovery')['rearm_rejected_after_recovery'])

if __name__=='__main__': unittest.main()
