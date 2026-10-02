"""Read-only body-history protocol. Independent of camera and policy rates.

ZMQ requests carry only hello/read/stop, never motor commands. Age is bounded by
server-local sample age plus client-local RTT; host clocks are never subtracted.
The transport assumes a trusted isolated link, not authenticated ZMQ peers.
"""
from collections import deque
import copy
import math
import threading
import time
from state_history import validate_history,validate_state


class BodyHistoryBuffer:
    def __init__(self, clock=time.monotonic):
        self.clock=clock; self.condition=threading.Condition()
        self.frames=deque(maxlen=20); self.error=None; self.closed=False

    def push(self, frame):
        with self.condition:
            if self.closed or self.error: raise RuntimeError('Body source closed')
            try:
                validate_state(frame)
                self.frames.append(copy.deepcopy(frame))
            except Exception as exc:
                self.error=str(exc); self.condition.notify_all(); raise
            self.condition.notify_all()

    def fail(self, reason):
        with self.condition:
            self.error=reason; self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed=True; self.condition.notify_all()

    def warmup(self):
        return self.snapshot(timeout_s=1.,allow_warmup=True)

    def snapshot(self, previous_tick=None, timeout_s=.1,allow_warmup=False):
        deadline=time.monotonic()+timeout_s
        with self.condition:
            while True:
                if self.error or self.closed: raise RuntimeError(self.error or 'Body source closed')
                if len(self.frames)>=10 and self.frames[-1]['tick']!=previous_tick:
                    try:
                        retained=list(self.frames); end=len(retained)
                        if previous_tick is not None:
                            matches=[i for i,f in enumerate(retained) if f['tick']==previous_tick]
                            if len(matches)!=1 or matches[0]<8: raise ValueError('Requested consecutive body window no longer retained')
                            # Return the next REAL window, not the newest one
                            # after a small transport/scheduling delay. The
                            # unchanged age limit still rejects a stale backlog.
                            end=matches[0]+2
                        history=validate_history(retained[end-10:end])
                        age=self.clock()-history[-1]['receive_monotonic_s']
                        if not math.isfinite(age) or not 0<=age<=.1: raise ValueError('Body source stale or future')
                        return copy.deepcopy(history),age
                    except ValueError:
                        if not allow_warmup: raise
                remaining=deadline-time.monotonic()
                if remaining<=0: raise TimeoutError('No new complete body history')
                self.condition.wait(remaining)


class BodyHistoryServer:
    def __init__(self, buffer, max_frames=1500):
        if type(max_frames) is not int or not 1<=max_frames<=1500: raise ValueError('Frame bound')
        self.buffer=buffer; self.max_frames=max_frames; self.session=None
        self.sequence=0; self.previous_tick=None; self.closed=False

    def handle(self, request):
        if self.closed: raise RuntimeError('Body session closed')
        try:
            if self.session is None:
                if (set(request)!={'op','session','schema'} or request['op']!='hello' or request['schema']!=1
                        or type(request['schema']) is not int or not isinstance(request['session'],str) or not request['session']):
                    raise ValueError('Body hello schema')
                self.session=request['session']
                # Camera startup can disturb acquisition before any policy/control
                # request. Require a fresh real window at handshake, not a latched
                # invalid startup window. Once started, read() still rejects gaps.
                if hasattr(self.buffer,'warmup'): self.buffer.warmup()
                return dict(ready=True,session=self.session,schema=1,scope='measured_body_history_only',robot_commands_sent=False)
            if request.get('session')!=self.session: raise ValueError('Body session mismatch')
            if request==dict(op='stop',session=self.session):
                self.closed=True; return dict(stopped=True,session=self.session)
            if (set(request)!={'op','session','seq'} or request['op']!='read' or type(request['seq']) is not int
                    or request['seq']!=self.sequence or self.sequence>=self.max_frames):
                raise ValueError('Body request sequence/bound')
            history,age=self.buffer.snapshot(self.previous_tick)
            self.previous_tick=history[-1]['tick']; self.sequence+=1
            return dict(session=self.session,seq=request['seq'],body_history=history,
                        source_age_s=age,robot_commands_sent=False)
        except Exception:
            self.closed=True; raise


class BodyHistoryClient:
    def __init__(self,channel,session,clock=time.monotonic):
        self.channel=channel; self.session=session; self.clock=clock
        self.seq=0; self.phase='idle'

    def start(self):
        try:
            if self.phase!='idle': raise RuntimeError('Body client already started')
            self.channel.send(dict(op='hello',session=self.session,schema=1))
            expected=dict(ready=True,session=self.session,schema=1,scope='measured_body_history_only',robot_commands_sent=False)
            if self.channel.read()!=expected: raise ValueError('Body handshake')
            self.phase='running'
        except BaseException:
            self.phase='fault'; self.channel.close(); raise

    def read(self):
        try:
            if self.phase!='running': raise RuntimeError('Body client not running')
            sent=self.clock(); self.channel.send(dict(op='read',session=self.session,seq=self.seq))
            reply=self.channel.read(); received=self.clock()
            if 'error' in reply: raise RuntimeError('Body source: '+str(reply['error']))
            if (reply.get('session')!=self.session or type(reply.get('seq')) is not int or reply['seq']!=self.seq
                    or reply.get('robot_commands_sent') is not False): raise ValueError('Body response identity')
            age=reply['source_age_s']
            if type(age) not in (float,int) or not math.isfinite(age) or age<0: raise ValueError('Invalid source age')
            if not all(math.isfinite(v) for v in (sent,received)) or not 0<=received-sent or age+received-sent>.1:
                raise ValueError('Body input expired in transport')
            validate_history(reply['body_history']); self.seq+=1
            return dict(body_history=reply['body_history'],source_age_s=age+received-sent,
                        received_at=received,request_roundtrip_s=received-sent)
        except BaseException:
            self.phase='fault'; self.channel.close(); raise

    def close(self):
        self.channel.close()
        if self.phase!='fault': self.phase='stopped'

    def stop(self):
        try:
            if self.phase!='running': raise RuntimeError('Body client not running')
            self.channel.send(dict(op='stop',session=self.session))
            if self.channel.read()!=dict(stopped=True,session=self.session): raise ValueError('Body stop acknowledgement')
        except BaseException:
            self.phase='fault'; raise
        finally: self.close()
