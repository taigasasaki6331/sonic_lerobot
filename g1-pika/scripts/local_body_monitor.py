"""G1-local LowState freshness monitor, independent of GPU/ZMQ replies.

The input must come from receive_state on this SAME Linux host. This pure core
has no sockets, SDK or writer, and cannot confirm ownership or physical stop.
"""
import copy
import math
from state_history import validate_state


class LocalBodyMonitor:
    def __init__(self, *, max_age_s=.1,require_crc=False):
        if type(max_age_s) not in (int,float) or not math.isfinite(max_age_s) or not 0<max_age_s<=.1:
            raise ValueError('Local body age limit must be 0..100ms')
        if type(require_crc) is not bool: raise ValueError('Explicit CRC requirement bool')
        self.require_crc=require_crc
        self.max_age_s=max_age_s; self.frame=None; self.now=None; self.fault=None; self.mode_machine=None

    def _fail(self, reason):
        if self.fault is None: self.fault=str(reason)
        raise ValueError(self.fault)

    def _clock(self, now):
        if self.fault: raise ValueError(self.fault)
        if type(now) not in (int,float) or not math.isfinite(now) or (self.now is not None and now<self.now):
            self._fail('local_body_clock_invalid')
        self.now=float(now)

    def ingest_local(self, frame, *, now):
        self._clock(now)
        try:
            validate_state(frame)
            for key in ('mode_machine','mode_pr'):
                if type(frame.get(key)) is not int or not 0<=frame[key]<=255:
                    raise ValueError('Missing/invalid local LowState '+key)
            if frame['mode_pr']!=0: raise ValueError('Only P/R mode supported by current command profile')
            if type(frame.get('crc_verified')) is not bool: raise ValueError('Explicit CRC verification status required')
            if self.require_crc:
                if frame['crc_verified'] is not True: raise ValueError('Verified local LowState CRC required')
                for key in ('crc_received','crc_calculated'):
                    if type(frame.get(key)) is not int or not 0<=frame[key]<=0xffffffff:
                        raise ValueError('CRC diagnostic uint32 required')
                if (frame['crc_received']!=frame['crc_calculated'] or
                        type(frame.get('crc_native_size_bytes')) is not int or frame['crc_native_size_bytes']!=2092):
                    raise ValueError('Local CRC diagnostic mismatch')
            age=self.now-frame['receive_monotonic_s']
            if not 0<=age<=self.max_age_s: raise ValueError('Local body source stale/future or not same-host clock')
            if self.mode_machine is not None and frame['mode_machine']!=self.mode_machine:
                raise ValueError('Local robot mode_machine changed during session')
            if self.frame is not None:
                delta=(frame['tick']-self.frame['tick'])&0xffffffff
                if delta==0:
                    if any(frame[key]!=self.frame[key] for key in ('q','dq','gyroscope','quaternion')):
                        raise ValueError('Repeated body tick with changed sensor values')
                    # A duplicate DDS sample must never renew the watchdog.
                    self.snapshot(now=self.now)
                    return False
                if delta>=0x80000000: raise ValueError('Reversed local body tick')
                if frame['receive_monotonic_s']<=self.frame['receive_monotonic_s']:
                    raise ValueError('Local body receive clock not increasing')
            self.frame=copy.deepcopy(frame); self.mode_machine=frame['mode_machine']
            return True
        except (ValueError,KeyError,TypeError) as exc: self._fail(str(exc))

    def snapshot(self, *, now):
        self._clock(now)
        if self.frame is None: self._fail('No local LowState')
        age=self.now-self.frame['receive_monotonic_s']
        if not 0<=age<=self.max_age_s: self._fail('Local LowState watchdog expired')
        return copy.deepcopy(self.frame),age

    def status(self):
        return dict(scope='same_host_LowState_monitor_NOT_actuator_transport',
            local_body_tick=self.frame['tick'] if self.frame else None,mode_machine=self.mode_machine,
            fault=self.fault,crc_verified=self.frame['crc_verified'] if self.frame else False,
            crc_verification_required=self.require_crc,
            hardware_ready=False,robot_commands_sent=False,physical_stop_validated=False)
