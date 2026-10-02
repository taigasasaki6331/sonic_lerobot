"""Rebuild SONIC inputs from a verified saved online run; no live IO."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_online_record import verify,checked_file
from sonic_process import strict_message
from sonic_observation import ObservationBuilder
from sonic_joint_trajectory import JointTrajectory


def prepare(path,mode,transition_s=.4):
    if mode not in ('recorded_ik','measured_hold','causal_quintic_ik'): raise ValueError('Unknown reference ablation')
    path=Path(path); verify(path); report=strict_message(path.read_bytes()); rows=[]
    builder=ObservationBuilder(); captures={}; trajectory=None; last_policy=-1; epoch=None
    reference_rows=[]; replan_continuity=0.
    for out in report['outputs']:
        index=out['policy_seq']; policy=report['policy_records'][index]
        if index not in captures:
            captures[index]=strict_message(checked_file(path.parent,policy['capture'],r'capture-[0-9]{4}\.json'))
        capture=captures[index]
        body=strict_message(checked_file(path.parent,out['body_input_record'],r'body-[0-9]{4}\.json'))['body_history']
        q=np.asarray([b['q'][:29] for b in body]); dq=np.asarray([b['dq'][:29] for b in body])
        quat=np.asarray([b['quaternion'] for b in body]); quat/=np.linalg.norm(quat,axis=1)[:,None]
        refq=policy['ik']['q_reference_hardware'] if mode!='measured_hold' else q[-1]
        refquat=np.asarray(capture['g1_state']['quaternion']) if mode!='measured_hold' else quat[-1]
        refquat=refquat/np.linalg.norm(refquat)
        reference_q=np.tile(refq,(10,1)); reference_dq=np.zeros((10,29))
        if mode=='causal_quintic_ik':
            # Use only the source clock. Activation is the first observed policy use,
            # not an invented GPU publish timestamp or a future policy sample.
            stamp=body[-1]['receive_monotonic_s']
            if epoch is None: epoch=stamp
            now=float(stamp-epoch)
            if trajectory is None:
                trajectory=JointTrajectory(q[-1],dq[-1],now=now,duration_s=transition_s)
            if index!=last_policy:
                before=trajectory.sample(now)
                trajectory.update(refq,now=now)
                after=trajectory.sample(now)
                replan_continuity=max(replan_continuity,max(float(np.max(abs(a-b))) for a,b in zip(before,after)))
                last_policy=index
            reference_q,reference_dq,reference_ddq=trajectory.window(now=now)
            reference_rows.append(dict(seq=out['seq'],policy_seq=index,source_elapsed_s=now,
                q_hardware=reference_q.tolist(),dq_hardware=reference_dq.tolist(),
                ddq_hardware=reference_ddq.tolist()))
        rows.append(dict(seq=out['seq'],measured_q=q[-1].tolist(),gripper_width_m=policy['action']['action'][9],
            gripper_actuated=False,encoder=builder.encoder(reference_q,reference_dq,
                np.tile(refquat,(10,1)),quat[-1]).tolist(),
            decoder_tail=builder.decoder_tail(q,dq,[b['gyroscope'] for b in body],quat,np.zeros((10,29))).tolist()))
    result=dict(scope='diagnostic_real_body_history_zero_prior_actions',frames=rows,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reference=mode,
        history='saved_real_windows_with_zero_or_recomputed_prior_actions_not_executed_actions',
        hardware_ready=False,robot_commands_sent=False,skipped_windows=0)
    if mode=='causal_quintic_ik':
        result.update(reference_windows=reference_rows,transition_s=transition_s,
            q_dq_ddq_replan_max_discontinuity=replan_continuity,
            activation_clock='saved_source_clock_first_observed_policy_use_not_original_GPU_publish_time',
            limitation='Joint interpolation only; orientation endpoint held; no balance/contact/collision/rate limits')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--mode',choices=('recorded_ik','measured_hold','causal_quintic_ik'),required=True)
    p.add_argument('--transition-seconds',type=float,default=.4,help='Diagnostic interpolation duration, not a hardware limit')
    p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    result=prepare(args.report,args.mode,args.transition_seconds)
    with args.output.open('x') as f: json.dump(result,f,allow_nan=False)
    print('Prepared',len(result['frames']),'saved windows:',args.mode)


if __name__=='__main__': main()
