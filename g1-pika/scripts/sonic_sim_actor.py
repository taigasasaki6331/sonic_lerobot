"""Pinned LeRobot ACT worker for hybrid MuJoCo tests, never live cameras.

RGB is an unchanged verified saved pair; width is explicitly assumed. Actual
simulated TCP anchors each fresh h1 action in the caller. Not visual/task proof.
"""
import base64
import hashlib
import json
from pathlib import Path
from sonic_process import JsonProcess


class SimActor:
    def __init__(self, root, images, record, bundle, output, frames):
        if type(frames) is not int or not 1<=frames<=900: raise ValueError('Require 1..900 ACT queries')
        self.worker=None; self.sequence=0; self.frames=frames
        capture=json.loads(Path(record).read_bytes())['frames'][0]['capture']
        self.images={}; self.hashes={}
        for role in ('realsense_rgb','fisheye'):
            blob=(Path(images)/('00-'+role+'.jpg')).read_bytes()
            digest=hashlib.sha256(blob).hexdigest()
            if digest!=capture['images'][role]['sha256']:
                raise ValueError('Saved ACT image SHA mismatch')
            self.images[role]={'jpeg':base64.b64encode(blob).decode()}
            self.hashes[role]=digest
        root=Path(root)
        self.log=(output/'act.stderr.log').open('x')
        try:
            self.worker=JsonProcess([root/'.venv-gpu/bin/python','-I',
                Path(__file__).with_name('probe_gpu_images.py'),'--root',root,
                '--policy-bundle',bundle,'--images',output,'--diagnostic-width','.04',
                '--stream','--frames',str(frames),'--warmup-steps','3'],self.log,startup_timeout=90)
            if self.worker.ready.get('hardware_ready') is not False:
                raise ValueError('ACT worker must be diagnostic only')
        except BaseException:
            if self.worker: self.worker.close()
            self.log.close(); raise

    def infer(self):
        self.worker.send(dict(seq=self.sequence,images=self.images))
        response=self.worker.read(timeout=5)
        if (type(response.get('seq')) is not int or response['seq']!=self.sequence
                or response.get('robot_commands_sent') is not False):
            raise ValueError('ACT sequence/output mode mismatch')
        self.sequence+=1
        return response

    def stop(self):
        self.worker.send(dict(stop=True))
        return self.worker.process.wait(timeout=5)

    def close(self):
        if self.worker: self.worker.close()
        self.log.close()
