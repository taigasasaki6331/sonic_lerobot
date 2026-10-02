"""Fail-latched session/freshness boundary for RECORD-ONLY integration.

No physical stop is implemented. Caller clocks must be local monotonic clocks;
remote monotonic timestamps must never be subtracted from local timestamps.
"""
import math


class GateFault(RuntimeError): pass


class RecordGate:
    def __init__(self, session, limits):
        if not isinstance(session, str) or not session: raise ValueError('Session required')
        expected = {'max_source_age_s','max_roundtrip_s','max_tick_gap_s'}
        if set(limits) != expected or any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in limits.values()):
            raise ValueError('Invalid limits')
        self.session=session; self.limits=dict(limits); self.phase='idle'; self.reason=None
        self.last_seq=-1; self.last_time=None; self.pending=None

    def fail(self, reason):
        if self.reason is None: self.reason=reason
        self.phase='fault'; self.pending=None
        raise GateFault(self.reason)

    def start(self):
        if self.phase != 'idle': self.fail('start_not_allowed')
        self.phase='running'

    def submit(self, *, session, seq, now, source_age_s):
        if self.phase != 'running': self.fail('not_running')
        if session != self.session: self.fail('session_mismatch')
        if type(seq) is not int or seq != self.last_seq+1: self.fail('sequence_mismatch')
        if self.pending is not None: self.fail('request_already_pending')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (now,source_age_s)):
            self.fail('invalid_clock')
        if not 0<=source_age_s<=self.limits['max_source_age_s']: self.fail('stale_source')
        if self.last_time is not None and not 0<now-self.last_time<=self.limits['max_tick_gap_s']:
            self.fail('tick_gap')
        self.pending=(seq,now,source_age_s)

    def receive(self, *, session, seq, now):
        if self.phase != 'running' or self.pending is None: self.fail('no_pending_request')
        pending,sent,age=self.pending
        if session != self.session or type(seq) is not int or seq != pending: self.fail('response_identity')
        if type(now) not in (float,int) or not math.isfinite(now) or now<sent: self.fail('invalid_response_clock')
        elapsed=now-sent
        if elapsed>self.limits['max_roundtrip_s']: self.fail('response_timeout')
        if age+elapsed>self.limits['max_source_age_s']: self.fail('stale_at_response')
        self.last_seq=seq; self.last_time=now; self.pending=None

    def poll(self, now):
        if self.phase=='fault': raise GateFault(self.reason)
        if type(now) not in (float,int) or not math.isfinite(now): self.fail('invalid_clock')
        if self.pending:
            _,sent,age=self.pending
            if now<sent: self.fail('clock_reversed')
            if now-sent>self.limits['max_roundtrip_s']: self.fail('response_timeout')
            if age+now-sent>self.limits['max_source_age_s']: self.fail('stale_waiting')
        elif self.phase=='running' and self.last_time is not None:
            if now<self.last_time: self.fail('clock_reversed')
            if now-self.last_time>self.limits['max_tick_gap_s']: self.fail('input_timeout')

    def stop(self):
        self.pending=None
        if self.phase!='fault': self.phase='stopped'

    def status(self):
        return dict(phase=self.phase,reason=self.reason,last_seq=self.last_seq,
                    hardware_output_enabled=False,physical_stop_validated=False)
