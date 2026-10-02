"""Stateful measured-body observation assembly; no sensors or motor transport.

Policy references are absolute. Updating body state never reapplies h1 actions.
Time values supplied to this class MUST use one coordinator's monotonic clock.
This remains record-only: computed prior actions are not executed actions.
"""
import copy
import math
import numpy as np
from sonic_observation import ObservationBuilder, array
from state_history import validate_history
from sonic_joint_trajectory import JointTrajectory


class MeasuredStream:
    def __init__(self, session, max_reference_age_s=.1, joint_interpolation_s=None):
        if not isinstance(session,str) or not session: raise ValueError('Session required')
        if not math.isfinite(max_reference_age_s) or not 0<max_reference_age_s<=1:
            raise ValueError('Reference deadline required')
        self.session=session; self.max_age=max_reference_age_s
        self.builder=ObservationBuilder(); self.phase='running'
        self.reference=None; self.policy_seq=-1; self.control_seq=0
        self.history=np.zeros((10,29)); self.pending=None
        self.last_body_time=None; self.last_body_tick=None; self.last_now=None
        self.last_body_history=None
        if joint_interpolation_s is not None and (type(joint_interpolation_s) not in (int,float)
                or not math.isfinite(joint_interpolation_s) or not .02<=joint_interpolation_s<=5):
            raise ValueError('Invalid diagnostic joint interpolation duration')
        self.joint_interpolation_s=joint_interpolation_s
        self.trajectory=None; self.trajectory_policy_seq=-1

    def fail(self, reason):
        self.phase='fault'; self.pending=None
        raise ValueError(reason)

    def check(self, session):
        if self.phase!='running': raise RuntimeError('Measured stream is '+self.phase)
        if session!=self.session: self.fail('Measured stream session mismatch')

    def reference_update(self, *, session, seq, reference, issued_at, finished_at):
        self.check(session)
        try:
            if self.pending is not None: self.fail('Reference update during pending inference')
            if type(seq) is not int or seq!=self.policy_seq+1: self.fail('Policy sequence mismatch')
            if not all(math.isfinite(v) for v in (issued_at,finished_at)) or not 0<=finished_at-issued_at<=self.max_age:
                self.fail('Reference computation deadline')
            if self.reference is not None and issued_at<self.reference['issued_at']:
                self.fail('Reference clock moved backwards')
            q=array(reference['q_hardware'],(10,29))
            dq=array(reference['dq_hardware'],(10,29))
            if self.joint_interpolation_s is not None and (not np.array_equal(q,np.tile(q[0],(10,1)))
                    or np.any(dq!=0)):
                self.fail('Joint interpolation requires held IK endpoint input')
            quat=array(reference['quaternion_wxyz'],(10,4))
            if not np.allclose(np.linalg.norm(quat,axis=1),1,atol=1e-4,rtol=0):
                self.fail('Reference quaternion norm')
            width=reference['gripper_width_m']
            if type(width) not in (int,float) or not math.isfinite(width) or not 0<=width<=.1:
                self.fail('Reference width')
            if reference.get('gripper_actuated') is not False: self.fail('Reference must not actuate gripper')
            self.reference=dict(q=q.copy(),dq=dq.copy(),quat=quat.copy(),width=width,
                                issued_at=issued_at,finished_at=finished_at)
            self.policy_seq=seq
        except Exception:
            self.phase='fault'; raise

    def observe(self, *, session, seq, body_history, now, source_age_s):
        self.check(session)
        try:
            if type(seq) is not int or seq!=self.control_seq or self.pending is not None:
                self.fail('Control sequence or uncommitted output')
            if self.reference is None: self.fail('No absolute reference')
            ref=self.reference
            if not math.isfinite(now) or not ref['finished_at']<=now or not 0<=now-ref['issued_at']<=self.max_age:
                self.fail('Stale reference')
            # Source sample cadence and coordinator scheduling are distinct clocks.
            # Keep the source 20ms+/-2ms/overlap checks below. The host may jitter,
            # but must not reverse time or stall for two nominal control periods.
            if self.last_now is not None and not 0<now-self.last_now<.04:
                self.fail('Control clock reversed or missed two nominal periods')
            if type(source_age_s) not in (int,float) or not math.isfinite(source_age_s) or not 0<=source_age_s<=.1:
                self.fail('Stale measured body input')
            frames=validate_history(body_history); newest=frames[-1]
            # These differences are within the source clock; never subtract source from GPU clocks.
            stamp=newest['receive_monotonic_s']
            if self.last_body_time is not None and (not .018<=stamp-self.last_body_time<=.022 or
                    not 0<((newest['tick']-self.last_body_tick)&0xffffffff)<0x80000000):
                self.fail('Repeated or skipped measured body frame')
            if self.last_body_history is not None and self.last_body_history[1:]!=frames[:-1]:
                self.fail('Consecutive body windows have inconsistent overlapping samples')
            quat=np.asarray([f['quaternion'] for f in frames],dtype=float)
            quat/=np.linalg.norm(quat,axis=1)[:,None]
            reference_q,reference_dq=ref['q'],ref['dq']
            if self.joint_interpolation_s is not None:
                if self.trajectory is None:
                    self.trajectory=JointTrajectory(newest['q'][:29],newest['dq'][:29],
                        now=now,duration_s=self.joint_interpolation_s)
                if self.trajectory_policy_seq!=self.policy_seq:
                    self.trajectory.update(ref['q'][0],now=now)
                    self.trajectory_policy_seq=self.policy_seq
                reference_q,reference_dq,_=self.trajectory.window(now=now)
            row=dict(seq=seq,measured_q=newest['q'][:29],gripper_width_m=ref['width'],gripper_actuated=False,
                     encoder=self.builder.encoder(reference_q,reference_dq,ref['quat'],quat[-1]).tolist(),
                     decoder_tail=self.builder.decoder_tail([f['q'][:29] for f in frames],
                         [f['dq'][:29] for f in frames],[f['gyroscope'] for f in frames],quat,self.history).tolist())
            self.pending=seq; self.last_body_time=stamp; self.last_body_tick=newest['tick']; self.last_now=now
            self.last_body_history=copy.deepcopy(frames)
            return copy.deepcopy(row)
        except Exception:
            self.phase='fault'; self.pending=None; raise

    def commit(self, *, session, seq, result):
        self.check(session)
        try:
            if type(seq) is not int or seq!=self.pending: self.fail('Output commit sequence mismatch')
            raw=array(result['raw_action_isaaclab'],(29,))
            array(result['q_target_hardware'],(29,))
            if result.get('gripper_actuated') is not False or result.get('gripper_width_m')!=self.reference['width']:
                self.fail('Output width channel mismatch')
            self.history=np.concatenate((self.history[1:],raw[None,:]),axis=0)
            self.pending=None; self.control_seq+=1
        except Exception:
            self.phase='fault'; self.pending=None; raise

    def stop(self):
        if self.phase!='fault': self.phase='stopped'
        self.pending=None; self.reference=None
        self.trajectory=None
