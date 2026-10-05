"""Build/package or run ONE complete record-only G1 runtime rehearsal.

Default needs no G1/GPU: synthetic local body + ZMQ references + native writer.
serve feeds ONLY a same-host read-only LowState executable into that service.
No hardware transport is linked, and no output-enabled option exists.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle_profile import load_profile
from lowcmd_preview import export_data_headers,crc_words
from sonic_process import strict_message

ROOT=Path(__file__).resolve().parents[1]
FILES=('launch_body_runtime.py','local_body_service.py','local_body_runtime.py','body_runtime.py','body_runtime.cpp',
    'body_writer.hpp','body_io_adapter.hpp','body_owner_lifecycle.hpp','body_lifecycle.py','local_body_monitor.py',
    'sonic_body_bridge.py','sonic_process.py','state_history.py','sonic_startup_ablation.py',
    'sonic_joint_trajectory.py','sonic_observation.py','sonic_reference.py','zmq_transport.py')


def write(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def build(directory):
    source=directory/'runtime'; source.mkdir()
    for name in FILES: shutil.copy2(ROOT/'scripts'/name,source/name)
    shutil.copytree(ROOT/'scripts/state_receiver',source/'state_receiver')
    export_data_headers(source)
    shutil.copy2(ROOT/'config/body-lifecycle.json',source/'body-lifecycle.json')
    write(source/'profile.json',load_profile())
    # Same sources compile on G1/aarch64. Package contains source, not a falsely
    # portable x86 binary. The currently running build stays architecture tagged.
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread',
        '-shared','-fPIC','-I'+str(source),str(source/'body_runtime.cpp'),'-o',str(source/'body-runtime.so')],
        check=True,timeout=30)
    write(directory/'manifest.json',dict(scope='record_only_runtime_package',robot_commands_sent=False,
        machine=os.uname().machine,files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(source.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}))
    return source


def service_command(source,endpoint,report,seconds,peer=None,*,recovery=False):
    return [sys.executable,'-I',str(source/'local_body_service.py'),'--endpoint',endpoint,
        '--profile',str(source/'profile.json'),'--config',str(source/'body-lifecycle.json'),
        '--native-runtime',str(source/'body-runtime.so'),'--require-crc','--seconds',str(seconds),
        '--report',str(report)]+(['--peer-ip',peer] if peer else [])+(
        ['--record-recovery-note','ARTIFICIAL record stop observed; NOT physical confirmation'] if recovery else [])


def terminate(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)


def rehearse(directory,source,seconds,scenario):
    from zmq_transport import ZmqChannel
    from sonic_body_bridge import envelope
    import struct
    output=directory/'outputs'; output.mkdir()
    ipc_directory=tempfile.TemporaryDirectory(prefix='g1-body-ipc-')
    endpoint='ipc://'+str(Path(ipc_directory.name)/'body.sock')
    profile=strict_message((source/'profile.json').read_bytes()); config=strict_message((source/'body-lifecycle.json').read_bytes())
    initial=profile['defaults'].copy(); joint=22; initial[joint]+=.02
    process=None; channel=None; feed=None; quit_feed=threading.Event(); pause=threading.Event()
    lock=threading.Lock(); latest=[]; init_at=[]; feeder_errors=[]; received=[]; ready=None
    stderr=(output/'service.stderr').open('wb'); states=(output/'fixture-state.jsonl').open('wb')
    report=dict(passed=False,scope='one_runtime_native_owner_ZMQ_INIT_stop_rehearsal',
        scenario=scenario,input_source='ARTIFICIAL_body_and_targets_NOT_DDS_or_ACT_SONIC_inference',
        robot_commands_sent=False,physical_stop_confirmed=False,hardware_transport_linked=False)
    stage='service_start'
    try:
        process=subprocess.Popen(service_command(source,endpoint,output/'service-report.json',min(60,math.ceil(seconds)+8),
            recovery=scenario=='recovery'),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,bufsize=0,
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        def feeder():
            tick=0
            try:
                while not quit_feed.is_set():
                    now=time.monotonic(); q=initial.copy()
                    with lock: start=init_at[0] if init_at else None
                    if start is not None:
                        u=min(1.,max(0.,(now-start)/config['init_duration_s'])); blend=10*u**3-15*u**4+6*u**5
                        q[joint]=initial[joint]+blend*(profile['defaults'][joint]-initial[joint])
                    frame=dict(tick=tick,receive_monotonic_s=now,mode_pr=0,mode_machine=5,
                        q=q+[0.]*6,dq=[0.]*35,quaternion=[1.,0.,0.,0.],gyroscope=[0.]*3,
                        raw_motor_state=[0]*35,motor_modes=[1]*29+[0]*6,
                        crc_verified=True,crc_received=0,crc_calculated=0,crc_native_size_bytes=2092,
                        input_provenance='ARTIFICIAL_fixture_CRC_metadata_NOT_actual_CRC_validation')
                    with lock:
                        latest.append(frame)
                        del latest[:-3]
                    data=(json.dumps(frame)+'\n').encode(); states.write(data)
                    if not pause.is_set(): process.stdin.write(data)
                    tick+=1; quit_feed.wait(.02)
            except BrokenPipeError: pass
            except Exception as exc: feeder_errors.append(str(exc))
        feed=threading.Thread(target=feeder); feed.start()
        if not select.select([process.stdout],[],[],5)[0]: raise TimeoutError('Runtime ready timeout')
        line=process.stdout.readline()
        if not line: raise RuntimeError('Service exited before ready; see outputs/service.stderr')
        ready=json.loads(line)
        if ready.get('ready') is not True: raise ValueError('Service not ready')
        stage='hello'; channel=ZmqChannel(endpoint,timeout_ms=1000,max_message_bytes=65536)
        session='runtime-rehearsal'; channel.send(dict(op='hello',session=session,schema=1,mode='record_only'))
        if channel.read()!=dict(ready=True,session=session,schema=1,mode='record_only',hardware_output_enabled=False):
            raise ValueError('Runtime hello rejected')
        with lock: init_at[:]=[time.monotonic()]
        stage='stream'; start=time.monotonic(); seq=0; next_target=start; paused_at=None; frozen_peer_frame=None
        while time.monotonic()-start<seconds:
            now=time.monotonic()
            if process.poll() is not None:
                if scenario=='body_expiry' and paused_at is not None: break
                raise RuntimeError('Runtime exited before stop: '+str(process.returncode))
            if scenario=='body_expiry' and now-start>config['init_duration_s']+config['settle_duration_s']+.4:
                if paused_at is None:
                    paused_at=now; pause.set()
                    with lock: frozen_peer_frame=dict(latest[-2])
            if now<next_target: time.sleep(min(.005,next_target-now)); continue
            # The fixture producer's newest frame can still be in the pipe.
            # Use the prior sample, as a causal client would after processing;
            # do not weaken the local future-tick gate to conceal that race.
            with lock: frame=dict(latest[-2] if len(latest)>1 else latest[-1])
            if frozen_peer_frame is not None: frame=dict(frozen_peer_frame)
            target=profile['defaults'].copy()
            target[joint]+=.005*math.sin((now-start)*.5)
            result=dict(seq=seq,q_target_hardware=target,gripper_width_m=.04,gripper_actuated=False)
            # In expiry mode the artificial peer keeps claiming fresh targets
            # with its last known body tick. It cannot refresh SAME-HOST body.
            payload=envelope(session,seq,frame,result,
                source_age_s=0. if paused_at is not None else now-frame['receive_monotonic_s'],joint_names=profile['names'])
            stage='send_target_'+str(seq)
            channel.send(dict(op='record',session=session,seq=seq,payload=payload))
            stage='receive_target_'+str(seq)
            try: reply=channel.read()
            except OSError as exc:
                if scenario=='body_expiry' and paused_at is not None and exc.errno==11: break
                raise
            if reply.get('seq')!=seq or reply.get('hardware_output_enabled') is not False: raise ValueError('Runtime reply mismatch')
            received.append(reply['result']); seq+=1; next_target=time.monotonic()+.02
        stage='stop'
        if scenario in ('normal','recovery'):
            channel.send(dict(op='stop',session=session))
            if channel.read()!=dict(stopped=True,session=session): raise ValueError('Runtime stop ACK mismatch')
            code=process.wait(timeout=3)
            if code!=0: raise RuntimeError('Runtime stop exit '+str(code))
        else:
            if paused_at is None: raise ValueError('Expiry rehearsal too short')
            code=process.wait(timeout=3)
            if code==0: raise RuntimeError('Expiry unexpectedly succeeded')
        journal=strict_message((output/'service-report.json').read_bytes()); native=journal['native_runtime']
        packet=bytes.fromhex(native['last_native_memory_hex'])
        packet_crc_ok=struct.unpack_from('<I',packet,1000)[0]==crc_words(packet[:1000])
        accepted=sum(v['decision']=='accepted_abstract_target_NOT_sent' for v in received)
        passed=(native['owner_exited'] and native['record_stop_attempted'] and native['record_stop_write_accepted']
            and native['normal_publications_final']>100 and accepted>0 and packet_crc_ok and not feeder_errors)
        if scenario=='body_expiry':
            passed=passed and ('body' in native['reason'] or 'local_body' in native['reason'])
        passed=passed and lifecycle_passes(native,scenario)
        report.update(passed=bool(passed),service_exit_code=code,targets=len(received),accepted_abstract_targets=accepted,
            gated_targets=len(received)-accepted,native_runtime=native,last_packet_crc_matches=packet_crc_ok,
            service_report='outputs/service-report.json',duration_wall_s=time.monotonic()-start,
            initial_reference_duration_s=config['init_duration_s'],fixture_body_paused_stdin_open=paused_at is not None)
        report['artificial_peer_continued_after_body_pause']=paused_at is not None
    except BaseException as exc:
        report['error']=type(exc).__name__+': '+str(exc); report['failure_stage']=stage
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGUSR1); time.sleep(.05)
    finally:
        # Record process only. No physical-stop claim from termination.
        if channel: channel.close()
        terminate(process); quit_feed.set()
        if feed: feed.join(2)
        for stream in (process.stdin if process else None,process.stdout if process else None,stderr,states):
            if stream:
                try: stream.close()
                except BrokenPipeError: pass
        report.update(reader_feeder_exited=feed is None or not feed.is_alive(),feeder_errors=feeder_errors)
        write(output/'target-replies.json',received); write(output/'report.json',report)
        ipc_directory.cleanup()
    return report


def lifecycle_passes(native,scenario):
    owner=native['owner_lifecycle']; history=owner['history']
    required=('initialized','ownership_pending','owned','initializing','tracking','stop_required','stopped','closed')
    if not all(p in history for p in required) or not native['writer_exited'] or not native['owner_exited']: return False
    if owner['fault_latched']!=(scenario=='body_expiry'): return False
    if scenario=='recovery': return owner['recovery_acknowledged'] and 'recovered' in history
    return not owner['recovery_acknowledged'] and 'recovery_pending' not in history


def rehearse_direct(directory,source,seconds,scenario):
    """Same local worker/native owner; explicit socket-free fixture for CPU hosts.

    The artificial body follows the INIT reference. This is software lifecycle
    evidence, never a hardware pose/ownership/CRC or ZMQ-delivery check.
    """
    from local_body_runtime import LocalBodyRuntimeWorker
    from sonic_body_bridge import envelope
    import struct
    output=directory/'outputs'; output.mkdir()
    profile=strict_message((source/'profile.json').read_bytes())
    config=strict_message((source/'body-lifecycle.json').read_bytes())
    worker=LocalBodyRuntimeWorker(profile,config,library=source/'body-runtime.so')
    session='direct-runtime-rehearsal'; joint=22; initial=profile['defaults'].copy(); initial[joint]+=.02
    replies=[]; tick=0; frame=None; paused=False; start=None; error=None; rearm_rejected=False
    states=(output/'fixture-state.jsonl').open('w')
    report=dict(passed=False,scope='one_runtime_native_owner_DIRECT_INIT_stop_rehearsal',scenario=scenario,
        pc_transport='in_process_envelope_NO_ZMQ_delivery_verified',
        input_source='ARTIFICIAL_body_and_targets_NOT_DDS_or_ACT_SONIC_inference',
        robot_commands_sent=False,physical_stop_confirmed=False,hardware_transport_linked=False)
    def feed(now):
        nonlocal tick,frame
        q=initial.copy()
        if start is not None:
            u=min(1.,max(0.,(now-start)/config['init_duration_s'])); blend=10*u**3-15*u**4+6*u**5
            q[joint]=initial[joint]+blend*(profile['defaults'][joint]-initial[joint])
        frame=dict(tick=tick,receive_monotonic_s=now,mode_pr=0,mode_machine=5,
            q=q+[0.]*6,dq=[0.]*35,quaternion=[1.,0.,0.,0.],gyroscope=[0.]*3,
            raw_motor_state=[0]*35,motor_modes=[1]*29+[0]*6,
            crc_verified=True,crc_received=0,crc_calculated=0,crc_native_size_bytes=2092,
            input_provenance='ARTIFICIAL_fixture_CRC_metadata_NOT_actual_CRC_validation')
        states.write(json.dumps(frame)+'\n'); worker.ingest_local(frame); tick+=1
    try:
        feed(time.monotonic())
        worker.handle(dict(op='hello',session=session,schema=1,mode='record_only'))
        start=time.monotonic(); next_target=start; seq=0
        while time.monotonic()-start<seconds:
            now=time.monotonic()
            if scenario=='body_expiry' and now-start>config['init_duration_s']+config['settle_duration_s']+.4:
                paused=True
            if now<next_target:
                worker.poll(); time.sleep(min(.005,next_target-now)); continue
            if not paused: feed(now)
            target=profile['defaults'].copy(); target[joint]+=.005*math.sin((now-start)*.5)
            result=dict(seq=seq,q_target_hardware=target,gripper_width_m=.04,gripper_actuated=False)
            payload=envelope(session,seq,frame,result,
                source_age_s=0. if paused else now-frame['receive_monotonic_s'],joint_names=profile['names'])
            reply=worker.handle(dict(op='record',session=session,seq=seq,payload=payload))
            replies.append(reply['result']); worker.control_tick(); worker.poll()
            seq+=1; next_target=time.monotonic()+.02
        if scenario=='body_expiry': raise RuntimeError('Expected local body expiry was not observed')
        worker.handle(dict(op='stop',session=session))
        if scenario=='recovery':
            worker.recover_native('ARTIFICIAL local stop observed; NOT physical confirmation')
            probe=dict(q=profile['defaults'],dq=[0.]*29,tau=[0.]*29,kp=profile['kp'],kd=profile['kd'],
                       phase='tracking',source_age_s=0.)
            try: worker.native.reference(probe,now=time.monotonic())
            except ValueError: rearm_rejected=True
            if not rearm_rejected: raise RuntimeError('Recovery incorrectly rearmed normal output')
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)
        worker.fail(error)
    finally:
        try:
            worker.stop_native('direct_rehearsal_end'); worker.close_native()
        finally: states.close()
    native=worker.native_status()
    accepted=sum(v['decision']=='accepted_abstract_target_NOT_sent' for v in replies)
    crc_ok=False
    if native:
        packet=bytes.fromhex(native['last_native_memory_hex'])
        crc_ok=struct.unpack_from('<I',packet,1000)[0]==crc_words(packet[:1000])
    expected_fault=(scenario=='body_expiry' and paused and error is not None and native and
                    ('body' in native['reason'] or 'local_body' in native['reason']))
    passed=bool(native and native['record_stop_attempted'] and native['record_stop_write_accepted'] and
        native['normal_publications_final']>100 and accepted>0 and crc_ok and lifecycle_passes(native,scenario) and
        ((expected_fault and scenario=='body_expiry') or (error is None and scenario!='body_expiry')) and
        (scenario!='recovery' or rearm_rejected))
    report.update(passed=passed,error=error,expected_body_fault=bool(expected_fault),native_runtime=native,
        targets=len(replies),accepted_abstract_targets=accepted,last_packet_crc_matches=crc_ok,
        duration_wall_s=time.monotonic()-start if start else None,
        fixture_body_paused=paused,artificial_peer_continued_after_body_pause=paused,
        rearm_rejected_after_recovery=rearm_rejected,initial_reference_duration_s=config['init_duration_s'])
    write(output/'target-replies.json',replies); write(output/'report.json',report)
    return report


def serve(source,args):
    if not args.receiver or not args.interface or not args.endpoint or not args.peer_ip:
        raise ValueError('serve requires explicit receiver/interface/endpoint/peer-ip')
    from local_body_service import endpoint_filter
    endpoint_filter(args.endpoint,args.peer_ip)
    receiver=None; service=None
    try:
        receiver=subprocess.Popen([str(args.receiver.resolve()),'--stream','--verify-crc'],stdout=subprocess.PIPE,
            env=dict(os.environ,G1_STATE_INTERFACE=args.interface))
        service=subprocess.Popen(service_command(source,args.endpoint,source.parent/'service-report.json',math.ceil(args.seconds),args.peer_ip),
            stdin=receiver.stdout,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        receiver.stdout.close()
        return service.wait()
    finally:
        terminate(service); terminate(receiver)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('rehearse','build','serve'),default='rehearse')
    parser.add_argument('--scenario',choices=('normal','body_expiry','recovery'),default='normal')
    parser.add_argument('--transport',choices=('ipc','direct'),default='ipc',
        help='direct uses in-process envelopes and does NOT validate ZMQ delivery')
    parser.add_argument('--seconds',type=float,default=5)
    parser.add_argument('--output',type=Path); parser.add_argument('--package',type=Path)
    parser.add_argument('--receiver',type=Path); parser.add_argument('--interface')
    parser.add_argument('--endpoint'); parser.add_argument('--peer-ip')
    args=parser.parse_args()
    if not 4.2<=args.seconds<=30: parser.error('Require 4.2..30 seconds for full 3s INIT + settle')
    if args.mode=='serve':
        if not args.package: parser.error('serve requires an explicitly built same-architecture --package')
        return serve(args.package.resolve()/'runtime',args)
    base=ROOT/'artifacts/body-runtime'; base.mkdir(parents=True,exist_ok=True)
    if args.output:
        directory=args.output.resolve(); directory.mkdir(parents=True,exist_ok=False)
    else: directory=Path(tempfile.mkdtemp(prefix='run-',dir=base))
    source=build(directory)
    if args.mode=='build': print(json.dumps(dict(package=str(directory),robot_commands_sent=False))); return 0
    report=(rehearse_direct if args.transport=='direct' else rehearse)(directory,source,args.seconds,args.scenario)
    # Keep the full 1004-byte sample in the file, not console output.
    summary={key:value for key,value in report.items() if key!='native_runtime'}
    summary['native_runtime']={key:value for key,value in report.get('native_runtime',{}).items() if key!='last_native_memory_hex'}
    summary['report']=str(directory/'outputs/report.json'); print(json.dumps(summary,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': sys.exit(main())
