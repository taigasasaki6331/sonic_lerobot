"""File-only analysis of computed SONIC targets; never approves robot motion."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_online_record import verify,checked_file,vector
from sonic_process import strict_message

ROOT=Path(__file__).resolve().parents[1]
PARAMETERS=ROOT/'vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/policy_parameters.hpp'
PARAMETERS_SHA='b9332adf07c2c9b75c9b1e0756e57c7a1c2a890d8bb0aa53c3f1905fb739b791'


def joint_limits(urdf):
    raw=PARAMETERS.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PARAMETERS_SHA: raise ValueError('Pinned joint order changed')
    block=re.search(r'default_angles\s*=\s*\{([^}]+)\}',raw.decode()).group(1)
    names=re.findall(r'//\s*(\w+_joint)',block)
    if len(names)!=29 or len(set(names))!=29: raise ValueError('Joint order schema')
    tree=ET.fromstring(Path(urdf).read_bytes()); result=[]
    for name in names:
        joints=[joint for joint in tree.findall('joint') if joint.get('name')==name]
        if len(joints)!=1: raise ValueError('Missing/duplicate URDF joint '+name)
        limit=joints[0].find('limit')
        low,high=float(limit.attrib['lower']),float(limit.attrib['upper'])
        if not math.isfinite(low) or not math.isfinite(high) or low>=high: raise ValueError('Invalid URDF limit')
        result.append(dict(name=name,lower_rad=low,upper_rad=high))
    return result


def summarize(rows,limits):
    if not rows: raise ValueError('No computed targets')
    width=len(limits); results=[]
    for row in rows:
        for field in ('measured','target'): vector(row[field],width)
    for i,limit in enumerate(limits):
        measured=[row['measured'][i] for row in rows]; target=[row['target'][i] for row in rows]
        offsets=[abs(a-b) for a,b in zip(measured,target)]
        peak=max(range(len(rows)),key=offsets.__getitem__)
        outside=lambda values:[k for k,v in enumerate(values) if v<limit['lower_rad'] or v>limit['upper_rad']]
        results.append(dict(**limit,initial_target_offset_rad=offsets[0],
            max_target_offset_rad=offsets[peak],max_offset_control_seq=rows[peak]['seq'],
            max_target_step_rad=max((abs(b-a) for a,b in zip(target,target[1:])),default=0.),
            target_min_rad=min(target),target_max_rad=max(target),
            measured_outside_urdf_count=len(outside(measured)),target_outside_urdf_count=len(outside(target))))
    return results


def audit(path,urdf):
    path=Path(path); integrity=verify(path); report=strict_message(path.read_bytes())
    rows=[]
    for out in report['outputs']:
        body=strict_message(checked_file(path.parent,out['body_input_record'],r'body-[0-9]{4}\.json'))
        rows.append(dict(seq=out['seq'],measured=body['body_history'][-1]['q'][:29],
                         target=out['diagnostic_output']['q_target_hardware']))
    joints=summarize(rows,joint_limits(urdf))
    return dict(scope='offline_computed_target_audit_not_motion_approval',hardware_ready=False,
        robot_commands_sent=False,source_report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        urdf_sha256=hashlib.sha256(Path(urdf).read_bytes()).hexdigest(),joint_order_sha256=PARAMETERS_SHA,
        input_integrity=integrity,control_count=len(rows),joints=joints,
        max_offset_joint=max(joints,key=lambda x:x['max_target_offset_rad']),
        target_limit_violations=[j['name'] for j in joints if j['target_outside_urdf_count']],
        measured_limit_violations=[j['name'] for j in joints if j['measured_outside_urdf_count']],
        initial_ik_projected_joints=report['policy_records'][0].get('ik',{}).get('measured_outside_upstream_ik_limits',[]),
        unresolved=['Physical stop and control ownership not validated',
                    'Initial-pose transition and collision clearance not validated',
                    'IK endpoint hold is not a dynamic whole-body trajectory',
                    'Computed action history was not executed by the robot'],
        interpretation='Targets were NOT sent: offset is not tracking error or measured motion. URDF limits are model checks, not certified hardware limits.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--urdf',type=Path,default=ROOT/'artifacts/models/g1_pika_closed.urdf')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=audit(args.report,args.urdf)
    with args.output.open('x') as file: json.dump(result,file,indent=2,allow_nan=False); file.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='joints'},indent=2))


if __name__=='__main__': main()
