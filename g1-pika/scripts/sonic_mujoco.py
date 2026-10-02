"""MuJoCo physics -> pinned SONIC stdio -> PD -> MuJoCo; NO hardware IO.

No Unitree SDK/DDS/MotionSwitcher is imported. This is a synchronous sim-time
closed loop, not a real-time deadline or deployment/physical safety test.
"""
import argparse
from collections import deque
import hashlib
import math
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mujoco
import numpy as np
from sonic_observation import ObservationBuilder
from sonic_process import SonicProcess, strict_message

MODEL_HASHES={'model_encoder.onnx':'60be43157f57d812f38bdbb740a5de5d5d070e8840d9edc16f02a91a6d06255b',
              'model_decoder.onnx':'c4ac2e74045e7cbfb568f15e6bf47ea7ce023df7a94322af50be223e0a628bab'}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_timing(seconds,warmup):
    if (not np.isfinite(seconds) or not .1<=seconds<=60 or not np.isfinite(warmup) or not .2<=warmup<=5
            or abs(seconds/.02-round(seconds/.02))>1e-7 or abs(warmup/.02-round(warmup/.02))>1e-7):
        raise ValueError('Policy duration .1..60s and PD warmup .2..5s must align with 20ms control ticks')


def layout(model, names):
    if (model.nq,model.nv,model.nu)!=(36,35,29) or model.neq!=0 or model.jnt_type[0]!=mujoco.mjtJoint.mjJNT_FREE:
        raise ValueError('Require an unconstrained free-base 29-joint G1')
    joint_ids=np.array([model.joint(name).id for name in names])
    if len(set(joint_ids))!=29: raise ValueError('Duplicate body joint')
    actuator_ids=[]
    for joint in joint_ids:
        matches=np.flatnonzero(model.actuator_trnid[:,0]==joint)
        if len(matches)!=1: raise ValueError('Missing/duplicate body actuator')
        actuator_ids.append(int(matches[0]))
    return joint_ids,np.array(actuator_ids)


def body_state(model,data,joints):
    mujoco.mj_forward(model,data)
    q=data.qpos[model.jnt_qposadr[joints]].copy()
    dq=data.qvel[model.jnt_dofadr[joints]].copy()
    pelvis=model.body('pelvis').id
    quat=data.xquat[pelvis].copy(); quat/=np.linalg.norm(quat)
    velocity=np.zeros(6)
    # BODY uses the inertial axes, not the pelvis/IMU axes. XBODY uses the
    # regular body frame (MuJoCo 3.3.4 engine_support.c mj_objectVelocity).
    mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_XBODY,pelvis,velocity,1)
    return dict(q=q,dq=dq,gyro=velocity[:3].copy(),quat=quat)


def write_json(path,value):
    with Path(path).open('x') as file: json.dump(value,file,allow_nan=False,indent=2); file.write('\n')


