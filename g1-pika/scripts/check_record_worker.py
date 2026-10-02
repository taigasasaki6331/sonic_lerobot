from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from record_worker import RecordWorker


class Tests(unittest.TestCase):
    def data(self):
        request=dict(source_sha256='test',frames=[dict(seq=9,gripper_width_m=.04)])
        result=dict(source_sha256='test',hardware_ready=False,robot_commands_sent=False,
                    outputs=[dict(seq=9,q_target_hardware=[0]*29,gripper_width_m=.04,gripper_actuated=False)])
        return request,result
    def started(self):
        worker=RecordWorker(*self.data())
        worker.handle(dict(op='hello',session='test',schema=1,mode='record_only'))
        return worker
    def test_lifecycle(self):
        worker=self.started()
        out=worker.handle(dict(op='record',seq=0,session='test'))
        self.assertEqual(out['result']['seq'],9)
        self.assertFalse(out['hardware_output_enabled'])
        worker.handle(dict(op='stop',session='test'))
        with self.assertRaises(ValueError): worker.handle(dict(op='record',seq=1,session='test'))
    def test_duplicate_fault_latches(self):
        worker=self.started(); worker.handle(dict(op='record',seq=0,session='test'))
        with self.assertRaises(ValueError): worker.handle(dict(op='record',seq=0,session='test'))
        self.assertEqual(worker.phase,'fault')
    def test_identity(self):
        worker=self.started()
        with self.assertRaises(ValueError): worker.handle(dict(op='record',seq=0,session='old'))
    def test_invalid_file(self):
        a,b=self.data(); b['outputs'][0]['q_target_hardware'][0]=float('inf')
        with self.assertRaises(ValueError): RecordWorker(a,b)
    def test_hardware_rejected(self):
        a,b=self.data(); b['robot_commands_sent']=True
        with self.assertRaises(ValueError): RecordWorker(a,b)


if __name__=='__main__': unittest.main()
