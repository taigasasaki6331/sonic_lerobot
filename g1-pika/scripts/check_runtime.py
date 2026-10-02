import copy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime_config import load, validate
from runtime_gate import RecordGate, GateFault
from record_session import RecordSession
from zmq_transport import ZmqChannel
IPC='--ipc' in sys.argv
if IPC: sys.argv.remove('--ipc')


class Tests(unittest.TestCase):
    def gate(self):
        gate=RecordGate('new-session',load()['diagnostic_deadlines']); gate.start(); return gate

    def test_config(self):
        config=load()
        self.assertEqual(validate(config),config)
        for key,value in [('hardware_output_enabled',True),('mode','live'),('gpu_host','-oProxyCommand=x'),('cuda_root','/')]:
            bad=copy.deepcopy(config); bad[key]=value
            with self.assertRaises(ValueError): validate(bad)

    def test_unknown_config(self):
        config=load(); config['ignore_safety']=True
        with self.assertRaises(ValueError): validate(config)

    def test_fresh(self):
        gate=self.gate()
        gate.submit(session='new-session',seq=0,now=100.,source_age_s=.01)
        gate.receive(session='new-session',seq=0,now=100.02)
        self.assertEqual(gate.last_seq,0)
        gate.stop(); self.assertEqual(gate.phase,'stopped')
        with self.assertRaises(GateFault): gate.start()

    def test_stale_submit(self):
        gate=self.gate()
        with self.assertRaises(GateFault): gate.submit(session='new-session',seq=0,now=1.,source_age_s=.2)
        self.assertEqual(gate.phase,'fault')
        with self.assertRaises(GateFault): gate.start()

    def test_old_session(self):
        gate=self.gate()
        with self.assertRaises(GateFault): gate.submit(session='old-session',seq=0,now=1.,source_age_s=0.)

    def test_duplicate(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=0.)
        gate.receive(session='new-session',seq=0,now=1.01)
        with self.assertRaises(GateFault): gate.submit(session='new-session',seq=0,now=1.02,source_age_s=0.)

    def test_wrong_reply(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=0.)
        with self.assertRaises(GateFault): gate.receive(session='old',seq=0,now=1.01)

    def test_late_reply(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=.08)
        with self.assertRaises(GateFault): gate.receive(session='new-session',seq=0,now=1.04)
        self.assertEqual(gate.reason,'stale_at_response')

    def test_disconnect_poll(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=0.)
        with self.assertRaises(GateFault): gate.poll(2.)

    def test_missing_input(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=0.)
        gate.receive(session='new-session',seq=0,now=1.01)
        with self.assertRaises(GateFault): gate.poll(2.)

    def test_invalid_clock(self):
        for now in (float('nan'),float('inf')):
            gate=self.gate()
            with self.assertRaises(GateFault): gate.submit(session='new-session',seq=0,now=now,source_age_s=0.)

    def test_poll_clock_reversal(self):
        gate=self.gate(); gate.submit(session='new-session',seq=0,now=1.,source_age_s=0.)
        gate.receive(session='new-session',seq=0,now=1.01)
        with self.assertRaises(GateFault): gate.poll(.9)

    @unittest.skipUnless(IPC, 'Use --ipc for local socket integration tests')
    def test_real_zmq_lifecycle(self):
        # IPC exercises libzmq but cannot contact a robot or remote host.
        with tempfile.TemporaryDirectory(prefix='g1-pika-zmq-') as directory:
            endpoint='ipc://'+str(Path(directory)/'worker.sock')
            errors=[]
            ready=threading.Event()
            def worker():
                server=None
                try:
                    server=ZmqChannel(endpoint,server=True,timeout_ms=1000)
                    ready.set()
                    hello=server.read()
                    server.send(dict(ready=True,session=hello['session'],schema=1,mode='record_only',hardware_output_enabled=False))
                    request=server.read()
                    server.send(dict(session=request['session'],seq=request['seq'],result={'recorded':True},hardware_output_enabled=False))
                    stop=server.read(); server.send(dict(stopped=True,session=stop['session']))
                except BaseException as exc: errors.append(exc)
                finally:
                    ready.set()
                    if server: server.close()
            thread=threading.Thread(target=worker); thread.start()
            self.assertTrue(ready.wait(2))
            if errors:
                thread.join(3)
                raise RuntimeError('IPC bind failed: '+str(errors[0]))
            client=RecordSession(ZmqChannel(endpoint,timeout_ms=1000),'ipc-test',load()['diagnostic_deadlines'])
            try:
                client.start(); self.assertEqual(client.query(0,{'test':True},0.),{'recorded':True}); client.stop()
            finally: client.close(); thread.join(3)
            self.assertFalse(thread.is_alive()); self.assertEqual(errors,[])
            self.assertEqual(client.gate.phase,'stopped')

    @unittest.skipUnless(IPC, 'Use --ipc for local socket integration tests')
    def test_real_zmq_timeout_closes(self):
        with tempfile.TemporaryDirectory(prefix='g1-pika-zmq-') as directory:
            channel=ZmqChannel('ipc://'+str(Path(directory)/'absent.sock'),timeout_ms=30)
            client=RecordSession(channel,'timeout-test',load()['diagnostic_deadlines'])
            with self.assertRaises(OSError): client.start()
            self.assertTrue(client.closed)


if __name__=='__main__': unittest.main()
