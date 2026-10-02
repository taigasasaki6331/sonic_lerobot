"""Hybrid actor protocol tests using fake workers; no GPU/network/physics."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_sim_actor import SimActor


class Worker:
    def __init__(self,*args,**kwargs):
        self.ready={'hardware_ready':False}; self.closed=False; self.sequence=0
        self.process=type('Process',(),{'wait':lambda self,timeout:0})()
    def send(self,packet): self.packet=packet
    def read(self,timeout): return dict(seq=self.packet['seq'],action=[0.]*10,robot_commands_sent=False)
    def close(self): self.closed=True


class Tests(unittest.TestCase):
    def setup_files(self,path):
        images={}
        for role in ('realsense_rgb','fisheye'):
            blob=role.encode(); (path/('00-'+role+'.jpg')).write_bytes(blob)
            images[role]={'sha256':hashlib.sha256(blob).hexdigest()}
        record=path/'record.json'; record.write_text(json.dumps({'frames':[{'capture':{'images':images}}]}))
        return record

    def test_sequence_saved_image_integrity_and_close(self):
        with tempfile.TemporaryDirectory() as directory,patch('sonic_sim_actor.JsonProcess',Worker):
            path=Path(directory); actor=SimActor(path,path,self.setup_files(path),path/'bundle',path,3)
            self.assertEqual(actor.infer()['seq'],0); self.assertEqual(actor.infer()['seq'],1)
            self.assertEqual(actor.stop(),0); actor.close(); self.assertTrue(actor.worker.closed)

    def test_bad_image_rejected_before_worker_or_log(self):
        with tempfile.TemporaryDirectory() as directory,patch('sonic_sim_actor.JsonProcess') as worker:
            path=Path(directory); record=self.setup_files(path); (path/'00-fisheye.jpg').write_bytes(b'changed')
            with self.assertRaises(ValueError): SimActor(path,path,record,path/'bundle',path,3)
            worker.assert_not_called(); self.assertFalse((path/'act.stderr.log').exists())

    def test_bad_worker_mode_and_sequence_rejected(self):
        class WrongMode(Worker):
            def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.ready={'hardware_ready':True}
        with tempfile.TemporaryDirectory() as directory,patch('sonic_sim_actor.JsonProcess',WrongMode):
            path=Path(directory)
            with self.assertRaises(ValueError): SimActor(path,path,self.setup_files(path),path/'bundle',path,3)
        with tempfile.TemporaryDirectory() as directory,patch('sonic_sim_actor.JsonProcess',Worker):
            path=Path(directory); actor=SimActor(path,path,self.setup_files(path),path/'bundle',path,3)
            try:
                actor.sequence=1
                actor.worker.read=lambda **kw:dict(seq=0,robot_commands_sent=False)
                with self.assertRaises(ValueError): actor.infer()
            finally: actor.close()

    def test_query_bound(self):
        for frames in (0,901,True):
            with self.assertRaises(ValueError): SimActor(Path('/tmp'),Path('/tmp'),Path('/tmp/absent'),Path('/tmp'),Path('/tmp'),frames)


if __name__=='__main__': unittest.main()
