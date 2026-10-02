"""Worker/endpoint tests; no sockets, DDS, devices, processes or physics."""
from pathlib import Path
import json
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_body_service import LocalBodyRecordWorker,endpoint_filter
from body_lifecycle import DEFAULT
from sonic_process import strict_message
from sonic_body_bridge import envelope
from check_local_body_monitor import local
from check_body_lifecycle import profile,body
from check_sonic_body_bridge import result

IPC='--ipc' in sys.argv
if IPC: sys.argv.remove('--ipc')


class Tests(unittest.TestCase):
    def worker(self):
        self.now=1.; return LocalBodyRecordWorker(profile(),strict_message(DEFAULT.read_bytes()),lambda:self.now)
    def hello(self): return dict(op='hello',session='s',schema=1,mode='record_only')
    def test_local_source_then_handshake_gate_and_stop(self):
        w=self.worker(); w.ingest_local(local()); self.assertTrue(w.handle(self.hello())['ready'])
        m=envelope('s',0,body(1),result(),source_age_s=0.,joint_names=profile()['names'])
        reply=w.handle(dict(op='record',session='s',seq=0,payload=m))
        self.assertEqual(reply['result']['decision'],'gated_initial_pose_not_ready')
        self.assertTrue(w.handle(dict(op='stop',session='s'))['stopped'])
        self.assertEqual(w.bridge.bridge.lifecycle.phase,'stop_required')
    def test_poll_expires_without_peer_request_and_cannot_rearm(self):
        w=self.worker(); w.ingest_local(local()); w.handle(self.hello()); self.now=1.101
        with self.assertRaises(ValueError): w.poll()
        with self.assertRaises(ValueError): w.handle(self.hello())
        self.assertEqual(w.phase,'fault'); self.assertIsNone(w.bridge.bridge.lifecycle.target)
    def test_cold_start_discards_old_pipe_samples_only_before_first_sample(self):
        w=self.worker(); self.assertFalse(w.ingest_local(local(stamp=.5)))
        self.assertIsNone(w.monitor.frame)
        self.assertTrue(w.ingest_local(local(stamp=1.)))
        self.now=1.2
        with self.assertRaises(ValueError): w.ingest_local(local(2,1.))
    def test_no_peer_local_state_INIT_takeover_or_execute(self):
        for op in ('local_state','initialize','takeover','execute'):
            w=self.worker(); w.ingest_local(local()); w.handle(self.hello())
            with self.assertRaises(ValueError): w.handle(dict(op=op,session='s'))
            self.assertEqual(w.phase,'fault')
    def test_endpoint_rejects_wildcard_and_requires_single_TCP_peer(self):
        self.assertIsNone(endpoint_filter('ipc:///tmp/local-body-test.sock',None))
        self.assertEqual(endpoint_filter('tcp://192.0.2.11:6000','192.0.2.10'),'192.0.2.10/32')
        for endpoint,peer in (('tcp://0.0.0.0:6000','192.0.2.9'),('tcp://192.0.2.7:6000',None),
                ('ipc://relative',None),('tcp://192.0.2.7:6000','224.0.0.1')):
            with self.assertRaises(ValueError): endpoint_filter(endpoint,peer)


@unittest.skipUnless(IPC,'Use --ipc for temporary local socket/process tests; no G1')
class ProcessTests(unittest.TestCase):
    def run_service(self,*,expire):
        from zmq_transport import ZmqChannel
        with tempfile.TemporaryDirectory(prefix='g1-local-body-test-') as directory:
            path=Path(directory); (path/'profile.json').write_text(json.dumps(profile()))
            (path/'config.json').write_bytes(DEFAULT.read_bytes()); endpoint='ipc://'+str(path/'body.sock')
            process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('local_body_service.py')),
                '--endpoint',endpoint,'--profile',str(path/'profile.json'),'--config',str(path/'config.json'),
                '--seconds','3'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            stop=threading.Event(); errors=[]; channel=None
            def feed():
                tick=1
                try:
                    while not stop.is_set():
                        stamp=time.monotonic(); frame=local(tick,stamp)
                        process.stdin.write((json.dumps(frame)+'\n').encode()); process.stdin.flush()
                        tick+=1; stop.wait(.02)
                except (BrokenPipeError,ValueError): pass
                except Exception as exc: errors.append(str(exc))
            source=threading.Thread(target=feed); source.start()
            try:
                if not select.select([process.stdout],[],[],3)[0]: self.fail('Local service startup timeout')
                line=process.stdout.readline()
                if not line: self.fail('Local service failed before ready: '+process.stderr.read().decode())
                ready=json.loads(line); self.assertTrue(ready['ready'])
                channel=ZmqChannel(endpoint,timeout_ms=1000)
                channel.send(dict(op='hello',session='s',schema=1,mode='record_only'))
                self.assertTrue(channel.read()['ready'])
                if expire:
                    stop.set(); source.join(1)
                    # Keep stdin OPEN; only stopped sensor updates may expire
                    # the watchdog, not an EOF or a GPU command.
                    self.assertNotEqual(process.wait(timeout=2),0)
                    self.assertIn('watchdog expired',process.stderr.read().decode())
                else:
                    message=envelope('s',0,body(1),result(),source_age_s=0.,joint_names=profile()['names'])
                    # Oversized diagnostic arrays: >4KiB must not truncate.
                    message['sonic']['encoder_token']=[.12345678901234567]*256
                    self.assertGreater(len(json.dumps(message)),4096)
                    channel.send(dict(op='record',session='s',seq=0,payload=message))
                    self.assertEqual(channel.read()['result']['decision'],'gated_initial_pose_not_ready')
                    channel.send(dict(op='stop',session='s'))
                    self.assertTrue(channel.read()['stopped']); self.assertEqual(process.wait(timeout=2),0)
                self.assertEqual(errors,[])
            finally:
                stop.set(); source.join(1)
                if channel: channel.close()
                if process.poll() is None: process.terminate(); process.wait(timeout=2)
                for pipe in (process.stdin,process.stdout,process.stderr):
                    try: pipe.close()
                    except BrokenPipeError: pass  # feeder can race with a clean receiver exit

    def test_actual_record_service_process_stops_cleanly(self): self.run_service(expire=False)
    def test_watchdog_expires_without_GPU_or_EOF(self): self.run_service(expire=True)


if __name__=='__main__': unittest.main()
