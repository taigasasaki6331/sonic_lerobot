"""ZMQ request lifecycle for record-only workers, never an actuator transport."""
import time
from runtime_gate import RecordGate, GateFault


class RecordSession:
    def __init__(self, channel, session, limits, clock=time.monotonic):
        self.channel=channel; self.clock=clock
        self.gate=RecordGate(session, limits); self.closed=False

    def start(self):
        try:
            self.channel.send(dict(op='hello', session=self.gate.session, schema=1, mode='record_only'))
            reply=self.channel.read()
            if reply != dict(ready=True, session=self.gate.session, schema=1, mode='record_only', hardware_output_enabled=False):
                self.gate.fail('worker_handshake')
            self.gate.start()
        except BaseException:
            if self.gate.phase!='fault':
                try: self.gate.fail('startup_failed')
                except GateFault: pass
            self.close()
            raise

    def query(self, seq, payload, source_age_s):
        try:
            self.gate.submit(session=self.gate.session, seq=seq, now=self.clock(), source_age_s=source_age_s)
            self.channel.send(dict(op='record', session=self.gate.session, seq=seq, payload=payload))
            reply=self.channel.read()
            self.gate.receive(session=reply.get('session'), seq=reply.get('seq'), now=self.clock())
            if reply.get('hardware_output_enabled') is not False: self.gate.fail('worker_not_record_only')
            return reply['result']
        except BaseException as exc:
            if self.gate.phase!='fault':
                try: self.gate.fail(type(exc).__name__)
                except GateFault: pass
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.channel.close(); self.closed=True
        self.gate.stop()

    def stop(self):
        try:
            if not self.closed and self.gate.phase=='running':
                self.channel.send(dict(op='stop', session=self.gate.session))
                if self.channel.read()!=dict(stopped=True,session=self.gate.session):
                    self.gate.fail('shutdown_ack')
        except (OSError,ValueError,KeyError) as exc:
            self.gate.fail('shutdown_'+type(exc).__name__)
        finally:
            self.close()
