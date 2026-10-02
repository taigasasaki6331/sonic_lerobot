"""Nonblocking, single-flight recorded replay; NOT a real-time robot controller."""
import time
import numpy as np
from policy_replay_bridge import ReplayBridge


class CachedResponse:
    def __init__(self,metadata): self.metadata=metadata; self.response=None
    def query(self,seq): return self.response


class AsyncReplayBridge(ReplayBridge):
    def __init__(self,client,frames=30,fault='none',reference_mode='integrated',
                 timeout=.5,clock=time.monotonic):
        if not np.isfinite(timeout) or timeout<=0: raise ValueError('Invalid timeout')
        self.transport=client
        super().__init__(CachedResponse(client.metadata),frames,fault,reference_mode)
        self.clock=clock; self.timeout=timeout; self.pending=None
        self.actual_last_time=-1.; self.poll_count=0; self.pending_hold_ticks=0
        self.last_send=-float('inf'); self.callback_ms=[]

    def target(self,now,origin,measured):
        start=time.perf_counter()
        try: return self.update(now,origin,measured)
        finally: self.callback_ms.append((time.perf_counter()-start)*1000)

    def update(self,now,origin,measured):
        if self.last_target is None: self.last_target=origin.copy()
        if self.stop_reason: return self.last_target.copy()
        if not np.isfinite(now) or now<self.actual_last_time:
            self.stop_reason='non_monotonic_sim_time'; return self.last_target.copy()
        self.actual_last_time=now
        if now<self.settle: return self.last_target.copy()
        wall=self.clock()
        try:
            if self.pending is not None:
                seq,sent=self.pending
                age=wall-sent
                if age>=self.timeout: raise TimeoutError('Policy response deadline exceeded')
                # Fault injection withholds delivery, never sleeps in control loop.
                withheld=seq==5 and (self.fault=='silence' or
                                     (self.fault=='delay' and age<.25))
                self.poll_count+=1
                response=None if withheld else self.transport.poll()
                if response is None:
                    self.pending_hold_ticks+=1
                    return self.last_target.copy()
                self.client.response=response
                count=len(self.events)
                super().target(self.settle+seq/30,origin,measured)
                self.request_ms[-1:]=[age*1000]
                if len(self.events)>count:
                    self.events[-1]['sim_time']=float(now)
                    self.events[-1]['response_age_ms']=age*1000
                self.pending=None
            if not self.stop_reason and self.last_seq+1<self.frames and wall-self.last_send>=1/30:
                seq=self.last_seq+1
                self.transport.begin(seq)
                self.pending=(seq,wall); self.last_send=wall
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            self.stop_reason=f'{type(exc).__name__}: {exc}'
        return self.last_target.copy()

    def metrics(self):
        result=super().metrics(); m=result['policy_bridge']
        m.update(synchronous_simulation_only=False, nonblocking_transport=True,
                 lerobot_hz_sim_time=None, max_request_hz_wall=30,
                 playback_timing='recorded frames in sequence, slowed to response availability',
                 real_time_deadline_verified=False, response_timeout_s=self.timeout,
                 pending_hold_ticks=self.pending_hold_ticks,
                 callback_p95_ms=float(np.percentile(self.callback_ms,95)),
                 callback_max_ms=max(self.callback_ms))
        return result

    def __exit__(self,*args): self.transport.close()
