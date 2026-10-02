"""Worker ownership, nonblocking poll and cleanup without external connections."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from async_split import Worker


class FakeChannel:
    calls = []
    entered = None
    release = None
    bad = False
    def __init__(self, *args, **kwargs): self.record(); self.packet = None
    def record(self): self.calls.append(threading.get_ident())
    def send(self, packet): self.record(); self.packet = packet
    def read(self):
        self.record()
        if self.packet.get('op') == 'stop': return {'stopped': True, 'session': 'test'}
        if self.packet.get('op') == 'hello': return {'ready': True}
        self.entered.set()
        if not self.release.wait(1): raise TimeoutError('test release missing')
        return {'seq': self.packet['seq'], 'session': 'wrong' if self.bad else 'test'}
    def close(self): self.record()


class Tests(unittest.TestCase):
    def setUp(self):
        FakeChannel.calls = []
        FakeChannel.entered = threading.Event()
        FakeChannel.release = threading.Event()
        FakeChannel.bad = False
    def test_nonblocking_and_socket_owner(self):
        with patch('async_split.ZmqChannel', FakeChannel):
            worker = Worker('unused', 'test')
            try:
                worker.begin({'seq': 0})
                self.assertTrue(FakeChannel.entered.wait(1))
                self.assertIsNone(worker.poll())
                FakeChannel.release.set()
                response = worker.results.get(timeout=1)
                self.assertEqual(response[0]['seq'], 0)
            finally:
                FakeChannel.release.set()
                worker.close()
        self.assertTrue(worker.shutdown_confirmed)
        self.assertEqual(len(set(FakeChannel.calls)), 1)
        self.assertNotEqual(FakeChannel.calls[0], threading.get_ident())
    def test_stale_session_and_cleanup(self):
        FakeChannel.bad = True
        FakeChannel.release.set()
        with patch('async_split.ZmqChannel', FakeChannel):
            worker = Worker('unused', 'test')
            worker.begin({'seq': 0})
            self.assertIsInstance(worker.results.get(timeout=1), ValueError)
            worker.close()
        self.assertTrue(worker.shutdown_confirmed)
    def test_hello(self):
        with patch('async_split.ZmqChannel', FakeChannel):
            worker = Worker('unused', 'test', hello=True)
            self.assertEqual(worker.results.get(timeout=1), {'ready': True})
            worker.close()
    def test_closed_worker_rejects_request(self):
        with patch('async_split.ZmqChannel', FakeChannel):
            worker = Worker('unused', 'test')
            worker.close()
            with self.assertRaises(RuntimeError): worker.begin({'seq': 0})


if __name__ == '__main__': unittest.main()
