"""Saved real SONIC -> body receiver -> lifecycle; no robot or physics.

Default is file-only. --ipc uses a LOCAL Unix socket and two threads only.
No live inference, G1 connection, DDS client/publisher, serial IO or takeover.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import BodyLifecycle, DEFAULT
from body_lifecycle_profile import load_profile
from sonic_body_bridge import SonicBodyBridge, BodyRecordWorker, BodyRecordClient, envelope
from sonic_process import strict_message
from sonic_startup_ablation import ROOT, SOURCE_REPORT_SHA, sha, save
from verify_online_record import verify, checked_file


def load_rows(path):
    if sha(path)!=SOURCE_REPORT_SHA: raise ValueError('Expected pinned real-input record')
    integrity=verify(path); report=strict_message(path.read_bytes()); rows=[]
    for out in report['outputs']:
        frame=strict_message(checked_file(path.parent,out['body_input_record'],r'body-[0-9]{4}\.json'))['body_history'][-1]
        rows.append(dict(seq=out['seq'],body=frame,sonic=out['diagnostic_output']))
    if len(rows)!=150: raise ValueError('Expected 150 complete SONIC/body pairs')
    return rows,integrity


def replay(rows, profile, config, *, ipc=False):
    epoch=rows[0]['body']['receive_monotonic_s']
    times=[r['body']['receive_monotonic_s']-epoch for r in rows]
    if any(b<=a for a,b in zip(times,times[1:])): raise ValueError('Saved clock reversed')
    session='saved-sonic-body-boundary'; replies=[]
    if not ipc:
        bridge=SonicBodyBridge(BodyLifecycle(session,profile,config))
        for row,now in zip(rows,times):
            replies.append(bridge.consume(envelope(session,row['seq'],row['body'],row['sonic'],
                source_age_s=0.,joint_names=profile['names']),now=now))
        bridge.stop()
        return replies,bridge.status(),dict(kind='file_only',socket_opened=False)
    from record_session import RecordSession
    from zmq_transport import ZmqChannel
    with tempfile.TemporaryDirectory(prefix='g1-body-boundary-') as directory:
        endpoint='ipc://'+str(Path(directory)/'body.sock')
        ready=threading.Event(); errors=[]; timeline=[0.]
        worker=BodyRecordWorker(profile,config,lambda:timeline[0])
        def serve():
            channel=None
            try:
                channel=ZmqChannel(endpoint,server=True,timeout_ms=1000,max_message_bytes=65536)
                ready.set()
                while worker.phase not in {'stopped','fault'}:
                    channel.send(worker.handle(channel.read()))
            except BaseException as exc:
                errors.append(type(exc).__name__+': '+str(exc))
                if worker.bridge: worker.bridge.lifecycle.request_stop('record_transport_ended')
            finally:
                ready.set()
                if channel: channel.close()
        thread=threading.Thread(target=serve); thread.start(); client=None
        try:
            if not ready.wait(3) or errors: raise RuntimeError('Body IPC startup: '+str(errors))
            transport=RecordSession(ZmqChannel(endpoint,timeout_ms=500,max_message_bytes=65536),session,
                dict(max_source_age_s=.1,max_roundtrip_s=.1,max_tick_gap_s=.5))
            client=BodyRecordClient(transport,profile['names']); client.start()
            for row,now in zip(rows,times):
                timeline[0]=now
                replies.append(client.receive(row['seq'],row['body'],row['sonic'],source_age_s=0.))
            client.stop()
        finally:
            if client: client.close()
            thread.join(3)
        if errors or thread.is_alive() or worker.phase!='stopped': raise RuntimeError('Body IPC shutdown: '+str(errors))
        return replies,worker.bridge.status(),dict(kind='local_ZMQ_IPC_only',socket_opened=True,
            receiver_thread_exited=True,receiver_phase=worker.phase,transport_freshness_scope='local_replay_envelope_not_original_sensor_age')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipc',action='store_true',help='Local Unix socket only; no G1/GPU access')
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/full-record/run-b5do1ocs/outputs/report.json')
    args=parser.parse_args(); rows,integrity=load_rows(args.report)
    profile=load_profile(); config=strict_message(DEFAULT.read_bytes())
    start=time.monotonic(); replies,status,transport=replay(rows,profile,config,ipc=args.ipc)
    parent=ROOT/'artifacts/body-boundary'; parent.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    save(directory/'decisions.json',dict(decisions=replies)); save(directory/'profile.json',profile)
    report=dict(scope='saved_real_SONIC_to_body_record_boundary_NOT_robot_control',
        integration_passed=(len(replies)==150 and status['gated_targets']==150 and status['accepted_abstract_targets']==0
            and all(r['gripper_width_m']==row['sonic']['gripper_width_m'] for row,r in zip(rows,replies))),
        source_report_sha256=sha(args.report),input_integrity=integrity,transport=transport,
        input_count=len(rows),decision_count=len(replies),status=status,
        target_rows_outside_model=sum(bool(r['target_limit_violations']) for r in replies),
        target_violating_joints=sorted({name for r in replies for name in r['target_limit_violations']}),
        clock_scope='saved accelerated body timeline; source_age=0 is replay metadata, NOT live sensor freshness',
        elapsed_wall_s=time.monotonic()-start,hardware_ready=False,robot_commands_sent=False,g1_connected=False,
        physical_stop_validated=False,source_code_sha256={name:sha(Path(__file__).with_name(name)) for name in
            ('run_body_boundary.py','sonic_body_bridge.py','body_lifecycle.py','online_record_loop.py')},
        output_sha256={name:sha(directory/name) for name in ('decisions.json','profile.json')})
    save(directory/'report.json',report); print(json.dumps(report,indent=2)); print('Saved:',directory)
    return 0 if report['integration_passed'] else 1


if __name__=='__main__': raise SystemExit(main())
