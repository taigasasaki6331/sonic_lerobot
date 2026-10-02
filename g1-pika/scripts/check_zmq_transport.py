"""Local IPC checks for bounded ZMQ transport, no network or robot."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from zmq_transport import ZmqChannel


class Tests(unittest.TestCase):
    def test_publication_poll(self):
        with tempfile.TemporaryDirectory(prefix='pika-zmq-pub-') as path:
            endpoint='ipc://'+path+'/socket'
            pub=ZmqChannel(endpoint,server=True,kind='pub',timeout_ms=100)
            sub=ZmqChannel(endpoint,kind='sub',timeout_ms=0)
            result=None
            try:
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    pub.send({'seq':0})
                    try: result=sub.read(); break
                    except OSError as exc:
                        if exc.errno!=11: raise
                    time.sleep(.01)
                self.assertEqual(result,{'seq':0})
            finally: sub.close(); pub.close()
    def test_request_reply_and_shutdown(self):
        with tempfile.TemporaryDirectory(prefix='pika-zmq-test-') as path:
            endpoint='ipc://'+path+'/socket'; ready=threading.Event(); errors=[]
            def server():
                channel=None
                try:
                    channel=ZmqChannel(endpoint,server=True,timeout_ms=1000); ready.set()
                    self.assertEqual(channel.read(),{'seq':0}); channel.send({'seq':0})
                    self.assertEqual(channel.read(),{'stop':True}); channel.send({'stopped':True})
                except BaseException as exc: errors.append(exc); ready.set()
                finally:
                    if channel: channel.close()
            thread=threading.Thread(target=server); thread.start()
            self.assertTrue(ready.wait(2))
            client=ZmqChannel(endpoint,timeout_ms=1000)
            try:
                client.send({'seq':0}); self.assertEqual(client.read(),{'seq':0})
                client.finish()
            finally: client.close(); thread.join(timeout=2)
            self.assertFalse(thread.is_alive()); self.assertEqual(errors,[])
    def test_receive_timeout(self):
        with tempfile.TemporaryDirectory(prefix='pika-zmq-test-') as path:
            channel=ZmqChannel('ipc://'+path+'/socket',server=True,timeout_ms=30)
            try:
                with self.assertRaises(OSError): channel.read()
            finally: channel.close()
    def test_invalid_output_rejected(self):
        with tempfile.TemporaryDirectory(prefix='pika-zmq-test-') as path:
            channel=ZmqChannel('ipc://'+path+'/socket',timeout_ms=30)
            try:
                with self.assertRaises(ValueError): channel.send({'x':float('nan')})
                with self.assertRaises(ValueError): channel.send({'x':'x'*2000001})
            finally: channel.close()
    def test_numeric_overflow_rejected(self):
        with tempfile.TemporaryDirectory(prefix='pika-zmq-overflow-') as path:
            endpoint='ipc://'+path+'/socket'
            server=ZmqChannel(endpoint,server=True,timeout_ms=1000)
            client=ZmqChannel(endpoint,timeout_ms=1000)
            try:
                payload=b'{"nested":[1e999]}'
                client.check(client.lib.zmq_send(client.socket,payload,len(payload),0))
                with self.assertRaises(ValueError): server.read()
            finally: client.close(); server.close()


if __name__=='__main__': unittest.main()
