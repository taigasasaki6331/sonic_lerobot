"""Exercise the online coordinator with real models but SYNTHETIC input IO.

Saved image pair/body snapshot are repeated with artificial counters/timestamps.
No physics, network sensors, DDS, cameras or serial ports are used. This is NOT
a synchronized real dataset or evidence that actual input timing will work.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path
import time
from online_record_loop import run_online_loop
from sonic_process import JsonProcess,SonicProcess
from record_capture import archive_capture,archive_body


def run(config,record_path,images,output,seconds=1,joint_interpolation_s=None):
    output=Path(output); output.mkdir(exist_ok=False)
    record=json.loads(Path(record_path).read_text()); template=copy.deepcopy(record['frames'][0]['capture'])
    for role,image in template['images'].items():
        blob=(Path(images)/('00-'+role+'.jpg')).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=image['sha256']: raise ValueError('Fixture image SHA')
        image['jpeg']=base64.b64encode(blob).decode()
    def history(seq):
        frames=[]
        for i in range(10):
            frame=copy.deepcopy(template['g1_state']); frame['tick']=seq+i
            frame['receive_monotonic_s']=10000+(seq+i)*.02; frames.append(frame)
        return frames
    class CameraFixture:
        closed=False
        def send(self,request):
            self.seq=request['seq']
            if self.seq==0: self.epoch=time.monotonic()
        def read(self):
            time.sleep(max(0,self.epoch+self.seq/30-time.monotonic()))
            packet=copy.deepcopy(template); packet.update(seq=self.seq,schema_version=2,capture_age_s=0.,robot_commands_sent=False)
            packet['g1_state_history']=history(self.seq); packet['g1_state']=packet['g1_state_history'][-1]
            for image in packet['images'].values(): image['frame_counter']=self.seq+1
            return packet
        def finish(self): self.close()
        def close(self): self.closed=True
    class BodyFixture:
        seq=0
        closed=False
        def start(self): pass
        def read(self):
            result=dict(body_history=history(self.seq),source_age_s=0.,received_at=time.monotonic()); self.seq+=1
            return result
        def stop(self): self.close()
        def close(self): self.closed=True
    source=Path(__file__).resolve().parent; stage=source.parent; children=[]; logs=[]
    report=dict(passed=False,robot_commands_sent=False,hardware_ready=False)
    def log(name):
        file=(output/(name+'.stderr.log')).open('w'); logs.append(file); return file
    try:
        root=Path(config['gpu_root']); ikroot=Path(config['ik_deployment']); models=Path(config['sonic_models'])
        actor=JsonProcess([root/'.venv-gpu/bin/python','-I',source/'probe_gpu_images.py','--root',root,
            '--policy-bundle',source/'policy-bundle.json',
            '--images',output,'--packet-width','--stream','--frames',str(30*seconds+3),
            '--warmup-steps','3'],log('act'),startup_timeout=90); children.append(actor)
        if actor.ready.get('model_sha256')!=record['gpu']['model_sha256']: raise ValueError('ACT checkpoint mismatch')
        ik=JsonProcess([ikroot/'.venv/bin/python','-I',source/'sonic_ik_worker.py','--urdf',
            ikroot/'artifacts/models/g1_pika_closed.urdf','--input-mode','measured'],log('ik')); children.append(ik)
        observer=JsonProcess([root/'.venv-gpu/bin/python','-I',source/'sonic_observation_worker.py'],log('observation')); children.append(observer)
        sonic=SonicProcess(stage/'sonic_offline_infer',models/'model_encoder.onnx',models/'model_decoder.onnx',log('sonic')); children.append(sonic)
        report=run_online_loop(actor,ik,observer,sonic,CameraFixture(),BodyFixture(),seconds=seconds,
                               joint_interpolation_s=joint_interpolation_s,
                               capture_recorder=lambda packet: archive_capture(output,packet),
                               body_recorder=lambda seq,history: archive_body(output,seq,history))
        report['act_provenance']=actor.ready
    except Exception as exc: report.update(passed=False,error=type(exc).__name__+': '+str(exc))
    finally:
        for child in children: child.close()
        for file in logs: file.close()
        report.update(scope='online_coordinator_with_SYNTHETIC_input_IO_fixture_real_models',
            g1_connected=False,physical_dynamics_verified=False,actual_sensor_freshness_verified=False,
            input_history='repeated_archived_snapshot_with_artificial_timestamps_NOT_actual_50Hz_history',
            source_sha256=hashlib.sha256(Path(record_path).read_bytes()).hexdigest(),
            worker_exit_codes=[child.process.returncode for child in children],requested_seconds=seconds)
        (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('outputs','policy_records','policy_timings','body_timings')},indent=2))
    return 0 if report['passed'] else 1
