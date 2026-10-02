"""Decode only train/validation frames from verified valid49; never cache test images."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from dataset_manifest import inventory
from train_rgb_smoke import rgb_input, CAMERAS


def main():
    if sys.version_info[:3] != (3,12,13):
        raise RuntimeError('Python version mismatch')
    lock = ROOT/'requirements-gpu.lock'
    for line in lock.read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name, version = line.split('==')
            if metadata.version(name) != version:
                raise RuntimeError(f'Dependency differs: {name}')
    upstream = ROOT/'vendor/lerobot'
    commit = json.loads((ROOT/'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()!=commit:
        raise RuntimeError('Wrong LeRobot commit')
    subprocess.run(['git','-C',str(upstream),'diff','--exit-code','HEAD'],check=True)
    sys.path.insert(0,str(upstream/'src'))
    os.environ.update(HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
                      HF_HOME=str(ROOT/'.cache/hf'),TORCH_HOME=str(ROOT/'.cache/torch'))
    def audit(event,args):
        if event in {'socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden in cache builder')
    sys.addaudithook(audit)
    import torch
    from safetensors.torch import save_file
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    torch.set_num_threads(4)
    data = ROOT/'datasets/valid49'
    files = ROOT/'assets/valid49-transfer-manifest.json'
    split_path = ROOT/'assets/valid49-split.json'
    split = json.loads(split_path.read_text())
    if inventory(data) != json.loads(files.read_text())['files']:
        raise RuntimeError('Dataset hash differs')
    if hashlib.sha256(files.read_bytes()).hexdigest()!=split['file_manifest_sha256']:
        raise RuntimeError('Split provenance differs')
    if split['splits'] != {'train':list(range(39)),'validation':list(range(39,44)),'test':list(range(44,49))}:
        raise RuntimeError('Unexpected split')
    tensors = {}
    for name in ['train','validation']:
        n = split['counts'][name]
        for key in ['observation.state','action',*CAMERAS]:
            shape = (n,3,96,128) if key in CAMERAS else (n,10)
            tensors[f'{name}/{key}'] = torch.empty(shape,dtype=torch.float32)
    positions = {'train':0,'validation':0}
    mapping = {'train':[],'validation':[]}
    start = time.perf_counter()
    for selection in split['selection']:
        name, episode = selection['split'], selection['episode']
        if name == 'test':
            continue
        if episode not in split['splits'][name]:
            raise RuntimeError('Wrong episode membership')
        ds = LeRobotDataset('data',root=data,episodes=[episode],return_uint8=True,video_backend='pyav')
        for index in selection['selected']:
            item = ds[index]
            if int(item['frame_index']) != index or int(item['episode_index']) != episode:
                raise RuntimeError('Dataset index alignment mismatch')
            sample = rgb_input(item)
            sample['action'] = item['action'].float()
            if not all(torch.isfinite(value).all() for value in sample.values()):
                raise RuntimeError('Nonfinite sample')
            position = positions[name]
            for key,value in sample.items():
                tensors[f'{name}/{key}'][position] = value
            positions[name] += 1
            mapping[name].append([episode,index])
        print(f'Cached episode {episode}: {len(selection["selected"])} {name} frames',flush=True)
    if positions != {k:split['counts'][k] for k in positions}:
        raise RuntimeError('Missing samples')
    base = ROOT/'artifacts/full-rgb-cache'
    base.mkdir(parents=True,exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='cache-',dir=base))
    save_file(tensors,directory/'samples.safetensors')
    digest = hashlib.sha256()
    with (directory/'samples.safetensors').open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    manifest = {'purpose':'valid49_train_validation_all_selected_RGB_frames',
        'samples_sha256':digest.hexdigest(),'counts':positions,'mapping':mapping,
        'lerobot_commit':commit,'split_sha256':hashlib.sha256(split_path.read_bytes()).hexdigest(),
        'source_files_manifest_sha256':split['file_manifest_sha256'],
        'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'preprocess_script_sha256':hashlib.sha256((ROOT/'scripts/train_rgb_smoke.py').read_bytes()).hexdigest(),
        'requirements_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
        'test_images_decoded':False,'depth_used':False,'build_seconds':time.perf_counter()-start,
        'resize':'same CPU smoke rgb_input: float32 [0,1], bilinear antialias 96x128'}
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for path in [Path(__file__),ROOT/'scripts/train_rgb_smoke.py',split_path,files]:
        (directory/path.name).write_bytes(path.read_bytes())
    (ROOT/'artifacts/full-rgb-cache-latest.json').write_text(json.dumps({'cache':str(directory)})+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='mapping'},indent=2))


if __name__ == '__main__':
    main()
