"""Controller-output gate and recording sink. No hardware transport exists here.

Bounds/timeouts are SIMULATION test values, not certified robot limits.
A fault suppresses subsequent outputs; it is not a physical emergency stop.
"""
import copy
import math
import numpy as np


class GuardFault(RuntimeError):
    pass


class ControlGuard:
    def __init__(self,names,lower,upper,*,max_state_age=.1,max_tick_gap=.1):
        self.names=tuple(names); self.lower=np.array(lower,dtype=float); self.upper=np.array(upper,dtype=float)
        if (not self.names or len(set(self.names))!=len(self.names)
                or self.lower.shape!=(len(self.names),) or self.upper.shape!=self.lower.shape
                or not np.isfinite([*self.lower,*self.upper,max_state_age,max_tick_gap]).all()
                or np.any(self.lower>=self.upper) or min(max_state_age,max_tick_gap)<=0):
            raise ValueError('Invalid guard configuration')
        self.max_state_age=max_state_age; self.max_tick_gap=max_tick_gap
        self.phase='idle'; self.reason=None; self.owner=None; self.last_time=None; self.last_seq=-1
        self.accepted=0; self.last_frame=None

    def start_simulation(self,owner):
        if self.phase!='idle': self.fail('activation_not_allowed')
        if not owner: self.fail('missing_owner')
        self.owner=owner; self.phase='active'

    def fail(self,reason):
        if self.reason is None: self.reason=reason
        self.phase='fault'
        raise GuardFault(self.reason)

    def stop(self,reason='operator_stop'):
        self.fail(reason)

    def approve(self,*,owner,seq,now,state_time,state_q,names,q,dq,tau,kp,kd,estop=False):
        if self.phase=='fault': raise GuardFault(self.reason)
        if self.phase!='active': self.fail('not_active')
        if owner is not self.owner: self.fail('wrong_owner')
        if estop: self.fail('operator_stop')
        if type(seq) is not int or seq!=self.last_seq+1: self.fail('sequence_error')
        try: valid_clock=all(math.isfinite(t) for t in [now,state_time])
        except (TypeError,ValueError): valid_clock=False
        if not valid_clock: self.fail('invalid_clock')
        if not 0<=now-state_time<=self.max_state_age: self.fail('stale_or_future_state')
        if self.last_time is not None and not 0<now-self.last_time<=self.max_tick_gap:
            self.fail('controller_tick_gap')
        try: valid_names=tuple(names)==self.names
        except TypeError: valid_names=False
        if not valid_names: self.fail('joint_order_mismatch')
        values={}
        for key,value in [('state_q',state_q),('q',q),('dq',dq),('tau',tau),('kp',kp),('kd',kd)]:
            try: a=np.asarray(value,dtype=float)
            except (TypeError,ValueError): self.fail('invalid_'+key)
            if a.shape!=self.lower.shape or not np.isfinite(a).all(): self.fail('invalid_'+key)
            values[key]=a.copy()
        if np.any(values['kp']<0) or np.any(values['kd']<0): self.fail('negative_gain')
        if np.any(values['q']<self.lower) or np.any(values['q']>self.upper): self.fail('joint_target_limit')
        frame={'seq':seq,'time':float(now),'state_time':float(state_time),'joint_names':list(self.names),
               'schema':'abstract_joint_targets_not_Unitree_LowCmd',
               **{k:v.tolist() for k,v in values.items() if k!='state_q'}}
        self.last_frame=copy.deepcopy(frame); self.last_time=now; self.last_seq=seq; self.accepted+=1
        return frame

    def metrics(self):
        return {'phase':self.phase,'fault_reason':self.reason,'accepted_frames':self.accepted,
                'hardware_transport_present':False,'hardware_stop_validated':False,
                'clock_scope':'caller_clock; simulation integration uses simulation time',
                'max_state_age_s':self.max_state_age,'max_tick_gap_s':self.max_tick_gap}


class RecordingSink:
    """Single-writer local record only, incapable of sending to a robot."""
    def __init__(self,guard): self.guard=guard; self.frames=[]
    def append(self,frame):
        if self.guard.phase!='active': raise GuardFault('sink_guard_not_active')
        if frame!=self.guard.last_frame or frame['seq']!=len(self.frames):
            self.guard.fail('sink_unapproved_or_duplicate_frame')
        self.frames.append(copy.deepcopy(frame))
