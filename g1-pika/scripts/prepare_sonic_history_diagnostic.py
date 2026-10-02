"""Real recorded body histories, held measured reference, zero prior actions.

Open-loop file diagnostic only: G1 did not execute these SONIC actions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_observation import ObservationBuilder


def prepare(raw):
    frames = [json.loads(line) for line in raw.splitlines()]
    builder = ObservationBuilder()
    rows = []
    skipped = 0
    for end in range(9, len(frames)):
        window = frames[end-9:end+1]
        stamps = [f['receive_monotonic_s'] for f in window]
        try:
            builder.require_50hz(stamps)
        except ValueError:
            skipped += 1
            continue
        if any(a['tick'] == b['tick'] for a, b in zip(window, window[1:])):
            raise ValueError('Repeated robot tick in history')
        q = np.asarray([f['q'][:29] for f in window])
        dq = np.asarray([f['dq'][:29] for f in window])
        quat = np.asarray([f['quaternion'] for f in window])
        norms = np.linalg.norm(quat, axis=1)
        if not np.isfinite(norms).all() or np.any(abs(norms-1) > .01):
            raise ValueError('Invalid measured quaternion norm')
        quat = quat / norms[:, None]
        gyro = np.asarray([f['gyroscope'] for f in window])
        encoder = builder.encoder(np.tile(q[-1], (10, 1)), np.zeros((10, 29)),
                                  np.tile(quat[-1], (10, 1)), quat[-1])
        tail = builder.decoder_tail(q, dq, gyro, quat, np.zeros((10, 29)))
        rows.append(dict(seq=end, timestamps=stamps, measured_q=q[-1].tolist(),
                         encoder=encoder.tolist(), decoder_tail=tail.tolist()))
    if not rows:
        raise ValueError('No valid ten-frame 50Hz history')
    return dict(scope='diagnostic_real_body_history_zero_prior_actions',
                source_sha256=hashlib.sha256(raw).hexdigest(),
                reference='latest_measured_pose_held_constant_not_LeRobot_action',
                history='measured_body_10_frames_zero_prior_SONIC_actions_not_closed_loop',
                quaternion_normalized=True, crc_verified=False,
                source_frames=len(frames), skipped_windows=skipped, frames=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.input.read_bytes())
    with args.output.open('x') as output:
        json.dump(result, output, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'frames'}, indent=2))
    print('Prepared windows:', len(result['frames']))


if __name__ == '__main__':
    main()
