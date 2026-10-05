"""One G1 record runtime: strict local state + existing SONIC ZMQ + INIT + native writer.

Diagnostic ownership/initialization only. GPU cannot request takeover or inject
local readiness. There is intentionally no hardware-output option.
"""
import time
from body_lifecycle import ACK_KIND
from body_runtime import NativeBodyRecordRuntime
from local_body_service import LocalBodyRecordWorker


class LocalBodyRuntimeWorker(LocalBodyRecordWorker):
    def __init__(self,profile,config,clock=time.monotonic,*,require_crc=True,library):
        if not require_crc: raise ValueError('Native record runtime requires CRC')
        super().__init__(profile,config,clock,require_crc=True)
        self.library=library; self.native=None; self.native_final=None; self.last_body_tick=None

    def ingest_local(self,frame):
        raw=frame.get('raw_motor_state')
        if (not isinstance(raw,list) or len(raw)!=35
                or any(type(v) is not int or not 0<=v<=0xffffffff for v in raw)):
            raise ValueError('Updated local receiver raw_motor_state[35] required')
        if self.native:
            # The native mailbox must see CRC-verified identity loss BEFORE
            # the Python monitor rejects it, so old-machine stop is forbidden.
            self.native.local_body(frame); self.last_body_tick=frame['tick']
        if any(raw[:29]): raise ValueError('Nonzero local raw motor diagnostic; record runtime rejects')
        return super().ingest_local(frame)

    def handle(self,message):
        was_idle=self.phase=='idle'
        reply=super().handle(message)
        if was_idle:
            c=self.bridge.bridge.lifecycle
            try:
                self.native=NativeBodyRecordRuntime(self.library,self.profile,c.session)
                frame,_=self.monitor.snapshot(now=self.clock())
                self.native.local_body(frame); self.last_body_tick=frame['tick']
                now=self.clock(); c.request_takeover(now=now)
                c.confirm_takeover(session=c.session,kind=ACK_KIND,now=now)
                c.begin_initialization(now=now)
                self.native.reference(c.sample_reference(now=now),now=now)
                self.native.begin()
            except Exception:
                self.fail('native_record_start_failed'); raise
        elif self.phase=='stopped': self.stop_native('peer_record_stop')
        return reply

    def control_tick(self):
        if self.native is None or self.phase!='running': return
        c=self.bridge.bridge.lifecycle; now=self.clock()
        # A diagnostic ACK never grants a real SDK contract/ownership lease.
        c.refresh_ownership(session=c.session,kind=ACK_KIND,now=now)
        ref=c.sample_reference(now=now)
        self.native.reference(ref,now=now)

    def poll(self):
        super().poll()
        if self.native and self.phase=='running':
            status=self.native.snapshot()
            if status['stop_latched'] or status['writer_exited'] or status['owner_exited']:
                self.fail('native_owner_stopped: '+status['reason'])
                raise RuntimeError('Native record owner stopped: '+status['reason'])

    def fail(self,reason):
        super().fail(reason)
        if self.native: self.stop_native(reason,fault=True)

    def stop_native(self,reason,*,fault=False):
        if self.native:
            self.native.stop(reason,fault=fault); self.native_final=self.native.snapshot()

    def recover_native(self,stop_observation):
        if self.native is None or self.phase!='stopped': raise ValueError('Stopped record runtime required')
        self.native.recover(stop_observation); self.native_final=self.native.snapshot()

    def native_status(self):
        return self.native.snapshot() if self.native else self.native_final

    def close_native(self):
        if self.native:
            try:
                try: self.native.finish()
                finally: self.native_final=self.native.snapshot()
            finally: self.native.close(); self.native=None
