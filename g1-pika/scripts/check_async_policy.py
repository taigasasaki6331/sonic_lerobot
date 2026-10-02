"""Deterministic async tests: fake wall clock and transport, no hardware."""
from pathlib import Path
import sys
import os
from types import SimpleNamespace
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from async_policy_bridge import AsyncReplayBridge
from policy_replay_bridge import PipePolicy


class Transport:
    metadata={}
    def __init__(self): self.sent=[]; self.response=None; self.closed=False
    def begin(self,seq): self.sent.append(seq)
    def poll(self):
        response=self.response; self.response=None; return response
    def close(self): self.closed=True
    def answer(self,seq):
        self.response={'seq':seq,'timestamp':seq/30,
                       'action':[0,0,0,1,0,0,0,1,0,.04]}


class Tests(unittest.TestCase):
    def setUp(self):
        self.wall=0.; self.transport=Transport(); self.pose=np.eye(4)
        self.bridge=AsyncReplayBridge(self.transport,frames=2,clock=lambda:self.wall)
    def tick(self,t):
        self.wall=t
        return self.bridge.target(2+t,self.pose,self.pose)
    def test_pending_keeps_ticking_without_new_requests(self):
        for t in [0,.02,.04,.06,.08,.1]:
            np.testing.assert_array_equal(self.tick(t),self.pose)
        self.assertEqual(self.transport.sent,[0])
        self.assertEqual(self.bridge.pending_hold_ticks,5)
        self.transport.answer(0); self.tick(.12)
        self.assertEqual(self.transport.sent,[0,1])
        self.assertEqual(len(self.bridge.events),1)
        self.transport.answer(1); self.tick(.24); self.tick(.3)
        self.assertEqual(len(self.bridge.events),2)
    def test_deadline_latches_and_late_reply_never_applied(self):
        self.tick(0); self.transport.answer(0); self.tick(.5); self.tick(.6)
        self.assertIn('deadline',self.bridge.stop_reason)
        self.assertEqual(len(self.bridge.events),0)
        self.assertEqual(self.transport.sent,[0])
    def test_stale_rejected(self):
        self.tick(0); self.transport.answer(-1); self.tick(.1)
        self.assertIn('stale',self.bridge.stop_reason)
        self.assertEqual(self.transport.sent,[0])
    def test_cleanup(self):
        with self.bridge: self.tick(0)
        self.assertTrue(self.transport.closed)

    def test_real_pipe_empty_partial_and_eof(self):
        request_r,request_w=os.pipe(); response_r,response_w=os.pipe()
        client=PipePolicy.__new__(PipePolicy); client.buffer=b''
        with os.fdopen(request_r,'rb',buffering=0) as requests, \
             os.fdopen(request_w,'wb',buffering=0) as writer, \
             os.fdopen(response_r,'rb',buffering=0) as reader:
            client.process=SimpleNamespace(stdin=writer,stdout=reader)
            try:
                client.begin(0)
                self.assertEqual(requests.read(11),b'{"seq": 0}\n')
                self.assertIsNone(client.poll())
                os.write(response_w,b'{"seq":')
                self.assertIsNone(client.poll())
                os.write(response_w,b'0}\n')
                self.assertEqual(client.poll(),{'seq':0})
            finally: os.close(response_w)
            with self.assertRaises(RuntimeError): client.poll()


if __name__=='__main__': unittest.main()
