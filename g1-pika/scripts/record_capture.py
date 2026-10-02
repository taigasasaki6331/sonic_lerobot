"""Save bounded input images and metadata to a fresh diagnostic directory."""
import base64
import copy
import hashlib
import json
from pathlib import Path


def archive_json(folder,name,value):
    blob=(json.dumps(value,allow_nan=False,separators=(',',':'))+'\n').encode()
    path=Path(folder)/name
    if path.exists():
        if path.read_bytes()!=blob: raise ValueError('Refusing to replace an existing input record')
    else:
        with path.open('xb') as file: file.write(blob)
    return dict(file=name,sha256=hashlib.sha256(blob).hexdigest())


def archive_body(folder,seq,history):
    if type(seq) is not int or not 0<=seq<1500: raise ValueError('Body record sequence bound')
    return archive_json(folder,f'body-{seq:04d}.json',dict(seq=seq,body_history=history))


def archive_capture(folder,packet):
    seq=packet['seq']
    if type(seq) is not int or not 0<=seq<903: raise ValueError('Capture sequence bound')
    if set(packet['images'])!={'realsense_rgb','fisheye'}: raise ValueError('Capture roles')
    result=copy.deepcopy(packet)
    for role,image in result['images'].items():
        blob=base64.b64decode(image.pop('jpeg'),validate=True)
        if not 0<len(blob)<=1000000: raise ValueError('Image byte bound')
        digest=hashlib.sha256(blob).hexdigest()
        path=Path(folder)/('image-'+digest+'.jpg')
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError('Existing capture hash mismatch')
        else:
            with path.open('xb') as file: file.write(blob)
        image.update(sha256=digest,file=path.name)
    reference=archive_json(folder,f'capture-{seq:04d}.json',result)
    # Do not retain every nested body window in the coordinator's GC heap.
    return dict(seq=seq,**reference,images=result['images'])
