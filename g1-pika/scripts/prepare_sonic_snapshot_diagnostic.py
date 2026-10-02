"""Explicit synthetic histories from saved real snapshots; no physical simulation.

Not a production observation adapter: repeats each snapshot 10 times and sets
unknown previous SONIC actions to zero. Never labels sparse data as actual 50Hz.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_observation import ObservationBuilder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--candidate-reference',type=Path,
                        help='Optional FAILED recorded-action IK diagnostic; never treats it as an approved trajectory')
    args=parser.parse_args()
    payload=json.loads(args.input.read_text())
    if not payload['passed'] or len(payload['frames'])!=30: raise ValueError('Incomplete real input record')
    candidate=None
    if args.candidate_reference:
        candidate=json.loads(args.candidate_reference.read_text())
        if (candidate['input_sha256'] != hashlib.sha256(args.input.read_bytes()).hexdigest()
                or candidate.get('lower_body_mode')!='measured'
                or candidate.get('target_source')!='recorded_action'
                or [r['seq'] for r in candidate['outputs']] != [f['seq'] for f in payload['frames']]):
            raise ValueError('Candidate source/sequence/semantics mismatch')
    builder=ObservationBuilder(); rows=[]; times=[]
    for frame in payload['frames']:
        body=frame['capture']['g1_state']; times.append(body['receive_monotonic_s'])
        q=np.tile(body['q'][:29],(10,1)); dq=np.tile(body['dq'][:29],(10,1))
        quat=np.tile(body['quaternion'],(10,1)); quat=quat/np.linalg.norm(quat,axis=1)[:,None]
        gyro=np.tile(body['gyroscope'],(10,1))
        reference=q
        if candidate is not None:
            reference=np.tile(candidate['outputs'][len(rows)]['q_target'],(10,1))
        encoder=builder.encoder(reference,np.zeros_like(q),quat,quat[-1])
        tail=builder.decoder_tail(q,dq,gyro,quat,np.zeros((10,29)))
        rows.append(dict(seq=frame['seq'],encoder=encoder.tolist(),decoder_tail=tail.tolist()))
    result=dict(scope='diagnostic_repeated_snapshot_not_50hz_history',
                source_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                measured_sample_gap_max_s=float(np.max(np.diff(times))),
                reference=('recorded_LeRobot_action_via_failed_IK_candidate_held_constant' if candidate is not None
                           else 'measured_pose_held_constant_not_LeRobot_action'),
                history='snapshot_repeated_10_times_last_action_zero_synthetic',frames=rows)
    if candidate is not None:
        result['candidate_sha256']=hashlib.sha256(args.candidate_reference.read_bytes()).hexdigest()
        result['candidate_original_passed']=candidate['passed']
        result['candidate_ik_error_max_m']=candidate['metrics']['ik_position_error_max_m']
    with args.output.open('x') as file: json.dump(result,file,allow_nan=False)


if __name__=='__main__': main()
