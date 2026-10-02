"""Bounded simulated-G1 inference service. No DDS, serial or robot output."""
import argparse
import base64
from contextlib import redirect_stdout
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zmq_transport import ZmqChannel


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--accept-ip', required=True)
    p.add_argument('--session', required=True)
    p.add_argument('--frames', type=int, default=30)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    p.add_argument('--fault', choices=['none', 'stale', 'disconnect', 'delay'], default='none')
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--idle-timeout', type=int, default=15)
    p.add_argument('--publish-endpoint', help='GPU-local action publication for nonblocking WBC')
    a = p.parse_args()
    if not 1 <= a.frames <= 206 or len(a.session) != 32 or not 1 <= a.idle_timeout <= 120:
        p.error('Invalid bounded session')
    root = a.root.resolve()
    if sys.version_info[:3] != (3, 12, 13):
        raise RuntimeError('Python 3.12.13 required')
    lock = root / ('requirements-gpu.lock' if a.device == 'cuda' else 'requirements-policy.lock')
    for line in lock.read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name, version = line.split('==')
            if importlib.metadata.version(name) != version:
                raise RuntimeError('Dependency mismatch: ' + name)
    source = root / 'vendor/lerobot'
    commit = json.loads((root / 'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != commit:
        raise RuntimeError('LeRobot commit mismatch')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD'], check=True)
    os.environ.update(HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    sys.path[:0] = [str(root / 'scripts'), str(source / 'src')]
    from train_rgb_smoke import rgb_input, CAMERAS
    from gripper_codec import decode_action
    from wbc_state import WbcState
    import numpy as np
    import torch
    from PIL import Image
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    if a.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no fallback')
    torch.set_num_threads(4)
    checkpoint = root / 'artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model'
    codec = json.loads((checkpoint / 'action_codec.json').read_text())
    if hashlib.sha256((root / 'scripts/gripper_codec.py').read_bytes()).hexdigest() != codec['codec_script_sha256']:
        raise RuntimeError('Codec mismatch')
    cfg = ACTConfig.from_pretrained(str(checkpoint), local_files_only=True)
    cfg.device = a.device
    cfg.pretrained_backbone_weights = None
    if cfg.chunk_size != 1 or cfg.n_action_steps != 1:
        raise RuntimeError('Expected h1 ACT')
    with redirect_stdout(sys.stderr):
        policy = ACTPolicy.from_pretrained(str(checkpoint), config=cfg, local_files_only=True, strict=True).eval()
    pre, post = make_pre_post_processors(cfg, pretrained_path=str(checkpoint),
        preprocessor_overrides={'device_processor': {'device': a.device}},
        postprocessor_overrides={'device_processor': {'device': a.device}})
    channel = ZmqChannel(a.endpoint, server=True, timeout_ms=a.idle_timeout * 1000,
                         accept_filter=a.accept_ip + '/32', max_message_bytes=2000000)
    records = []
    publisher = ZmqChannel(a.publish_endpoint, server=True, kind='pub', timeout_ms=100) if a.publish_endpoint else None
    metadata = {'ready': True, 'fps': 30, 'frames': a.frames, 'session': a.session,
                'device': a.device, 'lerobot_commit': commit,
                'model_sha256': hashlib.sha256((checkpoint / 'model.safetensors').read_bytes()).hexdigest(),
                'codec': codec['mode'], 'observation_source': 'recorded_RGB_and_state_plus_sim_body',
                'robot_commands_sent': False, 'hardware_ready': False}
    print(json.dumps(metadata), flush=True)
    reason = 'not_finished'
    connected = False
    try:
        while True:
            packet = channel.read()
            if packet.get('session') != a.session:
                raise ValueError('Wrong session')
            if packet.get('op') == 'hello' and not connected:
                connected = True
                channel.send(metadata)
                continue
            if packet.get('op') == 'stop':
                channel.send({'stopped': True, 'session': a.session})
                reason = 'client_stop'
                break
            seq = packet.get('seq')
            if not connected or type(seq) is not int or seq != len(records) or seq >= a.frames:
                raise ValueError('Unexpected request sequence')
            body = packet['body'].copy()
            if body.pop('source') != 'simulation_not_G1':
                raise ValueError('Only simulation input allowed')
            state_body = WbcState(**body).validate(body['names'])
            if records and state_body.time <= records[-1]['body_time']:
                raise ValueError('Stale simulated body state')
            state = torch.tensor(packet['state'], dtype=torch.float32)
            if state.shape != (10,) or not torch.isfinite(state).all() or not 0 <= state[9] <= .1:
                raise ValueError('Invalid recorded policy state')
            if abs(packet['timestamp'] - seq / 30) > 1e-5:
                raise ValueError('Invalid recorded timestamp')
            if seq == 5 and a.fault == 'disconnect':
                reason = 'injected_disconnect'
                break
            if seq == 5 and a.fault == 'delay':
                time.sleep(.8)
            item = {'observation.state': state}
            resized = packet.get('image_encoding') == 'rgb_input_float32_zlib_v1'
            if resized and packet.get('preprocessing_sha256') != hashlib.sha256((root / 'scripts/train_rgb_smoke.py').read_bytes()).hexdigest():
                raise ValueError('Preprocessing hash mismatch')
            for key in CAMERAS:
                blob = base64.b64decode(packet['images'][key], validate=True)
                if resized:
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(blob, 3 * 96 * 128 * 4 + 1)
                    if len(raw) != 3 * 96 * 128 * 4 or not decoder.eof or decoder.unused_data:
                        raise ValueError('Invalid bounded float image')
                    array = np.frombuffer(raw, dtype='<f4').reshape(3, 96, 128).copy()
                    if not np.isfinite(array).all() or array.min() < 0 or array.max() > 1:
                        raise ValueError('Float RGB outside bounds')
                    item[key] = torch.from_numpy(array)
                else:
                    with Image.open(io.BytesIO(blob)) as image:
                        if image.size != (640, 480) or image.format != 'PNG':
                            raise ValueError('Expected lossless 640x480 PNG')
                        array = np.asarray(image.convert('RGB')).copy()
                    item[key] = torch.from_numpy(array).permute(2, 0, 1)
            with torch.inference_mode():
                policy.reset()
                if a.device == 'cuda': torch.cuda.synchronize()
                started = time.perf_counter()
                raw = post(policy.select_action(pre(item if resized else rgb_input(item)))).reshape(10).cpu()
                action = decode_action(raw, state, codec['mode'])
                if a.device == 'cuda': torch.cuda.synchronize()
            if not torch.isfinite(action).all():
                raise ValueError('Nonfinite policy action')
            response = {'session': a.session, 'seq': seq, 'timestamp': packet['timestamp'],
                        'action': action.tolist(), 'inference_ms': (time.perf_counter() - started) * 1000}
            response['issued_monotonic_s'] = time.monotonic()
            response['model_sha256'] = metadata['model_sha256']
            response['lerobot_commit'] = commit
            records.append({'seq': seq, 'body_time': state_body.time,
                            'body_sha256': hashlib.sha256(json.dumps(packet['body'], sort_keys=True).encode()).hexdigest(),
                            'response': response.copy()})
            if seq == 5 and a.fault == 'stale': response['session'] = 'obsolete-session'
            if publisher: publisher.send(response)
            channel.send(response)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        reason = type(exc).__name__ + ': ' + str(exc)
    finally:
        channel.close()
        if publisher: publisher.close()
        a.report.write_text(json.dumps({'metadata': metadata, 'records': records,
                                       'termination': reason, 'fault': a.fault}, indent=2))


if __name__ == '__main__': main()
