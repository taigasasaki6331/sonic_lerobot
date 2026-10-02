"""Smoke checks for native command -> MuJoCo actuation boundary; no SDK IO."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from lowcmd_preview import export_data_headers,crc_words
from sim_body_gateway import SimBodyGateway


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='g1-sim-body-gateway-')
        directory=Path(cls.tmp.name); export_data_headers(directory); cls.library=directory/'sim.so'
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
            '-I'+str(directory),str(Path(__file__).with_name('sim_body_gateway.cpp')),'-o',str(cls.library)],check=True,timeout=20)
        cls.profile={name:[value]*29 for name,value in [('lower',-2),('upper',2),('kp',10),('kd',1),('defaults',0)]}

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_native_lowcmd_float32_fields_drive_torque_and_end_to_end_stop(self):
        gateway=SimBodyGateway(self.library,self.profile)
        try:
            target=[.123456789]*29; gateway.reference(0,target)
            torque=gateway.tick(0,[.02]*29,[.03]*29)
            expected=10*(float(np.float32(target[0]))-.02)-.03
            np.testing.assert_allclose(torque,[expected]*29,atol=1e-12)
            data=bytes.fromhex(gateway.samples[0]['native_memory_hex'])
            self.assertEqual(struct.unpack_from('<I',data,1000)[0],crc_words(data[:1000]))
            self.assertEqual(data[4+29*28:1000],bytes(6*28+16))
            gateway.tick(.002,[.02]*29,[.03]*29); gateway.stop(); report=gateway.report()
            self.assertEqual((report['writer_ticks'],report['memory_publications']),(2,3))
            self.assertEqual((report['simulated_releases'],report['simulated_restores']),(1,1))
            self.assertTrue(report['stop_completed']); self.assertFalse(report['physical_stop_confirmed'])
            self.assertFalse(report['hardware_transport_linked']); self.assertFalse(report['robot_commands_sent'])
        finally: gateway.close()

    def test_limits_expiry_and_physical_gate_are_not_claimed_as_passed(self):
        gateway=SimBodyGateway(self.library,self.profile)
        try:
            gateway.reference(0,[0]*29); gateway.tick(0,[0]*29,[0]*29)
            gateway.reference(.02,[.3]*29)
            self.assertFalse(gateway.report()['physical_step_gate_passed'])
            # This is a simulator backend, not a relaxation of hardware gates.
            with self.assertRaises(ValueError): gateway.tick(.2,[0]*29,[0]*29)
            gateway.stop()
        finally: gateway.close()


if __name__=='__main__': unittest.main()
