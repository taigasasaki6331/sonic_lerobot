"""Lossless recorded RGB/state packets for a simulated G1; no camera access."""
import argparse
import base64
import io
import hashlib
import zlib
import json
from pathlib import Path
import sys
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frames', type=int, default=30)
    p.add_argument('--preprocessed', action='store_true', help='Lossless float32 of shared training resize')
    a = p.parse_args()
    if not 1 <= a.frames <= 206:
        p.error('Validation episode 39, frames 1..206 only')
    from train_rgb_smoke import runtime, DATASET, CAMERAS, rgb_input
    with redirect_stdout(sys.stderr):
        commit = runtime()
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        from PIL import Image
        ds = LeRobotDataset('data', root=DATASET, episodes=[39], return_uint8=True, video_backend='pyav')
        a.output.mkdir(parents=True, exist_ok=False)
        for seq in range(a.frames):
            item = ds[seq]
            if int(item['frame_index']) != seq or int(item['episode_index']) != 39:
                raise ValueError('Recorded frame mismatch')
            images = {}
            resized = rgb_input(item) if a.preprocessed else None
            for key in CAMERAS:
                if a.preprocessed:
                    raw = resized[key].numpy().astype('<f4').tobytes()
                    blob = zlib.compress(raw)
                    if zlib.decompress(blob) != raw: raise ValueError('Float image roundtrip mismatch')
                else:
                    buf = io.BytesIO()
                    Image.fromarray(item[key].permute(1, 2, 0).numpy()).save(buf, format='PNG')
                    blob = buf.getvalue()
                images[key] = base64.b64encode(blob).decode()
            packet = {'seq': seq, 'timestamp': float(item['timestamp']),
                      'state': item['observation.state'].tolist(), 'images': images}
            if a.preprocessed:
                packet.update(image_encoding='rgb_input_float32_zlib_v1',
                              preprocessing_sha256=hashlib.sha256((ROOT / 'scripts/train_rgb_smoke.py').read_bytes()).hexdigest())
            (a.output / f'{seq:04d}.json').write_text(json.dumps(packet, allow_nan=False))
    (a.output / 'manifest.json').write_text(json.dumps({'frames': a.frames, 'fps': 30,
        'episode': 39, 'lerobot_commit': commit, 'source': 'recorded_not_live_camera'}))


if __name__ == '__main__':
    main()
