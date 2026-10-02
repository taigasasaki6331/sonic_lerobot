"""Wall-clock 30Hz ACT/IK and 50Hz SONIC with a REPEATED archived snapshot.

This tests scheduling/software only: no live sensors, plant, physics or motors.
"""
import base64
import copy
import hashlib
from pathlib import Path
import tempfile
import threading
import time
import uuid
from reference_mailbox import ReferenceMailbox
from record_session import RecordSession
from zmq_transport import ZmqChannel


def run_rate_check(actor,ik,sonic,record,images,config,seconds=1):
    if type(seconds) is not int or not 1<=seconds<=30: raise ValueError('Duration must be 1..30 integer seconds')
    policy_count=30*seconds; control_count=50*seconds
    session=str(uuid.uuid4()); mailbox=ReferenceMailbox(session,config['diagnostic_deadlines']['max_source_age_s'])
    errors=[]; policy_rows=[]; outputs=[]; ready=threading.Event(); stop=threading.Event()
    packet=copy.deepcopy(record['frames'][0]['capture'])
    for role,image in packet['images'].items():
        blob=(Path(images)/f'00-{role}.jpg').read_bytes()
        if hashlib.sha256(blob).hexdigest()!=image['sha256']: raise ValueError('Image hash mismatch')
        image['jpeg']=base64.b64encode(blob).decode()
    def policy_loop():
        try:
            epoch=time.monotonic()
            for seq in range(policy_count):
                if stop.wait(max(0,epoch+seq/30-time.monotonic())): break
                issued=time.monotonic(); sample=copy.deepcopy(packet); sample['seq']=seq
                actor.send(sample); action=actor.read(timeout=5)
                if action['seq']!=seq: raise ValueError('ACT identity')
                frame=copy.deepcopy(record['frames'][0]); frame.update(action); frame['capture']['seq']=seq
                ik.send(dict(op='infer',seq=seq,frame=frame)); candidate=ik.read(timeout=5)
                if candidate['seq']!=seq or candidate.get('hardware_output_enabled') is not False: raise ValueError('IK identity')
                finished=time.monotonic()
                mailbox.publish(session=session,seq=seq,issued_at=issued,finished_at=finished,reference=candidate['result'])
                policy_rows.append(dict(seq=seq,issued_at=issued,finished_at=finished,compute_ms=(finished-issued)*1000))
        except BaseException as exc:
            errors.append('policy: '+type(exc).__name__+': '+str(exc)); stop.set()
    with tempfile.TemporaryDirectory(prefix='sonic-rates-') as directory:
        endpoint='ipc://'+str(Path(directory)/'worker.sock')
        def serve():
            channel=None
            try:
                channel=ZmqChannel(endpoint,server=True,timeout_ms=3000,max_message_bytes=2000000)
                ready.set(); hello=channel.read()
                if hello!=dict(op='hello',session=session,schema=1,mode='record_only'): raise ValueError('Hello mismatch')
                channel.send(dict(ready=True,session=session,schema=1,mode='record_only',hardware_output_enabled=False))
                for expected in range(control_count+1):
                    message=channel.read()
                    if message.get('session')!=session: raise ValueError('Session mismatch')
                    if message.get('op')=='stop':
                        sonic.stop(); channel.send(dict(stopped=True,session=session)); break
                    if message.get('op')!='record' or message.get('seq')!=expected: raise ValueError('Control sequence')
                    result=sonic.infer(message['payload'])
                    channel.send(dict(session=session,seq=expected,result=result,hardware_output_enabled=False))
            except BaseException as exc: errors.append('sonic: '+type(exc).__name__+': '+str(exc)); stop.set()
            finally:
                ready.set()
                if channel: channel.close()
        worker=threading.Thread(target=serve); worker.start()
        if not ready.wait(3): raise RuntimeError('SONIC server timeout')
        client=RecordSession(ZmqChannel(endpoint,timeout_ms=1000),session,config['diagnostic_deadlines'])
        producer=threading.Thread(target=policy_loop)
        try:
            client.start(); producer.start()
            deadline=time.monotonic()+5
            while mailbox.read(time.monotonic()) is None:
                if stop.is_set() or time.monotonic()>deadline: raise RuntimeError('Initial reference unavailable: '+str(errors))
                time.sleep(.001)
            epoch=time.monotonic(); history=[0.]*290
            for seq in range(control_count):
                if stop.wait(max(0,epoch+seq/50-time.monotonic())): raise RuntimeError(str(errors))
                now=time.monotonic(); reference=mailbox.read(now)
                row=reference['reference']
                row['decoder_tail'][610:900]=history
                result=client.query(seq,row,source_age_s=now-reference['issued_at'])
                history=history[29:]+result['raw_action_isaaclab']
                if result.get('gripper_width_m')!=row['gripper_width_m'] or result.get('gripper_actuated') is not False:
                    raise ValueError('Width side-channel')
                outputs.append(dict(seq=seq,policy_seq=reference['seq'],started_at=now,
                                    lateness_ms=(now-(epoch+seq/50))*1000,sonic=result))
            producer.join(6)
            if producer.is_alive() or errors or len(policy_rows)!=policy_count: raise RuntimeError(str(errors))
            client.stop(); worker.join(3)
            if worker.is_alive() or errors: raise RuntimeError(str(errors))
            actor.send({'stop':True})
            if actor.process.wait(timeout=5)!=0: raise RuntimeError('ACT exit')
            ik.send(dict(op='stop'))
            if ik.read()!=dict(stopped=True) or ik.process.wait(timeout=5)!=0: raise RuntimeError('IK exit')
        finally:
            stop.set(); client.close(); mailbox.stop()
            if producer.ident: producer.join(6)
            worker.join(4)
    return dict(scope='synthetic_repeat_archived_snapshot_independent_rate_software_test',
                source_frames=[0],observation_history='repeated_snapshot_not_real_50Hz',
                control_requested_hz=50,policy_requested_hz=30,
                requested_seconds=seconds,
                policy_count=len(policy_rows),control_count=len(outputs),policy_records=policy_rows,outputs=outputs,
                control_start_lateness_max_ms=max(row['lateness_ms'] for row in outputs),
                action_history='prior_computed_SONIC_outputs_not_executed',
                physical_dynamics_verified=False)
