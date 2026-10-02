"""Prepare allowlisted PUBLIC snapshot payload for GitHub Git data APIs.

No network, credentials, Git ref edits, or uploads. Chunk output keeps large
source content out of conversation text; the calling tool passes it directly.
"""
import argparse
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_cloud_source import verify


def prepare(snapshot, output):
    verify(snapshot)
    manifest = json.loads((snapshot / 'cloud-source-manifest.json').read_bytes())
    if manifest.get('public_copy') is not True: raise ValueError('PUBLIC copy required')
    entries = []
    for name in sorted([*manifest['files'], 'cloud-source-manifest.json']):
        raw = (snapshot / name).read_bytes()
        binary = name.lower().endswith('.stl')
        entries.append(dict(path='g1-pika/' + name, encoding='base64' if binary else 'utf-8',
                            content=base64.b64encode(raw).decode() if binary else raw.decode()))
    with output.open('x') as stream: json.dump(entries, stream, ensure_ascii=True, separators=(',', ':'))
    return dict(files=len(entries), characters=output.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--offset', type=int)
    parser.add_argument('--length', type=int, default=50000)
    args = parser.parse_args()
    if args.offset is None:
        if not args.snapshot: parser.error('--snapshot required for preparation')
        result = prepare(args.snapshot, args.payload)
    else:
        if args.offset < 0 or not 1 <= args.length <= 50000: parser.error('Invalid chunk')
        with args.payload.open() as stream:
            stream.seek(args.offset); chunk = stream.read(args.length)
        result = dict(offset=args.offset, chunk=chunk)
    print(json.dumps(result))


if __name__ == '__main__': main()
