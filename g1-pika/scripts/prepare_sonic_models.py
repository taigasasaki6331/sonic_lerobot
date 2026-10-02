"""Download a fixed official ONNX pair and manifest. No controller execution."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = '6733128a3d8a523b1418b06bca3cdf61c8b0987f'
REPO = 'nvidia/GEAR-SONIC'
FILES = ['LICENSE', 'config.json', 'low_latency/model_encoder.onnx',
         'low_latency/model_decoder.onnx', 'low_latency/observation_config.yaml']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    url = f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true'
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    if metadata['sha'] != REVISION:
        raise ValueError('Revision mismatch')
    siblings = {item['rfilename']: item for item in metadata['siblings']}
    report = dict(repo=REPO, revision=REVISION, variant='low_latency',
                  robot_commands_sent=False, inference_performed=False, files={})
    for name in FILES:
        item = siblings[name]
        target = args.output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}', timeout=60) as response, target.open('xb') as output:
            while chunk := response.read(1024*1024):
                output.write(chunk); digest.update(chunk); size += len(chunk)
        if size != item['size']:
            raise ValueError('Size mismatch: '+name)
        if item.get('lfs') and digest.hexdigest() != item['lfs']['sha256']:
            raise ValueError('LFS hash mismatch: '+name)
        if not item.get('lfs'):
            blob = b'blob '+str(size).encode()+b'\0'+target.read_bytes()
            if hashlib.sha1(blob).hexdigest() != item['blobId']:
                raise ValueError('Git blob hash mismatch: '+name)
        report['files'][name] = dict(size=size,sha256=digest.hexdigest())
        print(name, size, digest.hexdigest(), flush=True)
    (args.output/'download-manifest.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__': main()
