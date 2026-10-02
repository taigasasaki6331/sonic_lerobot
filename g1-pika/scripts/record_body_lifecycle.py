"""Replay saved body inputs through an abstract startup/watchdog lifecycle.

No robot, GPU, sockets, SDK, physical simulation or actuator adapter is used.
The caller's clock is an accelerated diagnostic timeline, NOT live freshness.
Diagnostic ownership acknowledgements are synthetic and explicitly labeled.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import BodyLifecycle, LifecycleFault, ACK_KIND, DEFAULT, settings
from body_lifecycle_profile import load_profile
from sonic_startup_ablation import ROOT, SOURCE_REPORT_SHA, sha, save
from sonic_process import strict_message
from verify_online_record import verify, checked_file

SCHEMA = 'saved_body_lifecycle_replay_not_physical_control'


def replay(frames, profile, config):
    if not frames: raise ValueError('No saved body frames')
    controller = BodyLifecycle('saved-body-lifecycle-diagnostic',profile,config)
    epoch = frames[0]['receive_monotonic_s']
    times = [frame['receive_monotonic_s']-epoch for frame in frames]
    if any(b<=a for a,b in zip(times,times[1:])): raise ValueError('Reversed saved source clock')
    controller.observe(frames[0],now=0.,source_age_s=0.)
    controller.request_takeover(now=0.)
    controller.confirm_takeover(session=controller.session,kind=ACK_KIND,now=0.)
    controller.begin_initialization(now=0.)
    next_frame = 1; stop_fault = None; commands = []
    # Allow the input deadline to expire after the final real saved sample.
    # Do not invent/repeat body observations to finish INIT or settle dwell.
    end = times[-1]+config['max_body_age_s']+2*config['writer_period_s']
    for index in range(int(end/config['writer_period_s'])+1):
        now = index*config['writer_period_s']
        try:
            while next_frame<len(frames) and times[next_frame]<=now:
                controller.observe(frames[next_frame],now=now,source_age_s=now-times[next_frame])
                controller.refresh_ownership(session=controller.session,kind=ACK_KIND,now=now)
                next_frame += 1
            commands.append(controller.writer_tick(now=now))
        except LifecycleFault as exc:
            stop_fault = str(exc); break
    before_stop = controller.status(); before_count = controller.writer_seq+1
    controller.request_stop('end_saved_replay')
    rejected_after_stop = False
    try: controller.writer_tick(now=controller.now)
    except LifecycleFault: rejected_after_stop = True
    controller.acknowledge_stop(session=controller.session,kind=ACK_KIND)
    controller.confirm_return(session=controller.session,kind=ACK_KIND)
    successful_protocol_check = (next_frame==len(frames) and stop_fault=='body_watchdog_expired'
        and controller.control_seq==-1 and rejected_after_stop and controller.writer_seq+1==before_count)
    return dict(schema_version=1,scope=SCHEMA,diagnostic_protocol_passed=successful_protocol_check,
        hardware_ready=False,robot_commands_sent=False,g1_connected=False,
        source_kind='saved_body; no executed feedback; synthetic diagnostic ACKs',
        clock_scope='accelerated saved source timeline, not live elapsed-time performance',
        saved_body_count=len(frames),body_count_consumed=next_frame,writer_record_count=before_count,
        control_target_count=controller.control_seq+1,stop_fault=stop_fault,status_before_stop=before_stop,
        command_after_stop_rejected=rejected_after_stop,final_status=controller.status(),events=list(controller.events)), commands


def verify_saved(directory):
    directory = Path(directory); report = strict_message((directory/'report.json').read_bytes())
    if (report.get('scope')!=SCHEMA or type(report.get('schema_version')) is not int or report.get('schema_version')!=1
            or report.get('hardware_ready') is not False or report.get('robot_commands_sent') is not False
            or report.get('g1_connected') is not False or report.get('diagnostic_protocol_passed') is not True):
        raise ValueError('Unsupported or incomplete lifecycle diagnostic')
    files = {}
    for name in ('profile.json','config.json','source-body.json','commands.jsonl'):
        files[name]=sha(directory/name)
    if files != report['output_file_sha256']: raise ValueError('Lifecycle record checksum mismatch')
    profile = strict_message((directory/'profile.json').read_bytes())
    config = settings(strict_message((directory/'config.json').read_bytes()))
    frames = strict_message((directory/'source-body.json').read_bytes())['frames']
    result, commands = replay(frames,profile,config)
    for key,value in result.items():
        if report[key]!=value: raise ValueError('Recalculated lifecycle differs: '+key)
    saved = [strict_message(line) for line in (directory/'commands.jsonl').read_bytes().splitlines()]
    if saved != commands: raise ValueError('Lifecycle command journal differs')
    return dict(integrity_passed=True,record_count=len(saved),physical_stop_validated=False,
                hardware_ready=False,robot_commands_sent=False,scope='saved_lifecycle_record_integrity_only')


def run(report_path, config_path):
    report_path=Path(report_path); config_path=Path(config_path)
    if sha(report_path)!=SOURCE_REPORT_SHA: raise ValueError('Unexpected input record')
    integrity=verify(report_path); report=strict_message(report_path.read_bytes())
    frames=[strict_message(checked_file(report_path.parent,out['body_input_record'],r'body-[0-9]{4}\.json'))['body_history'][-1]
            for out in report['outputs']]
    if len(frames)!=150: raise ValueError('Require pinned complete source record')
    config=settings(strict_message(config_path.read_bytes())); profile=load_profile()
    result, commands=replay(frames,profile,config)
    parent=ROOT/'artifacts/body-lifecycle'; parent.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    save(directory/'profile.json',profile); save(directory/'config.json',config)
    save(directory/'source-body.json',dict(frames=frames,source_report_sha256=sha(report_path),robot_commands_sent=False))
    with (directory/'commands.jsonl').open('x') as file:
        for command in commands: file.write(json.dumps(command,allow_nan=False,separators=(',',':'))+'\n')
    result.update(source_report_sha256=sha(report_path),source_config_sha256=sha(config_path),input_integrity=integrity,
        source_files={str(path):sha(path) for path in (Path(__file__),Path(__file__).with_name('body_lifecycle.py'),
                                                     Path(__file__).with_name('body_lifecycle_profile.py'))},
        output_file_sha256={name:sha(directory/name) for name in ('profile.json','config.json','source-body.json','commands.jsonl')})
    save(directory/'report.json',result)
    if result['diagnostic_protocol_passed']: save(directory/'integrity.json',verify_saved(directory))
    print(json.dumps({key:value for key,value in result.items() if key not in ('events','source_files')},indent=2))
    print('Saved:',directory)
    return 0 if result['diagnostic_protocol_passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/full-record/run-b5do1ocs/outputs/report.json')
    parser.add_argument('--config',type=Path,default=DEFAULT)
    parser.add_argument('--verify',type=Path,help='Recalculate an existing saved lifecycle run; no outputs written')
    args=parser.parse_args()
    if args.verify: print(json.dumps(verify_saved(args.verify),indent=2)); return 0
    return run(args.report,args.config)


if __name__=='__main__': raise SystemExit(main())
