"""Local LowState/watchdog fixtures; no DDS, sockets, devices or physics."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_body_monitor import LocalBodyMonitor
from sonic_body_bridge import LocalSonicBodyBridge,envelope
from check_body_lifecycle import body,profile
import check_body_lifecycle as fixtures
from body_lifecycle import BodyLifecycle
from check_sonic_body_bridge import result


def local(tick=1,stamp=1.):
    frame=body(tick); frame.update(receive_monotonic_s=stamp,mode_machine=3,mode_pr=0)
    return frame


class Tests(unittest.TestCase):
    def test_strict_CRC_rejects_unchecked_or_invalid_status_and_latches(self):
        for mutate in (lambda f:f.update(crc_verified=False),lambda f:f.update(crc_received=True),
                lambda f:f.update(crc_calculated=8),lambda f:f.pop('crc_received'),
                lambda f:f.update(crc_native_size_bytes=2092.0)):
            frame=local(); frame.update(crc_verified=True,crc_received=7,crc_calculated=7,crc_native_size_bytes=2092)
            mutate(frame); monitor=LocalBodyMonitor(require_crc=True)
            with self.assertRaises(ValueError): monitor.ingest_local(frame,now=1.)
            valid=local(2,1.02); valid.update(crc_verified=True,crc_received=7,crc_calculated=7,crc_native_size_bytes=2092)
            with self.assertRaises(ValueError): monitor.ingest_local(valid,now=1.02)
    def test_strict_CRC_evidence_still_does_not_mean_hardware_ready(self):
        frame=local(); frame.update(crc_verified=True,crc_received=7,crc_calculated=7,crc_native_size_bytes=2092)
        monitor=LocalBodyMonitor(require_crc=True); monitor.ingest_local(frame,now=1.)
        self.assertTrue(monitor.status()['crc_verified']); self.assertTrue(monitor.status()['crc_verification_required'])
        self.assertFalse(monitor.status()['hardware_ready'])
    def test_copy_and_reported_mode_is_not_readiness(self):
        m=LocalBodyMonitor(); f=local(); m.ingest_local(f,now=1.001); f['q'][0]=999
        stored,age=m.snapshot(now=1.01); self.assertEqual(stored['q'][0],0); self.assertAlmostEqual(age,.01)
        self.assertEqual(m.status()['mode_machine'],3); self.assertFalse(m.status()['hardware_ready'])

    def test_duplicate_does_not_refresh_and_fault_latches(self):
        m=LocalBodyMonitor(); m.ingest_local(local(),now=1.)
        self.assertFalse(m.ingest_local(local(stamp=1.09),now=1.09))
        with self.assertRaises(ValueError): m.snapshot(now=1.101)
        with self.assertRaises(ValueError): m.ingest_local(local(2,1.102),now=1.102)

    def test_wraparound_valid_reverse_invalid(self):
        m=LocalBodyMonitor(); m.ingest_local(local(0xffffffff),now=1.)
        m.ingest_local(local(0,1.02),now=1.02)
        with self.assertRaises(ValueError): m.ingest_local(local(0xffffffff,1.04),now=1.04)

    def test_sensor_mode_clock_and_machine_errors(self):
        mutations=(lambda f:f.update(mode_machine=True),lambda f:f.update(mode_pr=1),
            lambda f:f.update(receive_monotonic_s=1e9),lambda f:f.update(crc_verified=None),
            lambda f:f['q'].__setitem__(0,float('nan')))
        for mutate in mutations:
            m=LocalBodyMonitor(); f=local(); mutate(f)
            with self.assertRaises(ValueError): m.ingest_local(f,now=1.)
        m=LocalBodyMonitor(); m.ingest_local(local(),now=1.)
        f=local(2,1.02); f['mode_machine']=4
        with self.assertRaises(ValueError): m.ingest_local(f,now=1.02)

    def test_changed_duplicate_and_reversed_clock(self):
        for changed in (True,False):
            m=LocalBodyMonitor(); m.ingest_local(local(),now=1.)
            f=local(stamp=1.02)
            if changed: f['dq'][0]=.01
            with self.assertRaises(ValueError): m.ingest_local(f,now=1.02 if changed else .9)

    def test_GPU_carried_body_never_refreshes_local_liveness(self):
        c=BodyLifecycle('s',profile()); b=LocalSonicBodyBridge(c)
        b.observe_local(local(),now=1.)
        carried=body(1,q=.5)
        m=envelope('s',0,carried,result(),source_age_s=0.,joint_names=profile()['names'])
        reply=b.consume(m,now=1.02)
        self.assertEqual(reply['decision'],'gated_initial_pose_not_ready')
        self.assertEqual(c.body['q'][0],0); self.assertEqual(c.body_received,1.)
        m=envelope('s',1,carried,result(1),source_age_s=0.,joint_names=profile()['names'])
        with self.assertRaises(ValueError): b.consume(m,now=1.101)
        self.assertIsNone(c.target); self.assertEqual(c.phase,'stop_required')

    def test_no_network_needed_to_latch_local_watchdog(self):
        c=BodyLifecycle('s',profile()); b=LocalSonicBodyBridge(c)
        b.observe_local(local(),now=1.)
        with self.assertRaises(ValueError): b.poll(now=1.101)
        self.assertEqual(c.phase,'stop_required')
        self.assertFalse(b.status()['physical_writer_implemented'])

    def test_future_GPU_tick_rejected(self):
        c=BodyLifecycle('s',profile()); b=LocalSonicBodyBridge(c); b.observe_local(local(),now=1.)
        m=envelope('s',0,body(2),result(),source_age_s=0.,joint_names=profile()['names'])
        with self.assertRaises(ValueError): b.consume(m,now=1.01)

    def test_fixture_ready_uses_local_body_and_exact_SONIC_target(self):
        fixture=fixtures.Tests(); fixture.setUp(); fixture.ready()
        c=fixture.c; b=LocalSonicBodyBridge(c); b.observe_local(local(9,.18),now=.18)
        m=envelope('session',0,body(8,q=.5),result(),source_age_s=0.,joint_names=profile()['names'])
        self.assertEqual(b.consume(m,now=.18)['decision'],'accepted_abstract_target_NOT_sent')
        self.assertEqual(c.body['tick'],9); self.assertEqual(c.body['q'][0],0)
        self.assertEqual(c.target,[.01]*29); self.assertFalse(c.status()['physical_ownership_confirmed'])


if __name__=='__main__': unittest.main()
