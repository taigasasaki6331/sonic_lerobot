import copy
import math
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_measured_stream import MeasuredStream


class Tests(unittest.TestCase):
    def setUp(self):
        self.stream=MeasuredStream('test')
        self.ref=dict(q_hardware=np.tile(self.stream.builder.defaults,(10,1)).tolist(),
            dq_hardware=np.zeros((10,29)).tolist(),quaternion_wxyz=[[1,0,0,0]]*10,
            gripper_width_m=.04,gripper_actuated=False)
        self.publish(0,0.)

    def publish(self,seq,now):
        self.stream.reference_update(session='test',seq=seq,reference=self.ref,issued_at=now,finished_at=now)

    def frames(self,seq):
        return [dict(q=(self.stream.builder.defaults+.001*(seq+i)).tolist()+[0]*6,
                     dq=[.05]*29+[0]*6,quaternion=[math.cos(.001*(seq+i)),0,0,math.sin(.001*(seq+i))],
                     gyroscope=[0,0,.1],tick=seq+i,receive_monotonic_s=10000+.02*(seq+i)) for i in range(10)]

    def observe(self,seq,**kw):
        args=dict(session='test',seq=seq,body_history=self.frames(seq),now=.02*seq,source_age_s=.005)
        args.update(kw); return self.stream.observe(**args)

    def commit(self,seq):
        self.stream.commit(session='test',seq=seq,result=dict(raw_action_isaaclab=[.1]*29,
            q_target_hardware=[0]*29,gripper_width_m=.04,gripper_actuated=False))

    def test_body_changes_without_reintegrating_reference(self):
        first=self.observe(0); self.commit(0); second=self.observe(1)
        self.assertEqual(first['encoder'][4:584],second['encoder'][4:584])
        self.assertNotEqual(first['encoder'][584:644],second['encoder'][584:644])
        self.assertNotEqual(first['decoder_tail'][:610],second['decoder_tail'][:610])
        self.assertTrue(np.allclose(second['decoder_tail'][871:900],[.1]*29))
        self.assertEqual(first['decoder_tail'][610:900],[0.]*290)

    def test_policy_update_only_changes_absolute_reference_once(self):
        self.observe(0); self.commit(0)
        self.ref['q_hardware'][0][15]+=.01; self.publish(1,.02)
        row=self.observe(1); self.commit(1); repeated=self.observe(2)
        self.assertEqual(row['encoder'][4:584],repeated['encoder'][4:584])

    def test_stale_reference_fault_latches(self):
        with self.assertRaises(ValueError): self.observe(0,now=.101)
        with self.assertRaises(RuntimeError): self.observe(0)

    def test_history_required(self):
        with self.assertRaises(ValueError): self.observe(0,body_history=self.frames(0)[:1])

    def test_repeated_body_rejected(self):
        self.observe(0); self.commit(0)
        with self.assertRaises(ValueError): self.observe(1,body_history=self.frames(0))

    def test_source_age_rejected(self):
        with self.assertRaises(ValueError): self.observe(0,source_age_s=.11)

    def test_control_gap_rejected(self):
        self.observe(0); self.commit(0)
        with self.assertRaises(ValueError): self.observe(1,now=.04)

    def test_host_jitter_does_not_relabel_body_cadence(self):
        self.observe(0); self.commit(0)
        self.observe(1,now=.025)
        self.assertEqual(self.stream.last_body_time,self.frames(1)[-1]['receive_monotonic_s'])

    def test_commit_required(self):
        self.observe(0)
        with self.assertRaises(ValueError): self.observe(1)

    def test_reference_update_during_pending_rejected(self):
        self.observe(0)
        with self.assertRaises(ValueError): self.publish(1,.02)

    def test_history_overlap_must_match(self):
        self.observe(0); self.commit(0)
        frames=self.frames(1); frames[0]['q'][0]+=.1
        with self.assertRaises(ValueError): self.observe(1,body_history=frames)

    def test_nonfinite_output_latches(self):
        self.observe(0)
        with self.assertRaises(ValueError):
            self.stream.commit(session='test',seq=0,result=dict(raw_action_isaaclab=[float('nan')]*29))
        self.assertEqual(self.stream.phase,'fault')

    def test_stop_does_not_restart(self):
        self.stream.stop()
        with self.assertRaises(RuntimeError): self.publish(1,.02)

    def test_optional_trajectory_uses_control_time_and_preserves_action_boundary(self):
        self.stream=MeasuredStream('test',joint_interpolation_s=.4)
        self.publish(0,0.)
        first=self.observe(0); self.commit(0)
        order=self.stream.builder.order
        first_q=np.asarray(first['encoder'][4:294]).reshape(10,29)
        np.testing.assert_allclose(first_q[0],np.asarray(self.frames(0)[-1]['q'][:29])[order],atol=1e-7)
        self.assertGreater(np.max(abs(np.asarray(first['encoder'][294:584]))),0)
        second=self.observe(1); self.commit(1)
        before=self.stream.trajectory.sample(.04)
        self.ref['q_hardware']= (np.asarray(self.ref['q_hardware'])+.01).tolist()
        self.publish(1,.04)
        third=self.observe(2)
        for a,b in zip(before,self.stream.trajectory.sample(.04)):
            np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)
        self.assertNotEqual(first['encoder'][4:584],second['encoder'][4:584])
        self.assertEqual(third['gripper_width_m'],.04)
        self.assertFalse(third['gripper_actuated'])

    def test_optional_trajectory_rejects_non_endpoint_and_keeps_deadline(self):
        self.stream=MeasuredStream('test',joint_interpolation_s=.4)
        self.ref['q_hardware'][1][0]+=.01
        with self.assertRaises(ValueError): self.publish(0,0.)
        self.stream=MeasuredStream('test',joint_interpolation_s=.4)
        self.ref['q_hardware'][1][0]-=.01
        self.publish(0,0.)
        with self.assertRaises(ValueError): self.observe(0,now=.101)


if __name__=='__main__': unittest.main()
