"""Latest absolute reference for independent policy/control rates, no IO.

An h1 action must be converted to an absolute TCP/joint reference before publish.
Reading a reference never integrates the relative action again. All timestamps
belong to the same coordinator's monotonic clock, not a remote machine's clock.
"""
import copy
import math
import threading


class ReferenceMailbox:
    def __init__(self,session,max_age_s):
        if not session or not math.isfinite(max_age_s) or max_age_s<=0: raise ValueError('Invalid mailbox configuration')
        self.session=session; self.max_age=max_age_s; self.lock=threading.Lock()
        self.latest=None; self.sequence=-1; self.phase='running'

    def publish(self,*,session,seq,issued_at,finished_at,reference):
        with self.lock:
            if self.phase!='running': raise RuntimeError('Mailbox closed')
            if session!=self.session or type(seq) is not int or seq!=self.sequence+1:
                self.phase='fault'; raise ValueError('Mailbox identity/sequence')
            if (not all(math.isfinite(t) for t in (issued_at,finished_at)) or
                    not 0<=finished_at-issued_at<=self.max_age):
                self.phase='fault'; raise ValueError('Reference computation too old')
            self.latest=dict(seq=seq,issued_at=issued_at,finished_at=finished_at,reference=copy.deepcopy(reference))
            self.sequence=seq

    def read(self,now):
        with self.lock:
            if self.phase!='running': raise RuntimeError('Mailbox closed')
            if self.latest is None: return None
            age=now-self.latest['issued_at']
            if not math.isfinite(age) or not 0<=age<=self.max_age:
                self.phase='fault'; raise ValueError(f'Reference expired: age={age:.9f}s limit={self.max_age:.9f}s')
            return copy.deepcopy(self.latest)

    def stop(self):
        with self.lock:
            if self.phase!='fault': self.phase='stopped'
            self.latest=None
