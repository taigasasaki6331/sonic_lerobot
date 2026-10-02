"""GPU-only archived image reinference via existing isolated ACT worker, no G1."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--policy-bundle', type=Path, help='Default ROOT/config/policy-bundle.json')
    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=False)
    raw = args.record.read_bytes()
    original = json.loads(raw)
    if not original['passed'] or len(original['frames']) != 30: raise ValueError('Invalid source record')
    packets = []
    for seq, index in enumerate((0,29)):
        packet = copy.deepcopy(original['frames'][index]['capture'])
        packet['seq'] = seq
        for role, image in packet['images'].items():
            blob = (args.images/f'{index:02d}-{role}.jpg').read_bytes()
            if hashlib.sha256(blob).hexdigest() != image['sha256']:
                raise ValueError('Saved image checksum mismatch')
            image['jpeg'] = base64.b64encode(blob).decode()
        packets.append(packet)
    payload = '\n'.join(json.dumps(p) for p in packets)+'\n'+json.dumps({'stop':True})+'\n'
    command = [str(args.root/'.venv-gpu/bin/python'), '-I',
               str(Path(__file__).with_name('probe_gpu_images.py')), '--root', str(args.root),
               '--images', str(args.output_dir), '--packet-width', '--stream', '--frames', '2']
    if args.policy_bundle: command += ['--policy-bundle', str(args.policy_bundle)]
    result = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=180)
    (args.output_dir/'worker.stderr.log').write_text(result.stderr)
    (args.output_dir/'worker.stdout.jsonl').write_text(result.stdout)
    if result.returncode: raise RuntimeError('ACT worker failed; see saved logs')
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    if len(replies) != 3 or not replies[0].get('ready'): raise ValueError('Worker response mismatch')
    if replies[0]['model_sha256'] != original['gpu']['model_sha256']:
        raise ValueError('Checkpoint differs from original capture')
    frames = []
    for seq, index in enumerate((0,29)):
        response = replies[seq+1]
        if response['seq'] != seq: raise ValueError('Inference sequence mismatch')
        frame = copy.deepcopy(original['frames'][index])
        frame.update(response)
        frame['source_frame_index'] = index
        frame['capture']['seq'] = seq
        frames.append(frame)
    report = dict(passed=True, scope='archived_two_image_pairs_reinferred_not_live',
                  hardware_ready=False, robot_commands_sent=False, camera_stream_started=False,
                  source_sha256=hashlib.sha256(raw).hexdigest(), gpu=replies[0], frames=frames)
    (args.output_dir/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Reinferred archived frames 0 and 29; no live acquisition or commands')


if __name__ == '__main__': main()
