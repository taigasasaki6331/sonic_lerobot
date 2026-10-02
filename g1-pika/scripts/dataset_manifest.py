"""Create/verify a file-level SHA256 manifest without modifying a dataset."""
import argparse
import hashlib
import json
from pathlib import Path


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlink forbidden: {path}')
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024), b''):
                    digest.update(block)
            result[path.relative_to(root).as_posix()] = {
                'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
    if not result or 'meta/info.json' not in result:
        raise ValueError('Not a dataset')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['create','verify'])
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    args = parser.parse_args()
    root = args.dataset.resolve(strict=True)
    if args.manifest.resolve().is_relative_to(root):
        parser.error('Manifest must be outside source dataset')
    current = inventory(root)
    if args.mode == 'create':
        with args.manifest.open('x') as stream:
            json.dump({'format':1,'files':current},stream,indent=2)
            stream.write('\n')
    elif current != json.loads(args.manifest.read_text())['files']:
        raise ValueError('Dataset file set, sizes or hashes differ')
    print(json.dumps({'status':'passed','mode':args.mode,'files':len(current),
        'bytes':sum(x['bytes'] for x in current.values()),
        'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
