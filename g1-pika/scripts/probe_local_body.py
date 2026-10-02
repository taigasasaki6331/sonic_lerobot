"""Bounded G1 LowState -> local record-only service -> GPU TCP diagnostic.

No LowCmd, ownership, INIT, serial or physical stop. Probe targets are pinned
defaults, NOT SONIC inference. Strict SSH keys and fresh isolated directories.
Snapshot age is bounded causally over SSH, never by comparing host clocks.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))

FILES=('probe_local_body.py','local_body_service.py','body_lifecycle.py',
    'local_body_monitor.py','sonic_body_bridge.py','sonic_process.py','state_history.py',
    'sonic_startup_ablation.py','sonic_joint_trajectory.py','sonic_observation.py',
    'sonic_reference.py','zmq_transport.py','record_session.py','runtime_gate.py')


def emit(value): print(json.dumps(value,allow_nan=False),flush=True)


def causal_age(local_age,started,received):
    if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (local_age,started,received))
            or local_age<0 or received<started): raise ValueError('Invalid causal snapshot age')
    age=local_age+received-started
    if not age<.1: raise ValueError('Snapshot age bound exceeds 100ms')
    return age


def validate_topology(access):
    if (access['g1_host'],access['g1_interface'],access['gpu_wired_ip'])!=(
            'unitree@192.0.2.11','enP8p1s0','192.0.2.12'):
        raise ValueError('Unsupported topology; no silent IP/interface fallback')


def read_line(process,seconds=5):
    # Unbuffered Popen pipes: select must not miss data in a Python read buffer.
    if not select.select([process.stdout],[],[],seconds)[0]:
        raise TimeoutError('Read-only supervisor response timeout')
    line=process.stdout.readline()
    if not line: raise RuntimeError('Read-only supervisor closed')
    return json.loads(line)


def cleanup(process):
    if process is None: return
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
    for pipe in (process.stdin,process.stdout):
        if pipe:
            try: pipe.close()
            except BrokenPipeError: pass


def on_g1(source,access,expire,verify_crc=False):
    """Only same-host receive_state supplies service stdin; peer cannot do so."""
    output=source/'outputs'; output.mkdir(exist_ok=True)
    receiver=service=None; feeder=None; stopped=threading.Event(); pause=threading.Event()
    lock=threading.Lock(); latest=[]; feeder_errors=[]; report={}
    state_log=(output/'state.jsonl').open('wb')
    receiver_error=(output/'receiver.stderr').open('wb')
    service_error=(output/'service.stderr').open('wb')
    try:
        service=subprocess.Popen([sys.executable,'-I',str(source/'local_body_service.py'),
            '--endpoint','tcp://192.0.2.11:6077','--peer-ip',access['gpu_wired_ip'],
            '--profile',str(source/'profile.json'),'--config',str(source/'body-lifecycle.json'),
            '--seconds','15','--report',str(output/'service-report.json')]+(['--require-crc'] if verify_crc else []),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=service_error,bufsize=0)
        environment=dict(os.environ,G1_STATE_INTERFACE=access['g1_interface'])
        receiver=subprocess.Popen([str(source/'receive_state'),'--stream']+(['--verify-crc'] if verify_crc else []),stdout=subprocess.PIPE,
            stderr=receiver_error,env=environment,bufsize=0)
        def feed():
            try:
                while not stopped.is_set():
                    if not select.select([receiver.stdout],[],[],.1)[0]: continue
                    line=receiver.stdout.readline()
                    if not line:
                        if stopped.is_set(): break
                        raise RuntimeError('LowState receiver EOF')
                    frame=json.loads(line); state_log.write(line)
                    with lock: latest[:]=[frame]
                    if not pause.is_set():
                        service.stdin.write(line)
            except BrokenPipeError:
                # Service closes its input after record stop or watchdog fault.
                # Its actual exit status/error decides whether that was valid.
                pass
            except ValueError as exc:
                if service.poll() is None and not stopped.is_set(): feeder_errors.append(str(exc))
            except Exception as exc: feeder_errors.append(type(exc).__name__+': '+str(exc))
        feeder=threading.Thread(target=feed); feeder.start()
        ready=read_line(service)
        if not ready.get('ready'): raise RuntimeError('Local record service not ready')
        emit(dict(event='ready',scope='real_LowState_record_only',robot_commands_sent=False))
        deadline=time.monotonic()+12; paused_at=None; expired_exit_at=None; finished=False
        while time.monotonic()<deadline:
            code=service.poll()
            if code is not None and (expire or code!=0):
                expired_exit_at=time.monotonic()
                if not expire or paused_at is None: raise RuntimeError('Service exited unexpectedly: '+str(code))
                break
            if not select.select([sys.stdin.buffer],[],[],.01)[0]: continue
            request=json.loads(sys.stdin.buffer.readline())
            if request=={'op':'snapshot'}:
                with lock: frame=dict(latest[0])
                age=time.monotonic()-frame['receive_monotonic_s']
                if not 0<=age<=.1: raise RuntimeError('Supervisor snapshot stale')
                emit(dict(event='snapshot',frame=frame,local_age_s=age))
            elif request=={'op':'expire'} and expire and paused_at is None:
                paused_at=time.monotonic(); pause.set()
                # Keep stdin open, drain actual receiver. Neither EOF nor a
                # network request triggers expiry: independent watchdog does.
                emit(dict(event='paused',stdin_kept_open=True))
            elif request=={'op':'finish'} and not expire:
                if service.wait(timeout=2)!=0: raise RuntimeError('Service abnormal stop')
                finished=True; break
            else: raise ValueError('Unsupported supervisor operation')
        if expire:
            if paused_at is None or service.poll() in (None,0): raise RuntimeError('Watchdog failed to terminate')
            service_error.flush()
            if 'watchdog expired' not in (output/'service.stderr').read_text():
                raise RuntimeError('Failure was not local watchdog expiry')
        elif not finished: raise RuntimeError('No bounded diagnostic stop')
        report=dict(passed=True,scope='local_body_record_service_actual_LowState',
            scenario='sensor_updates_paused_stdin_open' if expire else 'normal_record_stop',
            service_exit_code=service.returncode,
            watchdog_exit_elapsed_s=expired_exit_at-paused_at if expire else None,
            sensor_pause_monotonic_s=paused_at,
            physical_stop_validated=False,robot_commands_sent=False,
            hardware_ready=False)
    except Exception as exc:
        report=dict(passed=False,error=type(exc).__name__+': '+str(exc),
            robot_commands_sent=False,physical_stop_validated=False)
    finally:
        stopped.set(); cleanup(service); cleanup(receiver)
        if feeder: feeder.join(2)
        state_log.close(); receiver_error.close(); service_error.close()
        frames=[json.loads(line) for line in (output/'state.jsonl').read_bytes().splitlines()]
        gaps=[b['receive_monotonic_s']-a['receive_monotonic_s'] for a,b in zip(frames,frames[1:])]
        report.update(frames=len(frames),receiver_exit_code=receiver.returncode if receiver else None,
            service_exit_code=service.returncode if service else None,
            feeder_exited=not feeder or not feeder.is_alive(),feeder_errors=feeder_errors,
            max_receiver_gap_s=max(gaps,default=None),mode_machine=sorted({f['mode_machine'] for f in frames}),
            mode_pr=sorted({f['mode_pr'] for f in frames}),
            state_sha256=hashlib.sha256((output/'state.jsonl').read_bytes()).hexdigest())
        report['crc_verification_requested']=verify_crc
        report['crc_verified']=bool(frames) and all(f['crc_verified'] is True for f in frames)
        if verify_crc and not report['crc_verified']: report['passed']=False
        if feeder_errors or (feeder and feeder.is_alive()): report['passed']=False
        (output/'g1-report.json').write_text(json.dumps(report,indent=2)+'\n')
        emit(dict(event='report',report=report))
    return 0 if report['passed'] else 1


def on_gpu(source,access,expire,verify_crc=False):
    from run_state_shadow import directory,run
    from sonic_body_bridge import BodyRecordClient
    from record_session import RecordSession
    from zmq_transport import ZmqChannel
    opts=['-i',access['gpu_ssh_identity'],'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+access['gpu_known_hosts'],
        '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=5']
    ssh=['ssh',*opts,access['g1_host']]
    dest=directory(ssh,'/tmp/g1-pika-local-body-')
    extra=[str(source/'crc-oracle')] if verify_crc else []
    run(['scp',*opts,'-r',*[str(source/f) for f in FILES],str(source/'state_receiver'),
        str(source/'profile.json'),str(source/'body-lifecycle.json'),str(source/'g1-runtime-access.json'),
        *extra,
        access['g1_host']+':'+dest+'/'])
    output=source/'outputs'; output.mkdir(exist_ok=True)
    if verify_crc:
        oracle=dest+'/crc-oracle'
        run(ssh+[f'g++ -std=c++17 -O2 -Wall -Wextra -Werror -I{oracle} -I/usr/local/include '
            f'{oracle}/check_state_crc.cpp -o {dest}/crc-oracle-check'])
        result=subprocess.run(ssh+[dest+'/crc-oracle-check'],capture_output=True,timeout=10)
        baseline=(source/'crc-oracle/native.hex').read_bytes()
        oracle_report=dict(passed=result.returncode==0 and result.stdout==baseline,
            fixtures=128,native_state_size_bytes=2092,scope='data_only_lowstate_layout_crc_not_actuation',
            x86_64_sha256=hashlib.sha256(baseline).hexdigest(),aarch64_sha256=hashlib.sha256(result.stdout).hexdigest(),
            pinned=json.loads((source/'crc-oracle/expected.json').read_bytes()),
            binary_exit_code=result.returncode,robot_commands_sent=False)
        (output/'crc-oracle-report.json').write_text(json.dumps(oracle_report,indent=2)+'\n')
        (output/'crc-oracle.stderr').write_bytes(result.stderr)
        if not oracle_report['passed']: raise RuntimeError('aarch64 native LowState oracle mismatch')
    code=dest+'/state_receiver'
    run(ssh+["grep -q '#define DDS_VERSION \"0.10.2\"' /usr/local/include/dds/version.h && "
        f'gcc -O2 -Wall -Wextra -I/usr/local/include -I{code}/generated '
        f'{code}/receive_state.c {code}/generated/State.c -L/usr/local/lib '
        f'-Wl,-rpath,/usr/local/lib -lddsc -lm -o {dest}/receive_state'])
    process=channel=client=None; replies=[]; report={}; snapshot_ages=[]
    targets=json.loads((source/'probe-targets.json').read_bytes()) if (source/'probe-targets.json').exists() else None
    target_source='saved_real_SONIC_NOT_live_inference' if targets else 'pinned_default_probe_NOT_SONIC'
    error=(output/'supervisor.stderr').open('wb')
    try:
        process=subprocess.Popen(ssh+['timeout --signal=TERM --kill-after=2s 20s python3 -I '+
            shlex.quote(dest+'/probe_local_body.py')+' --on-g1'+(' --expire' if expire else '')+
            (' --verify-crc' if verify_crc else '')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error,bufsize=0)
        ready=read_line(process,7)
        if ready.get('event')!='ready': raise RuntimeError('G1 supervisor startup: '+str(ready))
        channel=ZmqChannel('tcp://192.0.2.11:6077',timeout_ms=1000,max_message_bytes=65536)
        session='local-body-probe-'+Path(dest).name
        profile=json.loads((source/'profile.json').read_bytes())
        client=BodyRecordClient(RecordSession(channel,session,
            dict(max_source_age_s=.1,max_roundtrip_s=.1,max_tick_gap_s=.5)),profile['names'])
        client.start()
        for seq in range(len(targets['outputs']) if targets else 50):
            started=time.monotonic()
            process.stdin.write(b'{"op":"snapshot"}\n')
            response=read_line(process,2)
            if response.get('event')!='snapshot': raise RuntimeError('Snapshot: '+str(response))
            age=causal_age(response['local_age_s'],started,time.monotonic())
            # Causal round-trip + local age overbounds a sample's age without
            # subtracting two machines' monotonic clocks. Not target readiness.
            snapshot_ages.append(age)
            result=targets['outputs'][seq] if targets else dict(seq=seq,q_target_hardware=profile['defaults'],
                gripper_width_m=.04,gripper_actuated=False,probe_target_not_inference=True)
            reply=client.receive(seq,response['frame'],result,source_age_s=age)
            if reply['decision']!='gated_initial_pose_not_ready':
                raise ValueError('Read-only target gate failed')
            replies.append(reply)
            remaining=.02-(time.monotonic()-started)
            if remaining>0: time.sleep(remaining)
        if expire:
            process.stdin.write(b'{"op":"expire"}\n')
            if read_line(process).get('event')!='paused': raise RuntimeError('Missing pause ACK')
        else:
            client.stop()
            process.stdin.write(b'{"op":"finish"}\n')
        final=read_line(process,5)
        if final.get('event')!='report': raise RuntimeError('Missing G1 report: '+str(final))
        report=final['report']; report['supervisor_exit_code']=process.wait(timeout=3)
        if process.returncode!=0: report['passed']=False
    except Exception as exc:
        report=dict(passed=False,error=type(exc).__name__+': '+str(exc),robot_commands_sent=False)
    finally:
        if client: client.close()
        elif channel: channel.close()
        cleanup(process); error.close()
        # Keep evidence even on failure. Pull G1 outputs after bounded cleanup.
        run(['scp',*opts,'-r',access['g1_host']+':'+dest+'/outputs',str(output/'g1')])
        report.update(g1_directory=dest,received_records=len(replies),accepted_targets=0,
            snapshot_age_bound_max_s=max(snapshot_ages,default=None),
            robot_commands_sent=False,target_source=target_source,
            source_age_scope='causal_bound_for_live_body_probe_transport_NOT_original_saved_inference_age',
            target_source_report_sha256=targets['source_report_sha256'] if targets else None,
            target_rows_outside_model=sum(bool(r['target_limit_violations']) for r in replies),
            camera_or_serial_opened=False,physical_stop_validated=False)
        (output/'decisions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in replies))
        service_report_path=output/'g1/service-report.json'
        if service_report_path.exists():
            service_report=json.loads(service_report_path.read_bytes())
            report['service_diagnostic_journal_present']=True
            boundary=service_report.get('boundary')
            if (service_report['robot_commands_sent'] is not False or
                    boundary is None or boundary['accepted_abstract_targets']!=0 or
                    boundary['lifecycle']['command_records']!=0 or
                    not service_report['reader_exited'] or not service_report['watchdog_exited']):
                report['passed']=False
            fault_at=service_report['fault_observed_monotonic_s']
            if expire and fault_at is not None and report.get('sensor_pause_monotonic_s') is not None:
                report['watchdog_fault_observed_after_pause_s']=fault_at-report['sensor_pause_monotonic_s']
                report['watchdog_fault_age_since_last_sample_s']=fault_at-service_report['last_receive_monotonic_s']
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        emit(report)
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--on-gpu',action='store_true'); parser.add_argument('--on-g1',action='store_true')
    parser.add_argument('--expire',action='store_true')
    parser.add_argument('--verify-crc',action='store_true',help='Canonical native LowState CRC; mismatch terminates receiver')
    parser.add_argument('--saved-sonic',action='store_true',help='Use the verified 150 saved real SONIC outputs, NOT live inference')
    args=parser.parse_args()
    if args.on_g1 and args.on_gpu: parser.error('Select only one deployment role')
    source=Path(__file__).resolve().parent
    if args.on_g1 or args.on_gpu:
        access=json.loads((source/'g1-runtime-access.json').read_bytes()); validate_topology(access)
        if args.on_g1:
            def interrupt(signum,frame): raise RuntimeError('Bounded supervisor interrupted: '+str(signum))
            signal.signal(signal.SIGTERM,interrupt); signal.signal(signal.SIGINT,interrupt)
            return on_g1(source,access,args.expire,args.verify_crc)
        return on_gpu(source,access,args.expire,args.verify_crc)
    from run_state_shadow import GPU,GPU_ROOT,GPU_OPTS,directory,run
    from body_lifecycle_profile import load_profile
    profile=load_profile()
    root=source.parent
    validate_topology(json.loads((root/'assets/network/g1-runtime-access.json').read_bytes()))
    local=root/'artifacts/local-body'; local.mkdir(parents=True,exist_ok=True)
    import tempfile
    staging=Path(tempfile.mkdtemp(prefix='stage-',dir=local))
    (staging/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    targets_path=None
    if args.saved_sonic:
        from run_body_boundary import load_rows
        from sonic_startup_ablation import SOURCE_REPORT_SHA
        rows,_=load_rows(root/'artifacts/full-record/run-b5do1ocs/outputs/report.json')
        targets_path=staging/'probe-targets.json'
        targets_path.write_text(json.dumps(dict(source_report_sha256=SOURCE_REPORT_SHA,
            outputs=[r['sonic'] for r in rows]),allow_nan=False)+'\n')
    generated=source/'state_receiver/generated'
    for name,digest in json.loads((generated/'manifest.json').read_bytes())['sha256'].items():
        if hashlib.sha256((source/'state_receiver'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Fixed receiver source changed: '+name)
    dest=directory(['ssh',*GPU_OPTS,GPU],GPU_ROOT+'/artifacts/local-body-')
    files=[source/f for f in FILES]+[source/'run_state_shadow.py',source/'state_receiver',
        staging/'profile.json',root/'config/body-lifecycle.json',root/'assets/network/g1-runtime-access.json']
    if args.verify_crc:
        from check_state_crc import export_oracle,verify_native,PINNED
        from lowcmd_preview import SDK
        oracle=staging/'crc-oracle'; oracle.mkdir(); export_oracle(oracle)
        executable=oracle/'oracle-x86_64'
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(oracle),
            '-I'+str(SDK/'thirdparty/include'),str(oracle/'check_state_crc.cpp'),'-o',str(executable)],
            check=True,timeout=30)
        native=subprocess.check_output([str(executable)],timeout=5); verify_native(native)
        (oracle/'native.hex').write_bytes(native)
        (oracle/'expected.json').write_text(json.dumps(dict(pinned_sdk_sha256=PINNED,
            python_crc_verified=True,state_crc_header_sha256=hashlib.sha256((oracle/'state_crc.h').read_bytes()).hexdigest()),indent=2)+'\n')
        files.append(oracle)
    if targets_path: files.append(targets_path)
    manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    (staging/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    run(['scp',*GPU_OPTS,'-r',*map(str,files),str(staging/'source-manifest.json'),GPU+':'+dest+'/'])
    result=subprocess.run(['ssh',*GPU_OPTS,GPU,'python3 -I '+shlex.quote(dest+'/probe_local_body.py')+
        ' --on-gpu'+(' --expire' if args.expire else '')+(' --verify-crc' if args.verify_crc else '')],timeout=75)
    run(['scp',*GPU_OPTS,'-r',GPU+':'+dest,str(local)+'/'])
    print('Local evidence: '+str(local/Path(dest).name),flush=True)
    return result.returncode


if __name__=='__main__': raise SystemExit(main())
