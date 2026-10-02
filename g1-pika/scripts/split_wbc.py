"""GPU-PC WBC service / local MuJoCo plant. SIMULATION ONLY, no robot SDK.

Lockstep simulation: network waits pause simulated time, not a real-time controller.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mujoco
import numpy as np
import yaml
from control_guard import ControlGuard, RecordingSink
from wbc_state import WbcState
from zmq_transport import ZmqChannel


def setup(root):
    from pika_model import build_pika_model
    upstream = root / 'vendor/GR00T-WholeBodyControl'
    lock = json.loads((root / 'sources.lock.json').read_text())['wbc']
    import subprocess
    if subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip() != lock['commit']:
        raise ValueError('WBC commit mismatch')
    subprocess.run(['git', '-C', str(upstream), 'diff', '--exit-code', 'HEAD'], check=True)
    import importlib.metadata
    for line in (root / 'requirements-wbc.lock').read_text().splitlines():
        if '==' in line and not line.startswith(('#', '--')):
            name, version = line.split('==')
            if importlib.metadata.version(name) != version: raise ValueError('WBC dependency mismatch: ' + name)
    resources = upstream / 'decoupled_wbc/sim2mujoco/resources/robots/g1'
    for key, file in [('balance_sha256', 'Balance'), ('walk_sha256', 'Walk')]:
        if hashlib.sha256((resources / ('policy/GR00T-WholeBodyControl-' + file + '.onnx')).read_bytes()).hexdigest() != lock[key]:
            raise ValueError('WBC model checksum mismatch')
    config = yaml.safe_load((resources / 'g1_gear_wbc.yaml').read_text())
    path, urdf, _ = build_pika_model(upstream, root)
    model = mujoco.MjModel.from_xml_path(str(path))
    model.opt.timestep = .005
    if (model.nq, model.nv, model.nu) != (36, 35, 29): raise ValueError('Unexpected plant dimensions')
    if not np.array_equal(model.actuator_trnid[:, 0], np.arange(1, 30)): raise ValueError('Actuator order')
    data = mujoco.MjData(model)
    defaults = np.zeros(29, dtype=np.float32)
    defaults[:15] = config['default_angles']
    defaults[16], defaults[23] = .2, -.2
    data.qpos[7:] = defaults
    mujoco.mj_forward(model, data)
    names = tuple(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(1, 30))
    return upstream, lock, model, data, defaults, urdf, names


class DeliveredBridge:
    """Apply each delivered h1 action once; retain existing TCP limit/codec checks."""
    def __init__(self, metadata, frames):
        from policy_replay_bridge import ReplayBridge
        self.metadata = metadata
        self.response = None
        self.bridge = ReplayBridge(self, frames)
    def query(self, seq): return self.response
    def target(self, now, origin, measured):
        if self.response is not None:
            seq = self.response['seq']
            result = self.bridge.target(2 + seq / 30, origin, measured)
            self.response = None
            if self.bridge.stop_reason: raise ValueError(self.bridge.stop_reason)
            self.bridge.events[-1]['sim_time'] = now
            return result
        if self.bridge.last_target is None: return origin.copy()
        return self.bridge.last_target.copy()
    def metrics(self):
        result = self.bridge.metrics()
        result['policy_bridge']['lerobot_hz_sim_time'] = 25
        result['policy_bridge']['playback_timing'] = 'one action each two 50Hz simulated WBC ticks'
        return result


def server(a):
    from wbc_controller import WholeBodyController
    upstream, lock, model, data, defaults, urdf, names = setup(a.root)
    with redirect_stdout(sys.stderr):
        wbc = WholeBodyController(upstream, lock, model, data, defaults, pika_urdf=urdf)
    actor = None
    subscriber = None
    if a.async_control:
        subscriber = ZmqChannel(a.policy_results, kind='sub', timeout_ms=0)
        metadata = {'session': a.session, 'frames': a.frames, 'device': 'cuda',
                    'observation_source': 'recorded_images_separate_ZMQ_stream',
                    'model_sha256': hashlib.sha256((a.policy_root / 'artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model/model.safetensors').read_bytes()).hexdigest()}
    else:
        actor = ZmqChannel(a.actor_endpoint, timeout_ms=1500)
        actor.send({'op': 'hello', 'session': a.session})
        metadata = actor.read()
    checkpoint = a.policy_root / 'artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model/model.safetensors'
    if (metadata.get('session') != a.session or metadata.get('frames') != a.frames
            or metadata.get('device') != 'cuda'
            or metadata.get('model_sha256') != hashlib.sha256(checkpoint.read_bytes()).hexdigest()):
        raise ValueError('Actor handshake mismatch')
    bridge = DeliveredBridge(metadata, a.frames)
    wbc.policy_bridge = bridge
    guard = ControlGuard(names, model.jnt_range[1:30, 0], model.jnt_range[1:30, 1])
    owner = object()
    guard.start_simulation(owner)
    sink = RecordingSink(guard)
    channel = ZmqChannel(a.endpoint, server=True, accept_filter=a.accept_ip + '/32',
                         timeout_ms=15000, max_message_bytes=2000000)
    print(json.dumps({'ready': True, 'session': a.session, 'wbc_commit': lock['commit']}), flush=True)
    records = []
    due = 2.
    expected = 0
    reason = 'not_finished'
    try:
        while True:
            request = channel.read()
            if request.get('session') != a.session: raise ValueError('Wrong WBC session')
            if request.get('op') == 'stop':
                channel.send({'stopped': True, 'session': a.session})
                reason = 'client_stop'
                break
            seq = request['seq']
            if type(seq) is not int or seq != expected or seq >= 6000: raise ValueError('WBC sequence')
            if seq == 200 and a.fault == 'disconnect':
                reason = 'injected_disconnect'
                break
            if seq == 200 and a.fault == 'delay': time.sleep(.8)
            state = dict(request['body'])
            if state.pop('source') != 'simulation_not_G1': raise ValueError('Simulation input only')
            state = WbcState(**state).validate(names)
            if not a.async_control and abs(state.time - seq * .02) > 1e-6: raise ValueError('State step/time mismatch')
            data.qpos[:] = np.r_[state.base_pose, state.q]
            data.qvel[:] = np.r_[state.base_velocity, state.dq]
            data.time = state.time
            mujoco.mj_forward(model, data)  # FK only; no remote physics stepping
            wants_image = not a.async_control and state.time >= due - 1e-7 and len(bridge.bridge.events) < a.frames
            inference_ms = 0.
            if subscriber:
                try: result = subscriber.read()
                except OSError as exc:
                    if exc.errno != 11: raise
                    result = None
                if result is not None:
                    age = time.monotonic() - result.get('issued_monotonic_s', float('nan'))
                    if (result.get('session') != a.session or result.get('seq') != len(bridge.bridge.events)
                            or result.get('model_sha256') != metadata['model_sha256']
                            or not np.isfinite(age) or not 0 <= age < .5):
                        raise ValueError('Stale/missing published action')
                    bridge.response = result
            if wants_image:
                packet = request['observation']
                packet.update(body=request['body'], session=a.session)
                if packet['seq'] != len(bridge.bridge.events): raise ValueError('Image sequence')
                before = time.perf_counter()
                actor.send(packet)
                response = actor.read()
                inference_ms = (time.perf_counter() - before) * 1000
                if response.get('seq') != packet['seq'] or response.get('session') != a.session:
                    raise ValueError('Actor response identity')
                bridge.response = response
                due = state.time + 1 / 30
            elif 'observation' in request:
                raise ValueError('Unexpected image packet')
            before = time.perf_counter()
            q = wbc.step(data)
            frame = guard.approve(owner=owner, seq=seq, now=state.time, state_time=state.time,
                state_q=state.q, names=names, q=q, dq=np.zeros(29), tau=wbc.feedforward(data), kp=wbc.kp, kd=wbc.kd)
            sink.append(frame)
            compute_ms = (time.perf_counter() - before) * 1000
            next_frame = len(bridge.bridge.events) if not a.async_control and state.time + .02 >= due - 1e-7 and len(bridge.bridge.events) < a.frames else None
            response = {'session': a.session, 'seq': seq, 'command': frame, 'next_frame': next_frame,
                        'wbc_ms': compute_ms, 'actor_roundtrip_ms': inference_ms}
            if seq == 200 and a.fault == 'stale': response['session'] = 'old-session'
            channel.send(response)
            records.append({'seq': seq, 'with_image': wants_image, 'wbc_ms': compute_ms,
                            'actor_roundtrip_ms': inference_ms})
            expected += 1
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        reason = type(exc).__name__ + ': ' + str(exc)
    finally:
        channel.close()
        if actor:
            try:
                actor.send({'op': 'stop', 'session': a.session})
                actor.read()
            except (OSError, ValueError): pass
            actor.close()
        if subscriber: subscriber.close()
        a.report.write_text(json.dumps({'termination': reason, 'records': records,
            'guard': guard.metrics(), 'metrics': wbc.metrics(), 'hardware_ready': False,
            'robot_commands_sent': False}, indent=2))
        if a.async_control:
            report = json.loads(a.report.read_text())
            report['metrics']['policy_bridge'].update(lerobot_hz_sim_time=None,
                playback_timing='GPU action publications applied on latest received body state',
                synchronous_simulation_only=False)
            a.report.write_text(json.dumps(report, indent=2))


def plant(a):
    _, lock, model, data, _, _, names = setup(a.root)
    channel = ZmqChannel(a.endpoint, timeout_ms=600)
    guard = ControlGuard(names, model.jnt_range[1:30, 0], model.jnt_range[1:30, 1])
    owner = object()
    guard.start_simulation(owner)
    sink = RecordingSink(guard)
    next_frame = None
    timings = []
    heights = []
    tilts = []
    xy = []
    reason = 'duration_completed'
    origin = data.qpos[:2].copy()
    pelvis = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'pelvis')
    packets = [json.loads((a.observations / f'{i:04d}.json').read_text()) for i in range(a.frames)]
    try:
        for seq in range(round(a.seconds * 50)):
            state = WbcState(float(data.time), names, data.qpos[7:], data.qvel[6:], data.qpos[:7], data.qvel[:6]).validate(names)
            packet = {'session': a.session, 'seq': seq, 'body': state.packet()}
            if next_frame is not None: packet['observation'] = packets[next_frame]
            before = time.perf_counter()
            channel.send(packet)
            response = channel.read()
            elapsed = (time.perf_counter() - before) * 1000
            if elapsed >= 500: raise TimeoutError('WBC response deadline exceeded')
            if response.get('session') != a.session or response.get('seq') != seq:
                raise ValueError('Stale WBC response')
            c = response['command']
            if c['seq'] != seq or abs(c['time'] - state.time) > 1e-6: raise ValueError('Command time mismatch')
            frame = guard.approve(owner=owner, seq=seq, now=state.time, state_time=state.time,
                state_q=state.q, names=c['joint_names'], **{key: c[key] for key in ('q', 'dq', 'tau', 'kp', 'kd')})
            sink.append(frame)
            next_frame = response['next_frame']
            if next_frame is not None and (type(next_frame) is not int or not 0 <= next_frame < a.frames):
                raise ValueError('Invalid next frame')
            timings.append({'seq': seq, 'roundtrip_ms': elapsed, 'with_image': 'observation' in packet,
                            'wbc_ms': response['wbc_ms'], 'actor_roundtrip_ms': response['actor_roundtrip_ms']})
            c = frame  # Apply normalized, copied guard output, not the raw network object.
            for _ in range(4):
                data.ctrl[:] = np.asarray(c['kp']) * (np.asarray(c['q']) - data.qpos[7:]) + np.asarray(c['kd']) * (np.asarray(c['dq']) - data.qvel[6:]) + np.asarray(c['tau'])
                mujoco.mj_step(model, data)
                mujoco.mj_forward(model, data)
                heights.append(float(data.qpos[2]))
                tilts.append(float(np.arccos(np.clip(data.xmat[pelvis].reshape(3, 3)[2, 2], -1, 1))))
                xy.append(float(np.linalg.norm(data.qpos[:2] - origin)))
                if not np.isfinite(data.qpos).all() or heights[-1] < .45 or tilts[-1] > .8 or xy[-1] > .25:
                    raise ValueError('Plant balance bound')
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        reason = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            channel.send({'op': 'stop', 'session': a.session})
            channel.read()
        except (OSError, ValueError): pass
        channel.close()
    report = {'passed': reason == 'duration_completed', 'termination': reason,
              'hardware_ready': False, 'robot_commands_sent': False, 'wbc_location': 'GPU_PC_CPU_process',
              'timing_scope': 'lockstep_simulation_network_wait_pauses_sim_time_not_realtime',
              'sim_seconds': float(data.time), 'accepted_commands': guard.accepted,
              'height_min': min(heights, default=0), 'tilt_max': max(tilts, default=0),
              'xy_max': max(xy, default=0), 'mujoco_warnings': int(sum(data.warning.number)),
              'timings': timings}
    a.report.write_text(json.dumps(report, indent=2))
    a.report.with_name('commands.json').write_text(json.dumps(sink.frames))
    print(json.dumps({k: v for k, v in report.items() if k != 'timings'}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['server', 'plant'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--session', required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--actor-endpoint')
    p.add_argument('--policy-root', type=Path)
    p.add_argument('--accept-ip')
    p.add_argument('--observations', type=Path)
    p.add_argument('--frames', type=int, default=206)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--fault', choices=['none', 'disconnect', 'stale', 'delay'], default='none')
    p.add_argument('--async-control', action='store_true')
    p.add_argument('--policy-results')
    a = p.parse_args()
    if not 1 <= a.frames <= 206 or not 12 <= a.seconds <= 120: p.error('Invalid bounded run')
    if a.async_control and a.mode == 'plant':
        from async_split import plant as async_plant
        raise SystemExit(async_plant(a))
    raise SystemExit(server(a) if a.mode == 'server' else plant(a))
