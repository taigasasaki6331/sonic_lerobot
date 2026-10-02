"""Resolve only three pinned x86 build libraries in a private staged copy."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

COMMIT = '087f9ac01d46f6d8e4d0b73c01ae64799f292a38'
RELATIVE = ['lib/x86_64/libunitree_sdk2.a', 'thirdparty/lib/x86_64/libddsc.so',
            'thirdparty/lib/x86_64/libddscxx.so']


def main():
    root = Path(sys.argv[1]).resolve()
    prefix = 'gear_sonic_deploy/thirdparty/unitree_sdk2/'
    report = {}
    for rel in RELATIVE:
        path = root/prefix/rel
        with path.open('rb') as f: pointer = f.read(256)
        if pointer.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            fields = dict(line.split(' ', 1) for line in pointer.decode().splitlines())
            expected = fields['oid'].removeprefix('sha256:')
            expected_size = int(fields['size'])
            url = f'https://media.githubusercontent.com/media/NVlabs/GR00T-WholeBodyControl/{COMMIT}/{prefix}{rel}'
            tmp = path.with_name(path.name+'.download')
            digest = hashlib.sha256(); size = 0
            with urllib.request.urlopen(url,timeout=60) as response, tmp.open('xb') as output:
                while chunk := response.read(1024*1024):
                    output.write(chunk); digest.update(chunk); size += len(chunk)
            if size != expected_size or digest.hexdigest() != expected:
                raise ValueError('LFS verification failed: '+rel)
            tmp.replace(path)
        report[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root/'resolved-lfs-sha256.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