def run(args):
    args.output.mkdir(exist_ok=False)
    profile=strict_message(args.profile.read_bytes()); builder=ObservationBuilder()
    if not np.array_equal(builder.defaults,np.asarray(profile['defaults'],dtype=np.float32).astype(float)):
        # Source Python parses decimal defaults; SDK constants are float32. Use
        # exact source tolerance only, not a posture safety threshold.
        if np.max(abs(builder.defaults-np.asarray(profile['defaults'])))>1e-6: raise ValueError('Default source mismatch')
    hashes={name:sha(args.models/name) for name in MODEL_HASHES}
    if hashes!=MODEL_HASHES: raise ValueError('SONIC model SHA mismatch')
    cache_hashes={name:sha(args.models/name) for name in ('model_encoder.trt','model_decoder.trt')}
    model=mujoco.MjModel.from_xml_path(str(args.model)); joints,actuators=layout(model,profile['names'])
    model.opt.timestep=.002; data=mujoco.MjData(model)
    qadr=model.jnt_qposadr[joints]; vadr=model.jnt_dofadr[joints]
    defaults=np.asarray(profile['defaults']); kp=np.asarray(profile['kp']); kd=np.asarray(profile['kd'])
    initial_q=defaults.copy()
    data.qpos[qadr]=initial_q; mujoco.mj_forward(model,data)
    qhist=deque(maxlen=10); dqhist=deque(maxlen=10); ghist=deque(maxlen=10); rhist=deque(maxlen=10)
    ahist=np.zeros((10,29)); reference_q=np.tile(initial_q,(10,1)); reference_dq=np.zeros((10,29))
    reference_quat=np.tile([1.,0.,0.,0.],(10,1))
    target=initial_q.copy(); observations=[]; records=[]; trajectory=[]; latencies=[]
    start_xy=data.qpos[:2].copy(); warnings_before=data.warning.number.copy()
    renderer=None; encoder=None; video_frames=0; worker=None; gateway=None; reason='duration_completed'
    bounds=model.jnt_range[joints]; outside_target=0; outside_measured=0
    control_seq=0; target_steps=[]; previous_target=target.copy(); start=time.monotonic()
    height=[]; tilt=[]; xy=[]; tracking=[]; policy_started=None
    ik=None; teacher=None; origin=None; planned_q=initial_q.copy(); actor=None; actor_records=[]; desired=None
    transition=None; teacher_travel_origin=None; transition_seconds=2.
    tcp_errors=[]; orientation_errors=[]; tcp_travel=[]; ik_errors=[]
    replay_tcp_errors=[]; replay_orientation_errors=[]
    act_tcp_origin=None; act_tcp_travel=[]
    if args.teacher:
        from teacher_trajectory import TeacherTrajectory
        from sonic_tcp_reference import TcpReference
        from sonic_joint_trajectory import JointTrajectory
        teacher=TeacherTrajectory(strict_message(args.teacher.read_bytes()))
        if args.seconds < transition_seconds+teacher.required_seconds:
            raise ValueError('Duration must include 2s reference transition, complete teacher replay and settles')
        ik=TcpReference(args.urdf)
        if ik.names != profile['names']: raise ValueError('IK/SONIC name order mismatch')
        neutral=defaults.copy(); neutral[15:]=0.; neutral[16]=.2; neutral[23]=-.2
        origin=ik.tcp_pose(neutral)
        transition=JointTrajectory(defaults,np.zeros(29),now=0.,duration_s=transition_seconds)
        transition.update(neutral,now=0.)
    report=dict(passed=False,robot_commands_sent=False,hardware_ready=False,g1_connected=False,
        plant_sha256=sha(args.model),policy_models_sha256=hashes,
        warmup_sim_seconds=args.warmup,requested_policy_sim_seconds=args.seconds,
        floating_base=True,elastic_band=False,root_resets_during_steps=False,
        cache_sha256_before=cache_hashes)
    try:
        if getattr(args,'body_gateway',None):
            from sim_body_gateway import SimBodyGateway
            gateway=SimBodyGateway(args.body_gateway,profile)
        if args.lerobot:
            from sonic_tcp_reference import TcpReference
            from sonic_sim_actor import SimActor
            ik=TcpReference(args.urdf)
            if ik.names != profile['names']: raise ValueError('IK/SONIC name order mismatch')
            actor=SimActor(args.act_root,args.act_images,args.act_record,args.act_bundle,args.output,math.ceil(args.seconds*30))
        if args.video:
            renderer=mujoco.Renderer(model,height=480,width=640)
            encoder=subprocess.Popen(['ffmpeg','-loglevel','error','-nostdin','-y','-f','rawvideo',
                '-pixel_format','rgb24','-video_size','640x480','-framerate','25','-i','pipe:0',
                '-an','-vcodec','libx264','-pix_fmt','yuv420p',str(args.output/'simulation.mp4')],stdin=subprocess.PIPE)
        log=(args.output/'sonic.stderr.log').open('x')
        worker=SonicProcess(args.binary,args.models/'model_encoder.onnx',args.models/'model_decoder.onnx',log)
        for step in range(round((args.warmup+args.seconds)/model.opt.timestep)):
            # Ten observations are collected by actually stepping PD physics.
            # No repeated or invented frames, root resets or elastic band.
            if step%10==0:
                state=body_state(model,data,joints)
                qhist.append(state['q']); dqhist.append(state['dq']); ghist.append(state['gyro']); rhist.append(state['quat'])
                if data.time>=args.warmup-1e-9 and len(qhist)==10:
                    if policy_started is None: policy_started=float(data.time)
                    width=.04; candidate=None
                    if teacher:
                        elapsed=float(data.time)-policy_started
                        # A planned teacher pose must not adopt each disturbed
                        # lower-body/left-arm measurement as its next goal.
                        # Lock those reference DOFs to the original plan; SONIC
                        # still receives every actual body observation below.
                        teacher_time=elapsed-transition_seconds
                        desired=teacher.target(teacher_time,origin)
                        frame=min(len(teacher.payload['frames'])-1,max(0,int((teacher_time-teacher.settle)*teacher.payload['fps'])))
                        width=teacher.payload['frames'][frame]['action'][9]
                        if elapsed<transition_seconds:
                            reference_q,reference_dq,_=transition.window(now=elapsed)
                            planned_q=reference_q[0].copy()
                            desired=ik.tcp_pose(planned_q)
                        else:
                            if teacher_time<.02: planned_q=neutral.copy()
                            candidate=ik.candidate_pose(desired,width,planned_q)
                            if not candidate['kinematic_target_within_diagnostic_tolerance']:
                                report['failed_candidate']=candidate
                                raise ValueError('Teacher IK candidate outside diagnostic tolerance')
                            planned_q=np.asarray(candidate['q_reference_hardware'])
                            reference_q=np.tile(planned_q,(10,1)); reference_dq=np.zeros((10,29))
                        # Evaluate physical TCP separately from IK prediction.
                        body=model.body('right_pika_tcp').id
                        pelvis=model.body('pelvis').id
                        rotation=data.xmat[pelvis].reshape(3,3)
                        actual=np.eye(4); actual[:3,3]=rotation.T@(data.xpos[body]-data.xpos[pelvis])
                        actual[:3,:3]=rotation.T@data.xmat[body].reshape(3,3)
                        if np.max(abs(actual-ik.tcp_pose(state['q'])))>1e-7:
                            raise ValueError('MuJoCo/IK measured TCP FK disagreement')
                        tcp_errors.append(float(np.linalg.norm(actual[:3,3]-desired[:3,3])))
                        orientation_errors.append(float(np.arccos(np.clip((np.trace(actual[:3,:3].T@desired[:3,:3])-1)/2,-1,1))))
                        if teacher_time>=teacher.settle:
                            if teacher_travel_origin is None: teacher_travel_origin=actual[:3,3].copy()
                            tcp_travel.append(float(np.linalg.norm(actual[:3,3]-teacher_travel_origin)))
                            replay_tcp_errors.append(tcp_errors[-1]); replay_orientation_errors.append(orientation_errors[-1])
                        if candidate: ik_errors.append(max(e['position_m'] for e in candidate['errors'].values()))
                    if actor and (len(actor_records)==0 or
                            float(data.time)-policy_started >= len(actor_records)/30-1e-8):
                        from policy_action import policy_target
                        predicted=actor.infer()
                        measured_tcp=ik.tcp_pose(state['q'])
                        if act_tcp_origin is None: act_tcp_origin=measured_tcp[:3,3].copy()
                        act_tcp_travel.append(float(np.linalg.norm(measured_tcp[:3,3]-act_tcp_origin)))
                        desired,width=policy_target(predicted['action'],measured_tcp,
                            action_reference='local-relative-h1',rotation_layout='columns')
                        candidate=ik.candidate_pose(desired,width,planned_q)
                        if not candidate['kinematic_target_within_diagnostic_tolerance']:
                            report['failed_candidate']=candidate
                            raise ValueError('ACT IK candidate outside diagnostic tolerance')
                        planned_q=np.asarray(candidate['q_reference_hardware'])
                        reference_q=np.tile(planned_q,(10,1))
                        actor_records.append(dict(sim_time_s=float(data.time),prediction=predicted,candidate=candidate))
                    if actor:
                        width=actor_records[-1]['prediction']['action'][9]
                    row=dict(seq=control_seq,gripper_width_m=width,gripper_actuated=False,
                        encoder=builder.encoder(reference_q,reference_dq,reference_quat,state['quat']).tolist(),
                        decoder_tail=builder.decoder_tail(list(qhist),list(dqhist),list(ghist),list(rhist),ahist).tolist())
                    result=worker.infer(row); target=np.asarray(result['q_target_hardware'])
                    if target.shape!=(29,) or not np.isfinite(target).all(): raise ValueError('Invalid SONIC target')
                    raw=np.asarray(result['raw_action_isaaclab'])
                    if raw.shape!=(29,) or not np.isfinite(raw).all(): raise ValueError('Invalid SONIC raw action')
                    ahist=np.concatenate((ahist[1:],raw[None,:]),axis=0)
                    target_steps.append(float(np.max(abs(target-previous_target)))); previous_target=target.copy()
                    latencies.append(result['encoder_decoder_wall_ms'])
                    outside_target+=int(np.any((target<bounds[:,0])|(target>bounds[:,1])))
                    outside_measured+=int(np.any((state['q']<bounds[:,0])|(state['q']>bounds[:,1])))
                    tracking.append(float(np.max(abs(target-state['q']))))
                    observations.append(dict(sim_time_s=float(data.time),row=row))
                    records.append(dict(sim_time_s=float(data.time),result=result,measured_q=state['q'].tolist(),candidate=candidate,
                        tcp_diagnostic=(dict(actual=actual.tolist(),desired=desired.tolist(),
                            teacher_time_s=teacher_time,position_error_m=tcp_errors[-1],
                            orientation_error_rad=orientation_errors[-1]) if teacher else None)))
                    control_seq+=1
            # Physical actuator limits belong to the MuJoCo model. Do NOT clip
            # policy target angles or alter raw-action recurrence to pass tests.
            if gateway:
                if step%10==0: gateway.reference(float(data.time),target)
                torque=gateway.tick(float(data.time),data.qpos[qadr],data.qvel[vadr])
            else:
                torque=kp*(target-data.qpos[qadr])-kd*data.qvel[vadr]
            data.ctrl[actuators]=torque
            mujoco.mj_step(model,data)
            pelvis=model.body('pelvis').id; z=float(data.xpos[pelvis,2])
            angle=float(np.arccos(np.clip(data.xmat[pelvis].reshape(3,3)[2,2],-1,1)))
            distance=float(np.linalg.norm(data.qpos[:2]-start_xy))
            height.append(z); tilt.append(angle); xy.append(distance)
            if step%20==0: trajectory.append(dict(sim_time_s=float(data.time),qpos=data.qpos.tolist()))
            if renderer is not None and step%20==0:
                camera=mujoco.MjvCamera(); camera.lookat[:]=data.xpos[pelvis]; camera.distance=2.8
                camera.azimuth=135; camera.elevation=-20
                renderer.update_scene(data,camera=camera); encoder.stdin.write(renderer.render().tobytes()); video_frames+=1
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all(): reason='nonfinite_physics'; break
            if np.any(data.warning.number>warnings_before): reason='mujoco_warning'; break
            if z<.45 or angle>.8: reason='fall_threshold'; break
        worker.stop(); exit_code=worker.process.returncode
        actor_exit=actor.stop() if actor else None
        report=dict(passed=reason=='duration_completed' and outside_target==0 and outside_measured==0,
            scope='SONIC_MuJoCo_dynamic_closed_loop_default_reference_NO_LeRobot_'+('fixed_PIKA' if args.pika else 'NO_PIKA'),
            termination_reason=reason,requested_policy_sim_seconds=args.seconds,sim_seconds=float(data.time),
            warmup_sim_seconds=args.warmup,policy_started_sim_s=policy_started,control_count=control_seq,
            height_min_m=min(height),height_final_m=height[-1],tilt_max_rad=max(tilt),xy_max_m=max(xy),
            target_outside_model_count=outside_target,measured_outside_model_count=outside_measured,
            max_target_step_rad=max(target_steps,default=0.),max_joint_target_tracking_error_rad=max(tracking,default=0.),
            inference_p95_ms=float(np.percentile(latencies,95)) if latencies else None,
            worker_exit_code=exit_code,physics_hz=500,policy_hz=50,realtime_guaranteed=False,
            timing_scope='synchronous_simulation_time; physics pauses during inference',
            plant_source=('existing generated g1_pika_closed.xml; grippers fixed, legacy inertias' if args.pika else
                'fixed Decoupled asset g1_gear_wbc.xml')+'; controller is SONIC, NOT old balance',
            policy_models_sha256=hashes,plant_sha256=sha(args.model),profile_sha256=sha(args.profile),
            robot_total_mass_kg=float(np.sum(model.body_mass)),
            thresholds=dict(min_height_m=.45,max_tilt_rad=.8),
            model_warning_count=int(np.sum(data.warning.number-warnings_before)),
            hardware_ready=False,robot_commands_sent=False,g1_connected=False,
            floating_base=True,elastic_band=False,root_resets_during_steps=False,
            initial_pose_source='pinned SONIC defaults; direct simulation initialization NOT hardware INIT',
            observation_history_source='actual simulated physics samples; raw-action zero before policy start',
            armature_range=model.dof_armature[vadr].tolist(),wall_seconds=time.monotonic()-start,
            cache_sha256_before=cache_hashes,mujoco_version=mujoco.__version__,numpy_version=np.__version__,
            gyro_frame='pelvis regular body XBODY; no synthetic noise',
            motor_torque_saturation='native model actuatorfrcrange; target angles are NOT clipped')
        if teacher:
            report.update(scope='teacher_TCP_IK_SONIC_MuJoCo_dynamic_closed_loop_fixed_PIKA_NO_LeRobot',
                teacher_sha256=sha(args.teacher),urdf_sha256=ik.urdf_sha256,
                teacher={**teacher.metrics(float(data.time)-policy_started-transition_seconds),
                    'teacher_reanchored_to_initial_tcp':False,
                    'teacher_reanchored_to_planned_neutral_tcp':True},
                initial_reference_transition_s=transition_seconds,
                minimum_total_policy_sim_seconds=transition_seconds+teacher.required_seconds,
                reference_mode='planned_default_lower_body_left_arm_IK_endpoint_10_frames_dq_zero_not_balance_plan',
                ik_seed_source='previous_kinematic_reference_not_measured',
                teacher_anchor='right_TCP_at_legacy_teacher_neutral_arm_reference_in_pelvis',
                tcp_position_error_max_m=max(tcp_errors),tcp_orientation_error_max_rad=max(orientation_errors),
                right_tcp_travel_max_m=max(tcp_travel),ik_position_error_max_m=max(ik_errors))
            report.update(teacher_replay_tcp_error_max_m=max(replay_tcp_errors),
                teacher_replay_orientation_error_max_rad=max(replay_orientation_errors),
                teacher_replay_tracking_within_threshold=bool(max(replay_tcp_errors)<=.05 and max(replay_orientation_errors)<=.3),
                teacher_replay_metric_scope='after 2s reference transition + 2s teacher settle; NOT overall pass criterion replacement')
            report['thresholds'].update(max_tcp_error_m=.05,max_tcp_orientation_error_rad=.3,min_tcp_travel_m=.04)
            report['passed'] &= (report['teacher']['teacher_completed'] and max(tcp_errors)<=.05
                and max(orientation_errors)<=.3 and max(tcp_travel)>=.04)
        if actor:
            report.update(scope='saved_RGB_ACT_actual_sim_TCP_IK_SONIC_MuJoCo_hybrid_fixed_PIKA',
                act_provenance=actor.worker.ready,act_image_sha256=actor.hashes,
                actor_count=len(actor_records),actor_expected_count=actor.frames,actor_exit_code=actor_exit,
                right_tcp_travel_max_m=max(act_tcp_travel,default=0.),
                policy_input_rate_hz=30,policy_schedule='30Hz sim-time queries quantized to 50Hz control ticks',
                camera_closed_loop=False,task_success_validated=False,gripper_actuated=False,
                gripper_width_input='assumed_0.04m_NOT_measured',
                reference_mode='current_measured_TCP_h1_action; IK planned lower body/left arm; endpoint hold')
            report['passed'] &= actor_exit==0 and len(actor_records)==actor.frames
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),control_count=control_seq,sim_seconds=float(data.time))
    finally:
        if gateway:
            try:
                gateway.stop(); body_report=gateway.report()
                write_json(args.output/'body-runtime.json',body_report)
                report['body_runtime']={key:value for key,value in body_report.items() if key!='samples'}
                report['body_gateway_library_sha256']=sha(args.body_gateway)
                report['actuation_path']='SONIC -> native BodyIoAdapter/WriterKernel -> LowCmd float32 -> MuJoCo'
                report['passed'] &= body_report['stop_completed'] and body_report['simulated_restores']==1
            except Exception as exc:
                report['passed']=False; report['body_runtime_error']=type(exc).__name__+': '+str(exc)
            finally: gateway.close()
        if worker: worker.close()
        if actor: actor.close(); report['actor_exit_code']=actor.worker.process.returncode
        if worker: report['worker_exit_code']=worker.process.returncode
        if 'log' in locals(): log.close()
        if renderer: renderer.close()
        if encoder:
            encoder.stdin.close()
            try: video_exit=encoder.wait(timeout=10)
            except subprocess.TimeoutExpired: encoder.kill(); video_exit=encoder.wait(timeout=2)
            report.update(video_frame_count=video_frames,video_exit_code=video_exit)
            if video_exit!=0: report['passed']=False
        report['model_files_unchanged']={name:sha(args.models/name)==digest for name,digest in hashes.items()}
        report['cache_files_unchanged']={name:sha(args.models/name)==digest for name,digest in cache_hashes.items()}
        if not all(report['model_files_unchanged'].values()): report['passed']=False
        if not all(report['cache_files_unchanged'].values()): report['passed']=False
        if not report['passed'] and 'error' in report:
            report.update(height_min_m=min(height,default=None),tilt_max_rad=max(tilt,default=None),
                target_outside_model_count=outside_target,measured_outside_model_count=outside_measured)
        write_json(args.output/'observations.json',dict(observations=observations))
        write_json(args.output/'outputs.json',dict(outputs=records))
        if args.lerobot: write_json(args.output/'actor.json',dict(predictions=actor_records))
        write_json(args.output/'trajectory.json',dict(trajectory=trajectory))
        write_json(args.output/'report.json',report)
        print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model','models','binary','profile','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=5.)
    parser.add_argument('--warmup',type=float,default=1.)
    parser.add_argument('--video',action='store_true')
    parser.add_argument('--pika',action='store_true',help='Label existing fixed-gripper PIKA plant')
    parser.add_argument('--teacher',type=Path)
    parser.add_argument('--urdf',type=Path)
    parser.add_argument('--lerobot',action='store_true')
    parser.add_argument('--body-gateway',type=Path,help='SIM ONLY native command runtime shared library')
    for name in ('act-root','act-images','act-record','act-bundle'): parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    try: validate_timing(args.seconds,args.warmup)
    except ValueError as exc: parser.error(str(exc))
    if args.teacher and (not args.pika or not args.urdf): parser.error('Teacher requires --pika and matched --urdf')
    if args.lerobot and (args.teacher or not args.pika or not args.urdf or
            not all((args.act_root,args.act_images,args.act_record,args.act_bundle)) or args.seconds>30):
        parser.error('ACT requires PIKA, URDF and saved input/bundle paths; no teacher; maximum 30s')
    return run(args)


if __name__=='__main__': raise SystemExit(main())
