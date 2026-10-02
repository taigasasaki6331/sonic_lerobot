"""File-only joint-reference extrema audit. No GPU, device, physics or motor IO."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_motion_record import joint_limits, ROOT
from sonic_joint_trajectory import JointTrajectory
from verify_online_record import verify, checked_file


def audit(path,urdf,duration):
    path=Path(path); integrity=verify(path); raw=path.read_bytes(); report=json.loads(raw)
    limits=joint_limits(urdf); tree=ET.fromstring(Path(urdf).read_bytes())
    velocity=[]
    for joint in limits:
        value=float(tree.find("joint[@name='"+joint['name']+"']/limit").attrib['velocity'])
        if not np.isfinite(value) or value<=0: raise ValueError('Invalid URDF velocity')
        velocity.append(value)
    trajectory=None; epoch=None; previous_policy=-1
    extrema=[]
    for output in report['outputs']:
        body=json.loads(checked_file(path.parent,output['body_input_record'],r'body-[0-9]{4}\.json'))['body_history'][-1]
        if epoch is None: epoch=body['receive_monotonic_s']
        now=float(body['receive_monotonic_s']-epoch)
        if trajectory is None:
            trajectory=JointTrajectory(body['q'][:29],body['dq'][:29],now=now,duration_s=duration)
        index=output['policy_seq']
        if index!=previous_policy:
            trajectory.update(report['policy_records'][index]['ik']['q_reference_hardware'],now=now)
            previous_policy=index
        bounds=trajectory.extrema(begin=now,end=now+.18)
        extrema.append(bounds)
    joints=[]
    for i,limit in enumerate(limits):
        qmin=min(v['q_min'][i] for v in extrema); qmax=max(v['q_max'][i] for v in extrema)
        vmax=max(max(abs(v['dq_min'][i]),abs(v['dq_max'][i])) for v in extrema)
        amax=max(max(abs(v['ddq_min'][i]),abs(v['ddq_max'][i])) for v in extrema)
        joints.append(dict(**limit,q_reference_min_rad=float(qmin),q_reference_max_rad=float(qmax),
            max_reference_velocity_rad_s=float(vmax),urdf_velocity_rad_s=velocity[i],
            max_reference_acceleration_rad_s2=float(amax),
            position_outside_urdf=bool(qmin<limit['lower_rad']-1e-9 or qmax>limit['upper_rad']+1e-9),
            velocity_outside_urdf=bool(vmax>velocity[i]+1e-9)))
    return dict(scope='numerical_saved_reference_extrema_not_hardware_validation',
        robot_commands_sent=False,hardware_ready=False,source_sha256=hashlib.sha256(raw).hexdigest(),
        urdf_sha256=hashlib.sha256(Path(urdf).read_bytes()).hexdigest(),duration_s=duration,
        trajectory_code_sha256=hashlib.sha256(Path(__file__).with_name('sonic_joint_trajectory.py').read_bytes()).hexdigest(),
        input_integrity=integrity,windows=len(extrema),forecast_horizon_s=.18,joints=joints,
        position_violations=[j['name'] for j in joints if j['position_outside_urdf']],
        velocity_violations=[j['name'] for j in joints if j['velocity_outside_urdf']],
        acceleration_limit_validated=False,
        limitation='Numerical stationary roots, not formal bounds. URDF values are model limits; activation uses first saved policy use. No contact/collision/torque/physical response checked.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--urdf',type=Path,default=ROOT/'artifacts/models/g1_pika_closed.urdf')
    p.add_argument('--transition-seconds',type=float,default=.4)
    p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    result=audit(args.report,args.urdf,args.transition_seconds)
    with args.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='joints'},indent=2))
