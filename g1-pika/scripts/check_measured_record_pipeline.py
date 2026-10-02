"""Archived real body -> ZMQ -> observation worker -> SONIC, NO live input.

Replay uses a synthetic coordinator clock and zero replay-source age. Neither
proves current sensor freshness. Reference is measured pose hold, NOT LeRobot.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
import numpy as np
from body_history_transport import BodyHistoryServer,BodyHistoryClient
from prepare_sonic_history_diagnostic import prepare
from sonic_process import JsonProcess,SonicProcess
from zmq_transport import ZmqChannel


def run(config,state_path,output):
    output=Path(output); output.mkdir(exist_ok=False)
    source=Path(__file__).resolve().parent; stage=source.parent
    raw=Path(state_path).read_bytes(); frames=[json.loads(line) for line in raw.splitlines()]
    baseline=prepare(raw)
    if baseline['skipped_windows']: raise ValueError('Consecutive body windows required')
    report=dict(passed=False,scope='archived_real_body_ZMQ_observation_SONIC_recurrent_equivalence',
                hardware_ready=False,g1_connected=False,robot_commands_sent=False,
                source_sha256=hashlib.sha256(raw).hexdigest(),coordinator_clock='synthetic_replay_50Hz',
                source_age='zero_for_replay_only_not_current_capture_freshness',
                reference='latest_measured_pose_hold_not_LeRobot',gripper_width='assumed_0.04m_not_measured')
    children=[]; logs=[]; errors=[]; results=[]; thread=None; client=None; stream_id=str(uuid.uuid4())
    encoder_difference=0.; body_difference=0.
    def log(name):
        f=(output/(name+'.stderr.log')).open('w'); logs.append(f); return f
    try:
        models=Path(config['sonic_models']); binary=stage/'sonic_offline_infer'
        observer=JsonProcess([Path(config['gpu_root'])/'.venv-gpu/bin/python','-I',source/'sonic_observation_worker.py'],log('observation'))
        children.append(observer)
        if observer.ready!=dict(ready=True,mode='measured_record_only',hardware_output_enabled=False): raise ValueError('Observation handshake')
        sonic=SonicProcess(binary,models/'model_encoder.onnx',models/'model_decoder.onnx',log('sonic'))
        children.append(sonic)
        def operation(op,**values):
            observer.send(dict(op=op,**values)); reply=observer.read(2)
            if reply.get('hardware_output_enabled') is not False: raise ValueError('Observation worker mode')
            return reply['result']
        operation('start',session=stream_id)
        class ArchiveSource:
            index=9
            def snapshot(self,previous_tick):
                if self.index>=len(frames): raise ValueError('Archive exhausted')
                history=frames[self.index-9:self.index+1]; self.index+=1
                return history,0.  # Replay envelope age, explicitly NOT original capture age.
        server=BodyHistoryServer(ArchiveSource(),max_frames=len(baseline['frames']))
        ready=threading.Event()
        with tempfile.TemporaryDirectory(prefix='sonic-measured-record-') as folder:
            endpoint='ipc://'+str(Path(folder)/'body.sock')
            def serve():
                channel=None
                try:
                    channel=ZmqChannel(endpoint,server=True,timeout_ms=3000)
                    ready.set()
                    while not server.closed: channel.send(server.handle(channel.read()))
                except Exception as exc: errors.append(type(exc).__name__+': '+str(exc))
                finally:
                    ready.set()
                    if channel: channel.close()
            thread=threading.Thread(target=serve); thread.start()
            if not ready.wait(3) or errors: raise RuntimeError('Body replay service startup: '+str(errors))
            client=BodyHistoryClient(ZmqChannel(endpoint,timeout_ms=1000),stream_id); client.start()
            for seq,expected in enumerate(baseline['frames']):
                packet=client.read(); body=packet['body_history'][-1]
                quat=np.asarray(body['quaternion']); quat=quat/np.linalg.norm(quat)
                reference=dict(q_hardware=[body['q'][:29]]*10,dq_hardware=[[0.]*29]*10,
                               quaternion_wxyz=[quat.tolist()]*10,gripper_width_m=.04,gripper_actuated=False)
                operation('reference',session=stream_id,seq=seq,reference=reference,issued_at=seq*.02,finished_at=seq*.02)
                row=operation('observe',session=stream_id,seq=seq,body_history=packet['body_history'],
                              now=seq*.02,source_age_s=packet['source_age_s'])
                difference=float(np.max(np.abs(np.asarray(row['encoder'])-expected['encoder'])))
                encoder_difference=max(encoder_difference,difference)
                if difference>np.finfo(np.float32).eps: raise ValueError('Encoder differs from independent file preparation: '+str(difference))
                # Check all body-driven fields against the older independent file assembly.
                indices=list(range(610))+list(range(900,930))
                difference=float(np.max(np.abs(np.asarray(row['decoder_tail'])[indices]-np.asarray(expected['decoder_tail'])[indices])))
                body_difference=max(body_difference,difference)
                if difference>np.finfo(np.float32).eps: raise ValueError('Measured decoder observation mismatch: '+str(difference))
                result=sonic.infer(row)
                operation('commit',session=stream_id,seq=seq,result=result)
                results.append(result)
                expected.update(seq=seq,gripper_width_m=.04,gripper_actuated=False)
            client.stop(); thread.join(3)
            if thread.is_alive() or errors: raise RuntimeError(str(errors))
        sonic.stop(); observer.send(dict(op='stop'))
        if observer.read()!=dict(stopped=True) or observer.process.wait(timeout=3)!=0: raise RuntimeError('Observation shutdown')
        (output/'baseline-input.json').write_text(json.dumps(baseline,allow_nan=False))
        with (output/'baseline.stderr.log').open('w') as file:
            subprocess.run([str(binary),str(models/'model_encoder.onnx'),str(models/'model_decoder.onnx'),
                str(output/'baseline-input.json'),str(output/'baseline.json'),'recurrent'],
                stdout=file,stderr=subprocess.STDOUT,check=True,timeout=30)
        comparison=json.loads((output/'baseline.json').read_text())['outputs']
        delta=float(np.max(np.abs(np.asarray([r['q_target_hardware'] for r in results])-
                                   np.asarray([r['q_target_hardware'] for r in comparison]))))
        if delta>1e-6: raise ValueError('Persistent/batch recurrent mismatch: '+str(delta))
        report.update(passed=True,windows=len(results),max_batch_target_difference_rad=delta)
    except Exception as exc: report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if client: client.close()
        for child in children: child.close()
        if thread: thread.join(4)
        for file in logs: file.close()
        report.update(worker_exit_codes=[child.process.returncode for child in children],worker_errors=errors,outputs=results,
                      max_encoder_observation_difference=encoder_difference,max_body_observation_difference=body_difference,
                      observation_comparison_atol=float(np.finfo(np.float32).eps))
        (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k!='outputs'},indent=2))
    return 0 if report['passed'] else 1
