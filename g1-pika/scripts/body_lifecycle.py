"""Pure, RECORD-ONLY body lifecycle and local watchdog. No SDK/network/device IO.

Acknowledgements are explicitly diagnostic, not evidence of physical ownership,
stop or return. Commands are abstract records, never Unitree LowCmd packets.
Thresholds and initial trajectories are unvalidated design/test settings.
"""
import copy
from collections import deque
import math
from pathlib import Path
import numpy as np
from sonic_joint_trajectory import JointTrajectory
from sonic_startup_ablation import vector
from sonic_process import strict_message
from state_history import validate_state

ACK_KIND = 'diagnostic_ack_not_physical_confirmation'
DEFAULT = Path(__file__).resolve().parents[1]/'config/body-lifecycle.json'
SETTING_NAMES = {'init_duration_s','settle_duration_s','settle_position_tolerance_rad',
    'settle_velocity_tolerance_rad_s','max_body_age_s','max_ownership_ack_age_s',
    'max_takeover_wait_s','max_command_age_s','max_target_step_rad','max_writer_gap_s','control_period_s','writer_period_s'}
ACTIVE = {'ownership_pending','owned','initializing','settling','ready','tracking'}
OWNED = ACTIVE - {'ownership_pending'}


def settings(value):
    if (set(value) != SETTING_NAMES | {'schema_version','mode','hardware_output_enabled'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['mode'] != 'record_only' or value['hardware_output_enabled'] is not False):
        raise ValueError('Only record-only lifecycle supported')
    for key in SETTING_NAMES:
        v = value[key]
        if type(v) not in (float,int) or not math.isfinite(v) or not 0 < v <= 5:
            raise ValueError('Invalid lifecycle test setting: '+key)
    if value['writer_period_s'] != .002 or value['control_period_s'] != .02 or value['init_duration_s'] < .02:
        raise ValueError('Require diagnostic 500Hz writer and supported trajectory duration')
    return copy.deepcopy(value)


class LifecycleFault(RuntimeError): pass


class BodyLifecycle:
    def __init__(self, session, profile, config=None):
        if not isinstance(session,str) or not session or len(session)>128: raise ValueError('Session required')
        self.session = session; self.config = settings(config if config is not None else strict_message(DEFAULT.read_bytes()))
        for key in ('defaults','kp','kd','lower','upper','velocity'): vector(profile[key],29)
        names = profile['names']
        if (len(names)!=29 or len(set(names))!=29 or any(not isinstance(v,str) or not v for v in names)
                or any(a>=b for a,b in zip(profile['lower'],profile['upper']))
                or any(v<=0 for key in ('kp','kd','velocity') for v in profile[key])):
            raise ValueError('Invalid motor profile')
        self.profile = copy.deepcopy(profile)
        self._within_bounds(profile['defaults'])
        self.phase = 'idle'; self.reason = None; self.now = None; self.body = None
        self.body_received = None; self.body_age = None; self.ownership_at = None; self.request_at = None
        self.trajectory = None; self.init_end = None; self.settle_since = None
        self.target = None; self.target_at = None; self.control_seq = -1; self.writer_seq = -1
        self.last_target_received_at = None
        self.last_writer_at = None; self.events = deque(maxlen=128); self.commands = deque(maxlen=256)

    def _within_bounds(self, q):
        vector(q,29)
        if any(not a<=v<=b for a,v,b in zip(self.profile['lower'],q,self.profile['upper'])):
            raise ValueError('target_outside_model_bounds')

    def _event(self, operation):
        self.events.append(dict(op=operation,phase=self.phase,session=self.session,local_time_s=self.now,
                                hardware_output_enabled=False,physical_confirmation=False))

    def _clock(self, now):
        if type(now) not in (float,int) or not math.isfinite(now) or (self.now is not None and now < self.now):
            self._fail('invalid_local_clock')
        self.now = float(now)

    def _fail(self, reason):
        if self.reason is None: self.reason = reason
        self.phase = 'fault'; self.target = None; self._event('local_stop_required_not_dispatched')
        raise LifecycleFault(self.reason)

    def _phase(self, phases):
        if self.phase == 'fault': raise LifecycleFault(self.reason)
        if self.phase not in phases: self._fail('operation_not_allowed_in_'+self.phase)

    def _fresh_body(self):
        if self.body is None or self.body_age+self.now-self.body_received > self.config['max_body_age_s']:
            self._fail('body_watchdog_expired')

    def poll(self, now):
        self._clock(now)
        if self.phase == 'fault': raise LifecycleFault(self.reason)
        if self.phase in ACTIVE:
            self._fresh_body()
            if self.phase == 'ownership_pending' and self.now-self.request_at > self.config['max_takeover_wait_s']:
                self._fail('takeover_ack_timeout')
            if self.phase in OWNED and self.now-self.ownership_at > self.config['max_ownership_ack_age_s']:
                self._fail('ownership_ack_expired')
            if self.phase == 'tracking' and (self.target_at is None or self.now-self.target_at > self.config['max_command_age_s']):
                self._fail('command_watchdog_expired')
        return self.status()

    def observe(self, frame, *, now, source_age_s):
        self._phase({'idle','observing',*ACTIVE}); self.poll(now)
        try:
            validate_state(frame); self._within_bounds(frame['q'][:29])
            if type(source_age_s) not in (float,int) or not math.isfinite(source_age_s) or not 0<=source_age_s<=self.config['max_body_age_s']:
                raise ValueError('Invalid source age')
            if self.body is not None and not 0<((frame['tick']-self.body['tick'])&0xffffffff)<0x80000000:
                raise ValueError('Repeated/reversed body tick')
        except (ValueError,TypeError,KeyError) as exc: self._fail('invalid_body: '+str(exc))
        self.body = copy.deepcopy(frame); self.body_received = self.now; self.body_age = float(source_age_s)
        if self.phase == 'idle': self.phase = 'observing'
        if self.phase == 'settling':
            near = (max(abs(q-v) for q,v in zip(frame['q'][:29],self.profile['defaults'])) <= self.config['settle_position_tolerance_rad']
                and max(abs(v) for v in frame['dq'][:29]) <= self.config['settle_velocity_tolerance_rad_s'])
            if not near: self.settle_since = None
            elif self.settle_since is None: self.settle_since = self.now
            elif self.now-self.settle_since >= self.config['settle_duration_s']:
                self.phase = 'ready'; self._event('diagnostic_pose_settled')
        return self.status()

    def request_takeover(self, *, now):
        self._phase({'observing'}); self.poll(now); self._fresh_body()
        self.phase = 'ownership_pending'; self.request_at = self.now
        self._event('takeover_intent_not_dispatched')

    def _ack(self, session, kind):
        if session != self.session or kind != ACK_KIND: self._fail('invalid_diagnostic_ack')

    def confirm_takeover(self, *, session, kind, now):
        self._phase({'ownership_pending'}); self.poll(now); self._ack(session,kind)
        self.ownership_at = self.now; self.phase = 'owned'; self._event('diagnostic_ownership_ack')

    def refresh_ownership(self, *, session, kind, now):
        self._phase(OWNED); self.poll(now); self._ack(session,kind); self.ownership_at = self.now

    def begin_initialization(self, *, now):
        self._phase({'owned'}); self.poll(now)
        try:
            trajectory = JointTrajectory(self.body['q'][:29],self.body['dq'][:29],now=self.now,duration_s=self.config['init_duration_s'])
            trajectory.update(self.profile['defaults'],now=self.now)
            extrema = trajectory.extrema(begin=self.now,end=self.now+self.config['init_duration_s'])
            self._within_bounds(extrema['q_min'].tolist()); self._within_bounds(extrema['q_max'].tolist())
            if np.any(np.maximum(abs(extrema['dq_min']),abs(extrema['dq_max'])) > self.profile['velocity']):
                raise ValueError('initialization_reference_model_velocity')
        except ValueError as exc: self._fail('initialization_rejected: '+str(exc))
        self.trajectory = trajectory; self.init_end = self.now+self.config['init_duration_s']
        self.phase = 'initializing'; self._event('initial_reference_started_not_sent')

    def accept_target(self, *, session, seq, q, now, source_age_s):
        self._phase({'ready','tracking'}); self.poll(now)
        if session != self.session or type(seq) is not int or seq != self.control_seq+1: self._fail('target_identity')
        if type(source_age_s) not in (float,int) or not math.isfinite(source_age_s) or not 0<=source_age_s<=self.config['max_command_age_s']:
            self._fail('invalid_target_age')
        try: self._within_bounds(q)
        except ValueError as exc: self._fail(str(exc))
        previous = self.profile['defaults'] if self.target is None else self.target
        if max(abs(a-b) for a,b in zip(q,previous)) > self.config['max_target_step_rad']:
            self._fail('target_step_exceeded')
        dt = self.config['control_period_s'] if self.last_target_received_at is None else min(
            self.config['control_period_s'],self.now-self.last_target_received_at)
        if dt <= 0: self._fail('target_clock_not_increasing')
        if any(abs(a-b)>velocity*dt for a,b,velocity in zip(q,previous,self.profile['velocity'])):
            self._fail('target_reference_model_velocity')
        self.target = list(q); self.target_at = self.now-source_age_s; self.control_seq = seq; self.phase = 'tracking'
        self.last_target_received_at = self.now

    def sample_reference(self, *, now):
        """Control-rate reference for a separate native writer, not a write.

        The caller owns scheduling and must forward source age, not renew a
        held SONIC target's lifetime. Diagnostic ownership remains diagnostic.
        """
        self._phase({'initializing','settling','ready','tracking'}); self.poll(now)
        if self.phase == 'initializing' and self.now >= self.init_end:
            self.phase = 'settling'; self._event('initial_reference_elapsed_not_pose_confirmation')
        reference_dq = np.zeros(29)
        if self.phase == 'initializing': q,reference_dq,_ = self.trajectory.sample(self.now)
        elif self.phase == 'tracking': q = self.target
        else: q = self.profile['defaults']
        try:
            q = list(map(float,q)); self._within_bounds(q); vector(list(map(float,reference_dq)),29)
        except ValueError as exc: self._fail('invalid_writer_reference: '+str(exc))
        return dict(q=q,dq=[0.]*29,tau=[0.]*29,kp=list(self.profile['kp']),kd=list(self.profile['kd']),
                    reference_dq=list(map(float,reference_dq)),phase=self.phase,
                    source_age_s=0. if self.phase!='tracking' else self.now-self.target_at)

    def writer_tick(self, *, now):
        self._phase({'initializing','settling','ready','tracking'}); self.poll(now)
        if self.last_writer_at is not None and now <= self.last_writer_at: self._fail('writer_clock_not_increasing')
        if self.last_writer_at is not None and now-self.last_writer_at > self.config['max_writer_gap_s']:
            self._fail('writer_watchdog_expired')
        reference=self.sample_reference(now=now)
        self.writer_seq += 1; self.last_writer_at = self.now
        command = dict(schema='abstract_29_joint_record_NOT_Unitree_LowCmd',session=self.session,
            writer_seq=self.writer_seq,control_seq=self.control_seq,local_time_s=self.now,phase=self.phase,
            joint_names=list(self.profile['names']),**{key:reference[key] for key in ('q','dq','tau','kp','kd','reference_dq')},
            source_body_tick=self.body['tick'],hardware_output_enabled=False,robot_commands_sent=False)
        self.commands.append(copy.deepcopy(command)); return command

    def request_stop(self, reason='operator_stop'):
        # No clock, GPU request, worker join or network round trip precedes this latch.
        if self.phase == 'closed': return self.status()
        if self.reason is None: self.reason = str(reason)
        self.target = None
        if self.phase != 'fault': self.phase = 'stop_required'
        self._event('local_stop_required_not_dispatched'); return self.status()

    def acknowledge_stop(self, *, session, kind):
        if self.phase not in {'stop_required','fault'}: self._fail('stop_ack_before_stop_request')
        self._ack(session,kind); self.phase = 'return_pending'; self._event('diagnostic_stop_ack')

    def confirm_return(self, *, session, kind):
        self._phase({'return_pending'}); self._ack(session,kind)
        self.phase = 'closed'; self.ownership_at = None; self._event('diagnostic_return_ack')

    def status(self):
        return dict(phase=self.phase,reason=self.reason,command_records=self.writer_seq+1,
            retained_command_records=len(self.commands),retained_event_records=len(self.events),
            hardware_output_enabled=False,hardware_ready=False,robot_commands_sent=False,
            physical_ownership_confirmed=False,physical_stop_validated=False,
            physical_return_confirmed=False,stop_adapter_implemented=False,
            clock_scope='caller_local_monotonic; remote timestamps never subtracted',
            scope='body_lifecycle_diagnostic_not_actuator_transport')
