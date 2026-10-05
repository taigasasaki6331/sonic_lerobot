"""Pure input/protocol tests; fake workers, no sensors, sockets, or physics."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from online_record_loop import camera_age,run_online_loop
from online_record_config import load_online
from record_capture import archive_capture,archive_body
from verify_online_record import verify
from online_input_sources import REMOTE_CLEANUP
with patch.dict(sys.modules,{'cv2':Mock()}):
    from g1_camera_stream import fresh_pair


def packet(seq=0):
    history=[dict(q=[0.]*35,dq=[0.]*35,quaternion=[1.,0,0,0],gyroscope=[0.]*3,
                  tick=seq+i,receive_monotonic_s=10000+(seq+i)*.02) for i in range(10)]
    return dict(schema_version=2,seq=seq,robot_commands_sent=False,capture_age_s=.001,
        images={role:dict(frame_counter=seq+1,jpeg='fixture_not_decoded_by_fake_actor') for role in ('realsense_rgb','fisheye')},
        g1_state=history[-1],g1_state_history=history,
        gripper=dict(width_m=.04,width_source='encoder_with_legacy_linkage_geometry'))


class Worker:
    def __init__(self,role):
        self.role=role; self.closed=False; self.process=Mock(); self.process.wait.return_value=0
        self.ready=dict(ready=True)
        if role in ('ik','observer'):
            self.ready.update(mode='measured_input_record_only' if role=='ik' else 'measured_record_only',hardware_output_enabled=False)
    def send(self,value): self.request=value
    def read(self,timeout=None):
        r=self.request
        if r.get('op')=='stop': return dict(stopped=True)
        if self.role=='actor': return dict(seq=r['seq'],action=[0,0,0,1,0,0,0,1,0,.04])
        if self.role=='ik':
            return dict(seq=r['seq'],hardware_output_enabled=False,result=dict(absolute_reference=dict(gripper_width_m=.04),ik={}))
        return dict(hardware_output_enabled=False,result={'seq':r.get('seq',0)})
    def infer(self,row): return dict(seq=row['seq'],raw_action_isaaclab=[0.]*29,q_target_hardware=[0.]*29,gripper_width_m=.04,gripper_actuated=False)
    def stop(self): self.close()
    def close(self): self.closed=True


class Camera:
    closed=False
    def send(self,value):
        import time
        self.seq=value['seq']
        if self.seq==0: self.epoch=time.monotonic()
    def read(self):
        import time
        time.sleep(max(0,self.epoch+self.seq/30-time.monotonic()))
        return packet(self.seq)
    def finish(self): self.close()
    def close(self): self.closed=True


class Body:
    closed=False
    seq=0
    def start(self): pass
    def read(self):
        import time
        value=dict(body_history=packet(self.seq)['g1_state_history'],source_age_s=.001,received_at=time.monotonic())
        self.seq+=1; return value
    def stop(self): self.close()
    def close(self): self.closed=True


class Tests(unittest.TestCase):
    def test_camera_pair_requires_new_recent_actual_receives(self):
        frames={role:('jpeg',1.,10) for role in ('fisheye','realsense_rgb')}
        self.assertTrue(fresh_pair(frames,{},1.02))
        self.assertFalse(fresh_pair(frames,{},1.03))
        self.assertFalse(fresh_pair(frames,{},.99))
        self.assertFalse(fresh_pair(frames,{'fisheye':10},1.02))
        self.assertFalse(fresh_pair({'fisheye':frames['fisheye']},{},1.02))

    def test_cleanup_only_own_input_process(self):
        # /proc may be mounted from an ancestor PID namespace in Cloud. Its
        # process numbers cannot safely be used with this namespace's kill().
        import os
        status=Path('/proc/self/status').read_text().splitlines()
        proc_pid=int(next(line for line in status if line.startswith('Pid:')).split()[1])
        if proc_pid!=os.getpid(): self.skipTest('/proc PID namespace differs from local kill namespace; no signals attempted')
        with tempfile.TemporaryDirectory(prefix='g1-pika-online-',dir='/tmp') as folder:
            path=Path(folder)/'body_history_service.py'
            path.write_text("import time\nprint('ready',flush=True)\ntime.sleep(30)\n")
            own=subprocess.Popen([sys.executable,'-I',str(path)],stdout=subprocess.PIPE,text=True)
            unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
            try:
                self.assertEqual(own.stdout.readline().strip(),'ready')
                result=subprocess.run([sys.executable,'-c',REMOTE_CLEANUP,folder],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(json.loads(result.stdout)['confirmed'])
                self.assertEqual(own.wait(timeout=1),-15)
                self.assertIsNone(unrelated.poll())
                rejected=subprocess.run([sys.executable,'-c',REMOTE_CLEANUP,'/tmp'],capture_output=True,text=True,timeout=2)
                self.assertNotEqual(rejected.returncode,0)
            finally:
                for child in (own,unrelated):
                    if child.poll() is None: child.terminate()
                    child.wait(timeout=2)
                own.stdout.close()

    def test_age_different_host_clock(self):
        self.assertAlmostEqual(camera_age(packet(),0,{},2.,2.01),.011)

    def test_server_processing_not_double_counted(self):
        value=packet(); value['request_processing_s']=.02; value['capture_age_s']=.03
        self.assertAlmostEqual(camera_age(value,0,{},2.,2.025),.035)
        for duration in (-.01,.026,float('nan'),True):
            value['request_processing_s']=duration
            with self.subTest(duration=duration),self.assertRaises(ValueError): camera_age(value,0,{},2.,2.025)

    def test_camera_repeat(self):
        counts={}; camera_age(packet(),0,counts,2,2.01)
        with self.assertRaises(ValueError): camera_age(packet(),0,counts,2.02,2.03)

    def test_bad_envelopes(self):
        for key,value in [('schema_version',1),('schema_version',True),('seq',False),
                          ('robot_commands_sent',True),('capture_age_s',float('nan')),('capture_age_s',.11)]:
            value_packet=packet(); value_packet[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): camera_age(value_packet,0,{},2,2.01)

    def test_missing_real_history(self):
        value=packet(); value['g1_state_history']=value['g1_state_history'][:1]
        with self.assertRaises(ValueError): camera_age(value,0,{},2,2.01)

    def test_transport_expiry(self):
        with self.assertRaises(ValueError): camera_age(packet(),0,{},2,2.2)

    def test_bound_online_loop_lifecycle_with_fake_workers(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        report=run_online_loop(*workers,camera,body,seconds=1)
        self.assertTrue(report['passed'],report.get('error'))
        self.assertEqual(report['policy_count'],33); self.assertEqual(report['control_count'],50)
        self.assertTrue(all(worker.closed for worker in workers)); self.assertTrue(camera.closed and body.closed)
        self.assertFalse(report['robot_commands_sent'])

    def test_startup_failure_closes_all(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        workers[1].ready['mode']='archived_record_only'
        report=run_online_loop(*workers,camera,body,seconds=1)
        self.assertFalse(report['passed']); self.assertTrue(all(worker.closed for worker in workers))
        self.assertTrue(camera.closed and body.closed)

    def test_online_loop_delivers_sonic_outputs_to_optional_body_sink(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        sink=Mock()
        sink.receive.side_effect=lambda seq,frame,result,**kw: dict(seq=seq,source_body_tick=frame['tick'],
            decision='gated_initial_pose_not_ready',robot_commands_sent=False)
        report=run_online_loop(*workers,camera,body,seconds=1,body_sink=sink)
        self.assertTrue(report['passed'],report.get('error')); self.assertEqual(sink.receive.call_count,50)
        self.assertEqual(len([o for o in report['outputs'] if 'body_boundary' in o]),50)
        sink.start.assert_called_once(); sink.stop.assert_called_once(); sink.close.assert_called_once()

    def test_body_sink_failure_closes_input_and_gpu_workers(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        sink=Mock(); sink.receive.side_effect=ValueError('body boundary rejection')
        report=run_online_loop(*workers,camera,body,seconds=1,body_sink=sink)
        self.assertFalse(report['passed']); self.assertIn('body boundary rejection',report['error'])
        self.assertTrue(all(worker.closed for worker in workers)); self.assertTrue(camera.closed and body.closed)
        sink.stop.assert_called_once(); sink.close.assert_called_once()

    def test_online_loop_real_body_handler_with_fake_inference_workers(self):
        import time
        from sonic_body_bridge import BodyRecordWorker,BodyRecordClient
        from record_session import RecordSession
        from check_body_lifecycle import profile
        from body_lifecycle import DEFAULT
        from sonic_process import strict_message
        worker=BodyRecordWorker(profile(),strict_message(DEFAULT.read_bytes()),time.monotonic)
        class Channel:
            def send(self,value): self.reply=worker.handle(value)
            def read(self): return self.reply
            def close(self): pass
        session=RecordSession(Channel(),'online-fixture-body',dict(max_source_age_s=.1,max_roundtrip_s=.1,max_tick_gap_s=.1))
        sink=BodyRecordClient(session,profile()['names'])
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]
        report=run_online_loop(*workers,Camera(),Body(),seconds=1,body_sink=sink)
        self.assertTrue(report['passed'],report.get('error'))
        self.assertEqual(worker.bridge.gated,50); self.assertEqual(worker.bridge.accepted,0)
        self.assertEqual(worker.phase,'stopped'); self.assertEqual(worker.bridge.lifecycle.phase,'stop_required')
        self.assertTrue(all(o['body_boundary']['gripper_width_m']==.04 for o in report['outputs']))

    def test_body_sink_stop_failure_does_not_skip_other_worker_cleanup(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        workers[1].ready['mode']='bad'
        sink=Mock(); sink.stop.side_effect=RuntimeError('lost body sink')
        with self.assertRaisesRegex(RuntimeError,'lost body sink'):
            run_online_loop(*workers,camera,body,seconds=1,body_sink=sink)
        self.assertTrue(all(worker.closed for worker in workers)); self.assertTrue(camera.closed and body.closed)
        sink.close.assert_called_once()

    def test_camera_failure_joins_and_closes_workers(self):
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        camera.read=Mock(side_effect=RuntimeError('camera disconnected'))
        report=run_online_loop(*workers,camera,body,seconds=1)
        self.assertFalse(report['passed'])
        self.assertIn('camera disconnected',str(report['worker_errors']))
        self.assertTrue(all(worker.closed for worker in workers))
        self.assertTrue(camera.closed and body.closed)

    def test_camera_prefetch_during_inference(self):
        import threading
        workers=[Worker(role) for role in ('actor','ik','observer','sonic')]; camera=Camera(); body=Body()
        next_capture=threading.Event(); original_camera=camera.read; original_actor=workers[0].read
        def read_camera():
            if camera.seq==1: next_capture.set()
            return original_camera()
        def read_actor(timeout=None):
            if workers[0].request['seq']==0:
                if not next_capture.wait(.08): raise RuntimeError('Acquisition was serialized behind ACT')
            return original_actor(timeout)
        camera.read=read_camera; workers[0].read=read_actor
        report=run_online_loop(*workers,camera,body,seconds=1)
        self.assertTrue(report['passed'],report.get('error'))
        self.assertTrue(next_capture.is_set())

    def test_config_rejects_motor_output(self):
        root=Path(__file__).resolve().parents[1]
        original=load_online(root/'config/online-record.json')
        with tempfile.TemporaryDirectory() as folder:
            for key,value in [('hardware_output_enabled',True),('seconds',0),('mode','live'),('body_endpoint','tcp://0.0.0.0:6159')]:
                config=copy.deepcopy(original); config[key]=value
                path=Path(folder)/'config.json'; path.write_text(json.dumps(config))
                with self.assertRaises(ValueError): load_online(path)

    def test_read_ack_required_before_ssh(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-I',str(root/'scripts/run_full_record_check.py'),
            '--online-config',str(root/'config/online-record.json')],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,2); self.assertIn('no G1 connection made',result.stderr)

    def test_capture_archive_no_overwrite_or_packet_mutation(self):
        import base64
        capture=packet()
        for image in capture['images'].values(): image['jpeg']=base64.b64encode(b'test_bytes_not_camera').decode()
        original=copy.deepcopy(capture)
        with tempfile.TemporaryDirectory() as folder:
            saved=archive_capture(folder,capture)
            self.assertEqual(capture,original)
            self.assertNotIn('jpeg',saved['images']['fisheye'])
            self.assertEqual((Path(folder)/saved['images']['fisheye']['file']).read_bytes(),b'test_bytes_not_camera')
            self.assertEqual(archive_capture(folder,capture),saved)
            self.assertEqual(len(list(Path(folder).glob('*.jpg'))),1)
            (Path(folder)/saved['images']['fisheye']['file']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): archive_capture(folder,capture)

    def test_archive_integrity_and_tamper_rejection(self):
        import base64
        capture=packet()
        for image in capture['images'].values(): image['jpeg']=base64.b64encode(b'fixture').decode()
        with tempfile.TemporaryDirectory() as folder:
            saved=archive_capture(folder,capture); body=archive_body(folder,0,capture['g1_state_history'])
            report=dict(passed=True,scope='online_coordinator_with_SYNTHETIC_input_IO_fixture_real_models',
                robot_commands_sent=False,hardware_ready=False,worker_exit_codes=[0]*4,policy_count=1,control_count=1,
                policy_records=[dict(seq=0,action=dict(seq=0,action=[0.]*9+[.04]),capture=saved)],
                outputs=[dict(seq=0,policy_seq=0,source_body_tick=9,body_input_record=body,
                    diagnostic_output=dict(raw_action_isaaclab=[0.]*29,q_target_hardware=[0.]*29,
                                           gripper_width_m=.04,gripper_actuated=False))])
            path=Path(folder)/'report.json'; path.write_text(json.dumps(report))
            result=verify(path); self.assertTrue(result['integrity_passed'])
            self.assertEqual(result['declared_input_kind'],'synthetic_fixture')
            (Path(folder)/body['file']).write_text('{}')
            with self.assertRaises(ValueError): verify(path)


if __name__=='__main__': unittest.main()
