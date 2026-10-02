"""Real local child-process fault tests; no GPU, sockets or robot IO."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_process import JsonProcess, SonicProcess, strict_message


class ProcessTests(unittest.TestCase):
    def worker(self, source):
        log = tempfile.TemporaryFile()
        self.addCleanup(log.close)
        worker = JsonProcess([sys.executable, '-I', '-u', '-c', source], log, startup_timeout=2)
        self.addCleanup(worker.close)
        return worker

    def test_invalid_json_values(self):
        for text in ('[]', 'null', '{"x":NaN}', '{"x":[1e999]}',
                     '{"ready":true,"ready":false}', '{"x":-Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError): strict_message(text)

    def test_roundtrip_and_close(self):
        worker = self.worker('import sys; print(\'{"ready":true}\'); print(sys.stdin.readline(), end="")')
        worker.send({'seq': 0})
        self.assertEqual(worker.read(2), {'seq': 0})
        worker.close(); worker.close()
        self.assertIsNotNone(worker.process.poll())

    def test_read_timeout(self):
        worker = self.worker('import time; print(\'{"ready":true}\'); time.sleep(30)')
        with self.assertRaises(TimeoutError): worker.read(.02)
        worker.close()
        self.assertIsNotNone(worker.process.poll())

    def test_unexpected_exit(self):
        worker = self.worker('print(\'{"ready":true}\')')
        worker.process.wait(timeout=2)
        with self.assertRaises(RuntimeError): worker.read(1)

    def test_oversized_response(self):
        worker = self.worker('print(\'{"ready":true}\'); print("x"*2000001)')
        with self.assertRaises(ValueError): worker.read(2)

    def test_infer_fault_closes_worker(self):
        for response in ('{"seq":1,"hardware_output_enabled":false,"result":{}}',
                         '{"seq":false,"hardware_output_enabled":false,"result":{}}',
                         '{"seq":0,"hardware_output_enabled":true,"result":{}}',
                         '{"seq":0,"hardware_output_enabled":false,"result":null}'):
            with self.subTest(response=response):
                worker = self.worker('import sys,time; print(\'{"ready":true}\'); sys.stdin.readline(); '
                                     'print('+repr(response)+'); time.sleep(30)')
                # Exercise the real SONIC client method with an intentionally faulty child.
                with self.assertRaises(ValueError): SonicProcess.infer(worker, {})
                self.assertEqual(worker.sequence, 0)
                self.assertIsNotNone(worker.process.poll())


if __name__ == '__main__': unittest.main()
