"""CPU MuJoCo checks of Balance alone or official WBC plus upper-body IK.

Observation layout and gains follow the pinned NVIDIA sim2mujoco example.
This runner has no robot SDK, transport, keyboard teleop, or hardware mode.
The default holds the arms at zero; --controller wbc exercises upper-body IK.
--pika adds the closed-gripper PIKA model to the WBC check.
"""

import argparse
from collections import deque
from contextlib import nullcontext, redirect_stdout
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import mujoco
import numpy as np
import onnxruntime as ort
import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/GR00T-WholeBodyControl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--controller", choices=("balance", "wbc"), default="balance")
    parser.add_argument("--pika", action="store_true", help="Replace original hands with fixed closed PIKA grippers")
    parser.add_argument("--teacher", type=Path, help="Exported local LeRobot h1 episode JSON")
    parser.add_argument("--playback-rate", type=float, default=1.0, help="Teacher speed; 1 is recorded speed")
    parser.add_argument('--policy-run',type=Path,help='Local ACT run; live CPU inference on recorded validation observations')
    parser.add_argument('--policy-frames',type=int,default=90)
    parser.add_argument('--policy-episode',type=int,default=39)
    parser.add_argument('--policy-fault',choices=['none','stale','invalid','delay','silence'],default='none')
    parser.add_argument('--policy-async',action='store_true')
    parser.add_argument('--policy-endpoint',help='Simulation-only ZMQ inference endpoint')
    parser.add_argument('--policy-session')
    parser.add_argument('--policy-observations',type=Path)
    parser.add_argument('--report-dir',type=Path,default=ROOT/'artifacts')
    parser.add_argument('--policy-reference',choices=['integrated','measured'],default='integrated')
    parser.add_argument('--guard-output',action='store_true',help='Validate and record abstract WBC outputs; no hardware')
    parser.add_argument('--guard-fault',choices=['none','stale','estop','nan','owner','order'],default='none')
    args = parser.parse_args()
    if args.policy_endpoint and (not args.policy_async or not args.policy_session or not args.policy_observations or not args.guard_output):
        parser.error('ZMQ requires async, session, recorded observations and output guard')
    if args.guard_output and args.controller!='wbc': parser.error('--guard-output requires WBC')
    if args.guard_fault!='none' and not args.guard_output: parser.error('--guard-fault requires --guard-output')
    if args.policy_async and not args.policy_run:
        parser.error('--policy-async requires --policy-run')
    if args.policy_fault in ('delay','silence') and not args.policy_async:
        parser.error('delay/silence require --policy-async')
    if args.policy_run:
        if not args.pika or args.controller!='wbc' or args.teacher:
            parser.error('--policy-run requires --pika --controller wbc and no teacher')
        if not 1<=args.policy_frames<=300 or args.policy_episode not in range(39,44):
            parser.error('Policy replay uses 1..300 frames from validation episode 39..43')
        if args.seconds < 4+args.policy_frames/30:
            parser.error('Not enough simulation time for policy replay and settle/hold')
        def no_network(event,values):
            if event in {'socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'}:
                raise RuntimeError('Network forbidden in policy simulation')
        sys.addaudithook(no_network)
    elif args.policy_fault!='none':
        parser.error('--policy-fault requires --policy-run')
    if not np.isfinite(args.seconds) or not 0.1 <= args.seconds <= 120:
        parser.error("--seconds must be between 0.1 and 120")
    if args.controller == "wbc" and args.seconds < 12:
        parser.error("WBC reach check requires at least 12 simulation seconds")
    if args.pika and args.controller != "wbc":
        parser.error("--pika requires --controller wbc")
    teacher = None
    if args.teacher:
        if not args.pika:
            parser.error("--teacher requires --pika and --controller wbc")
        sys.path.insert(0, str(ROOT / "scripts"))
        from teacher_trajectory import TeacherTrajectory
        teacher = TeacherTrajectory(json.loads(args.teacher.read_text()), args.playback_rate)
        if args.seconds < teacher.required_seconds:
            parser.error(f"Teacher needs at least {teacher.required_seconds:.3f} seconds including settle/hold")
    elif args.playback_rate != 1.0:
        parser.error("--playback-rate requires --teacher")

    lock = json.loads((ROOT / "sources.lock.json").read_text())["wbc"]
    revision = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != lock["commit"]:
        raise RuntimeError("WBC checkout does not match sources.lock.json")
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--exit-code", "HEAD"], check=True)
    resources = UPSTREAM / "decoupled_wbc/sim2mujoco/resources/robots/g1"
    policy = resources / "policy/GR00T-WholeBodyControl-Balance.onnx"
    if hashlib.sha256(policy.read_bytes()).hexdigest() != lock["balance_sha256"]:
        raise RuntimeError("Balance model checksum mismatch")
    config = yaml.safe_load((resources / "g1_gear_wbc.yaml").read_text())
    pika_urdf, pika_report = None, {}
    model_path = resources / config["xml_path"]
    if args.pika:
        sys.path.insert(0, str(ROOT / "scripts"))
        from pika_model import build_pika_model

        model_path, pika_urdf, pika_report = build_pika_model(UPSTREAM, ROOT)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    if (model.nq, model.nv, model.nu) != (36, 35, 29):
        raise RuntimeError("Expected a floating-base G1 with 29 actuated joints")
    if model.jnt_type[0] != mujoco.mjtJoint.mjJNT_FREE or model.neq != 0:
        raise RuntimeError("Expected an unconstrained floating base")
    if not np.array_equal(model.actuator_trnid[:, 0], np.arange(1, 30)):
        raise RuntimeError("Unexpected actuator ordering")
    model.opt.timestep = config["simulation_dt"]
    defaults = np.zeros(29, dtype=np.float32)
    defaults[:15] = config["default_angles"]
    if args.controller == "wbc":
        # Match upstream IK's shoulder-clearance limits and initial posture.
        defaults[16], defaults[23] = 0.2, -0.2
    # Start from the configured leg posture, without fixing the base or resetting
    # qpos during stepping. The XML supplies the initial free-base height.
    data.qpos[7:] = defaults
    mujoco.mj_forward(model, data)
    pelvis = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(policy), sess_options=options, providers=["CPUExecutionProvider"]
    )
    if session.get_inputs()[0].shape[-1] != 516 or session.get_outputs()[0].shape[-1] != 15:
        raise RuntimeError("Unexpected Balance network dimensions")
    kp = np.r_[config["kps"], np.full(14, 100.0)]
    kd = np.r_[config["kds"], np.full(14, 0.5)]
    target = defaults.copy()
    whole_body = None
    if args.controller == "wbc":
        sys.path.insert(0, str(ROOT / "scripts"))
        from wbc_controller import WholeBodyController

        with redirect_stdout(sys.stderr):
            whole_body = WholeBodyController(UPSTREAM, lock, model, data, defaults, pika_urdf=pika_urdf, teacher=teacher)
        kp, kd = whole_body.kp, whole_body.kd
    action = np.zeros(15, dtype=np.float32)
    history = deque([np.zeros(86, dtype=np.float32) for _ in range(6)], maxlen=6)
    latencies = []
    heights, tilts, displacements = [], [], []
    warnings_before = data.warning.number.copy()
    start_xy = data.qpos[:2].copy()
    steps = round(args.seconds / model.opt.timestep)
    if args.viewer:
        from mujoco import viewer as mj_viewer

        context = mj_viewer.launch_passive(model, data)
    else:
        context = nullcontext(None)
    bridge=None
    if args.policy_run:
        from policy_replay_bridge import PipePolicy,ReplayBridge
        if args.policy_async:
            from async_policy_bridge import AsyncReplayBridge
            ReplayBridge=AsyncReplayBridge
        if args.policy_endpoint:
            from zmq_policy_client import ZmqPolicyClient
            client=ZmqPolicyClient(args.policy_endpoint,args.policy_session,args.policy_observations,
                                   args.policy_frames,lambda: whole_body.latest_state)
        else:
            client=PipePolicy(args.policy_run,args.policy_episode,args.policy_frames)
        bridge=ReplayBridge(client,
                            args.policy_frames,args.policy_fault,args.policy_reference)
        whole_body.policy_bridge=bridge
    started = time.perf_counter()
    guard=None; sink=None; guard_seq=0; guard_owner=object()
    if args.guard_output:
        from control_guard import ControlGuard,GuardFault,RecordingSink
        joint_names=[mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,i) for i in range(1,30)]
        guard=ControlGuard(joint_names,model.jnt_range[1:30,0],model.jnt_range[1:30,1])
        guard.start_simulation(guard_owner); sink=RecordingSink(guard)
    completed = 0
    viewer_closed = False
    next_render = started
    with (bridge if bridge is not None else nullcontext()), context as viewer:
        for step in range(steps):
            tick = time.perf_counter()
            if viewer is not None and not viewer.is_running():
                viewer_closed = True
                break
            data.ctrl[:] = kp * (target - data.qpos[7:]) - kd * data.qvel[6:]
            if whole_body is not None:
                data.ctrl[:] += whole_body.feedforward(data)
            mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)
            completed = step + 1
            rotation = data.xmat[pelvis].reshape(3, 3)
            gravity = rotation.T @ np.array([0.0, 0.0, -1.0])
            heights.append(float(data.qpos[2]))
            tilts.append(float(np.arccos(np.clip(rotation[2, 2], -1, 1))))
            displacements.append(float(np.linalg.norm(data.qpos[:2] - start_xy)))
            if not np.isfinite(data.qpos).all() or heights[-1] < 0.45 or tilts[-1] > 0.8:
                break
            if completed % config["control_decimation"] == 0:
                if whole_body is not None:
                    with redirect_stdout(sys.stderr):
                        candidate = whole_body.step(data)
                    if guard is not None:
                        fault=args.guard_fault if guard_seq==100 else 'none'
                        command_q=candidate.copy()
                        if fault=='nan': command_q[0]=float('nan')
                        try:
                            frame=guard.approve(owner=object() if fault=='owner' else guard_owner,
                                seq=guard_seq,now=float(data.time),state_time=float(data.time)-(.2 if fault=='stale' else 0),
                                state_q=data.qpos[7:].copy(),names=joint_names[::-1] if fault=='order' else joint_names,
                                q=command_q,dq=np.zeros(29),tau=whole_body.feedforward(data),
                                kp=whole_body.kp,kd=whole_body.kd,estop=fault=='estop')
                            sink.append(frame)
                            candidate=np.asarray(frame['q']); guard_seq+=1
                        except GuardFault:
                            break
                    target=candidate
                else:
                    observation = np.concatenate([
                        np.asarray(config["cmd_init"]) * config["cmd_scale"],
                        [config["height_cmd"]], config["rpy_cmd"],
                        data.qvel[3:6] * config["ang_vel_scale"], gravity,
                        (data.qpos[7:] - defaults) * config["dof_pos_scale"],
                        data.qvel[6:] * config["dof_vel_scale"], action,
                    ]).astype(np.float32)
                    history.append(observation)
                    before = time.perf_counter()
                    action = session.run(None, {
                        session.get_inputs()[0].name: np.concatenate(history)[None, :]
                    })[0].reshape(15)
                    latencies.append((time.perf_counter() - before) * 1000)
                    if not np.isfinite(action).all():
                        raise RuntimeError("Non-finite policy output")
                    target[:15] = defaults[:15] + config["action_scale"] * action
            if viewer is not None:
                # Rendering need not run at the 200 Hz physics rate.
                now = time.perf_counter()
                if now >= next_render:
                    viewer.sync()
                    next_render = time.perf_counter() + 1 / 30
            if viewer is not None or args.policy_async:
                time.sleep(max(0, model.opt.timestep - (time.perf_counter() - tick)))
    within_thresholds = bool(
        all(h >= 0.45 for h in heights) and all(t <= 0.8 for t in tilts)
        and all(d <= 0.25 for d in displacements) and np.isfinite(data.qpos).all()
        and np.array_equal(data.warning.number, warnings_before)
    )
    wbc_metrics = whole_body.metrics() if whole_body is not None else {}
    if whole_body is not None:
        within_thresholds = within_thresholds and (
            wbc_metrics["ik_position_error_max_m"] <= 0.02
            and wbc_metrics["wrist_tracking_error_max_m"] <= 0.05
            and wbc_metrics["wrist_orientation_error_max_rad"] <= 0.3
        )
    passed = completed == steps and within_thresholds
    if whole_body is not None and bridge is None:
        passed = passed and wbc_metrics["right_wrist_travel_max_m"] >= 0.04
    if bridge is not None:
        passed=passed and bridge.stop_reason is None and len(bridge.events)==args.policy_frames
    if teacher is not None:
        passed = passed and wbc_metrics["teacher_completed"]
    status = "passed" if passed else (
        "interrupted" if viewer_closed and within_thresholds and (bridge is None or bridge.stop_reason is None) else "failed"
    )
    result = {
        "passed": passed, "status": status,
        "termination_reason": "viewer_closed" if viewer_closed else (
            "duration_completed" if completed == steps else "state_threshold_exceeded"
        ),
        "requested_sim_seconds": args.seconds,
        "scope": "upstream_wbc_pika_closed" if args.pika else (
            "upstream_wbc_and_ik_no_pika" if whole_body else "balance_only_arms_zero_no_pika_no_ik"),
        "upstream_commit": revision, "balance_sha256": lock["balance_sha256"],
        "providers": session.get_providers(), "sim_seconds": float(data.time),
        "wall_seconds": time.perf_counter() - started,
        "physics_hz": 1 / model.opt.timestep,
        "policy_hz": 1 / (model.opt.timestep * config["control_decimation"]),
        "pelvis_height_min_m": min(heights) if heights else None,
        "pelvis_height_final_m": heights[-1] if heights else None,
        "tilt_max_rad": max(tilts) if tilts else None,
        "xy_displacement_max_m": max(displacements) if displacements else None,
        "inference_p95_ms": float(np.percentile(latencies, 95)) if latencies else None,
        "mujoco_warning_count": int(np.sum(data.warning.number - warnings_before)),
        "thresholds": {"min_height_m": 0.45, "max_tilt_rad": 0.8, "max_xy_m": 0.25},
    }
    if whole_body is not None:
        result.update(wbc_metrics)
        result["thresholds"].update({"max_ik_error_m": 0.02, "max_wrist_error_m": 0.05,
                                     "max_wrist_orientation_error_rad": 0.3,
                                     "min_right_wrist_travel_m": 0.04})
    if args.pika:
        result["pika_model"] = pika_report
        result["robot_total_mass_kg"] = float(model.body_mass.sum())
        result["tcp_position_error_max_m"] = wbc_metrics["wrist_tracking_error_max_m"]
        result["tcp_orientation_error_max_rad"] = wbc_metrics["wrist_orientation_error_max_rad"]
        result["right_tcp_travel_max_m"] = wbc_metrics["right_wrist_travel_max_m"]
    if teacher is not None:
        result["scope"] = "teacher_action_replay_wbc_proxy_pika_fixed_gripper"
        result["teacher_sha256"] = hashlib.sha256(args.teacher.read_bytes()).hexdigest()
        result["dataset_contract"] = teacher.payload.get("dataset_contract")
    if bridge is not None:
        result['scope']='live_LeRobot_recorded_observations_to_simulated_WBC_not_camera_closed_loop'
        result['thresholds'].pop('min_right_wrist_travel_m',None)
        result['thresholds']['max_policy_workspace_m']=bridge.max_workspace_m
        result['task_success_validated']=False
        result['hardware_ready']=False
        if bridge.stop_reason:
            result['termination_reason']='policy_rejected_and_target_held'
    if guard is not None:
        result['output_guard']=guard.metrics()
        result['output_guard']['injected_fault']=args.guard_fault
        result['output_guard']['simulation_stopped_on_fault']=guard.phase=='fault'
        result['hardware_ready']=False
        result['motion_commands_sent']=False
        if guard.phase=='fault':
            result['passed']=False; result['status']='failed'; status='failed'
            result['termination_reason']='guard_fault_simulation_halted_before_rejected_output'
    print(json.dumps(result, indent=2))
    output = args.report_dir
    output.mkdir(exist_ok=True)
    output_name = "pika" if args.pika else args.controller
    if teacher is not None:
        output_name = "teacher"
    if bridge is not None:
        output_name='policy-sim' if args.policy_fault=='none' else f'policy-sim-{args.policy_fault}'
        if args.policy_async: output_name+='-async'
        (output/f'{output_name}-events.json').write_text(json.dumps(bridge.events,indent=2)+'\n')
    if guard is not None:
        output_name+='-guard-'+args.guard_fault
        (output/f'{output_name}-frames.json').write_text(json.dumps(sink.frames,indent=2)+'\n')
    (output / f"{output_name}-latest.json").write_text(json.dumps(result, indent=2) + "\n")
    # Closing a preview is a normal user action, but does not pass the full test.
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
