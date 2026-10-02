"""Read-only integrity audit of an online/fixture record; not hardware approval."""
import argparse
import hashlib
import math
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_process import strict_message
from state_history import validate_history


def checked_file(root,reference,pattern):
    name=reference['file']
    if not isinstance(name,str) or not re.fullmatch(pattern,name): raise ValueError('Unexpected record filename')
    path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()): raise ValueError('Record path escapes archive')
    if path.stat().st_size>2_000_000: raise ValueError('Oversized input record')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']: raise ValueError('Record hash mismatch: '+name)
    return raw


def vector(value,size):
    if len(value)!=size or any(type(v) not in (float,int) or not math.isfinite(v) for v in value):
        raise ValueError('Invalid recorded numeric vector')


def verify(path):
    path=Path(path); root=path.parent; report=strict_message(path.read_bytes())
    scopes=('online_measured_inputs_SONIC_record_only','online_coordinator_with_SYNTHETIC_input_IO_fixture_real_models')
    if report.get('scope') not in scopes or report.get('passed') is not True: raise ValueError('Complete supported record required')
    if report.get('robot_commands_sent') is not False or report.get('hardware_ready') is not False: raise ValueError('Record-only status required')
    if report.get('worker_exit_codes')!=[0,0,0,0]: raise ValueError('Worker shutdown not confirmed')
    policies=report['policy_records']; outputs=report['outputs']; images=set()
    if len(policies)!=report['policy_count'] or len(outputs)!=report['control_count'] or not policies or not outputs:
        raise ValueError('Record count mismatch')
    for seq,policy in enumerate(policies):
        if policy['seq']!=seq or policy['action']['seq']!=seq: raise ValueError('Policy sequence mismatch')
        vector(policy['action']['action'],10)
        capture=strict_message(checked_file(root,policy['capture'],r'capture-[0-9]{4}\.json'))
        if capture['seq']!=seq or capture.get('robot_commands_sent') is not False: raise ValueError('Capture identity')
        if validate_history(capture['g1_state_history'])[-1]!=capture['g1_state']: raise ValueError('Capture history endpoint')
        for reference in capture['images'].values():
            checked_file(root,reference,r'image-[0-9a-f]{64}\.jpg'); images.add(reference['file'])
    previous=None
    for seq,output in enumerate(outputs):
        if output['seq']!=seq or type(output['policy_seq']) is not int or not 0<=output['policy_seq']<len(policies):
            raise ValueError('Control sequence/reference')
        body=strict_message(checked_file(root,output['body_input_record'],r'body-[0-9]{4}\.json'))
        history=validate_history(body['body_history'])
        if body['seq']!=seq or history[-1]['tick']!=output['source_body_tick']: raise ValueError('Body record identity')
        if previous is not None and previous[1:]!=history[:-1]: raise ValueError('Recorded body windows do not overlap consistently')
        previous=history
        result=output['diagnostic_output']
        vector(result['raw_action_isaaclab'],29); vector(result['q_target_hardware'],29)
        if result.get('gripper_actuated') is not False or result.get('gripper_width_m')!=policies[output['policy_seq']]['action']['action'][9]:
            raise ValueError('Recorded width channel mismatch')
    return dict(integrity_passed=True,source_scope=report['scope'],policy_records=len(policies),
                body_records=len(outputs),unique_image_files=len(images),hardware_ready=False,
                declared_input_kind='online_sensor' if report['scope']==scopes[0] else 'synthetic_fixture',
                limitation='File integrity only; source scope is reported provenance, not independent sensor/physical validation')


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    import json
    print(json.dumps(verify(args.report),indent=2))


if __name__=='__main__': main()
