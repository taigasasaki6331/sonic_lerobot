"""Wall-clock-paced simulation with independent bounded image and body workers.

No robot transport. Expired command stops the simulation, not a physical robot.
"""
import hashlib
import json
import queue
import threading
import time
import numpy as np
import mujoco
from split_wbc import setup
from wbc_state import WbcState
from control_guard import ControlGuard, RecordingSink
from zmq_transport import ZmqChannel


class Worker:
    def __init__(self, endpoint, session, hello=False):
        self.requests = queue.Queue(1)
        self.results = queue.Queue(1)
        self.session = session
        self.shutdown_confirmed = False
        self.thread = threading.Thread(target=self.run, args=(endpoint, hello), daemon=True)
        self.thread.start()
    def run(self, endpoint, hello):
        channel = None
        try:
            channel = ZmqChannel(endpoint, timeout_ms=600)
            if hello:
                channel.send({'op': 'hello', 'session': self.session})
                self.results.put(channel.read(), timeout=1)
            while True:
                entry = self.requests.get()
                if entry is None:
                    channel.send({'op': 'stop', 'session': self.session})
                    if channel.read() != {'stopped': True, 'session': self.session}:
                        raise ValueError('Invalid worker shutdown')
                    self.shutdown_confirmed = True
                    break
                packet, sent = entry
                channel.send(packet)
                response = channel.read()
                if response.get('session') != self.session or response.get('seq') != packet['seq']:
                    raise ValueError('Stale worker response')
                self.results.put((response, sent, time.monotonic()), timeout=1)
        except (OSError, ValueError, queue.Full) as exc:
            try: self.results.put_nowait(exc)
            except queue.Full: pass
        finally:
            if channel: channel.close()
            if not self.shutdown_confirmed:
                cleanup = None
                try:
                    cleanup = ZmqChannel(endpoint, timeout_ms=600)
                    cleanup.send({'op': 'stop', 'session': self.session})
                    self.shutdown_confirmed = cleanup.read() == {'stopped': True, 'session': self.session}
                except (OSError, ValueError): pass
                finally:
                    if cleanup: cleanup.close()
    def begin(self, packet):
        if not self.thread.is_alive(): raise RuntimeError('Worker terminated')
        sent = time.monotonic()
        self.requests.put_nowait((packet, sent))
        return sent
    def poll(self):
        try: result = self.results.get_nowait()
        except queue.Empty: return None
        if isinstance(result, BaseException): raise result
        return result
    def close(self):
        try: self.requests.put_nowait(None)
        except queue.Full: pass
        self.thread.join(3)
        if self.thread.is_alive(): raise RuntimeError('Worker failed to stop')


def plant(a):
    _, _, model, data, _, _, names = setup(a.root)
    guard = ControlGuard(names, model.jnt_range[1:30, 0], model.jnt_range[1:30, 1])
    owner = object()
    guard.start_simulation(owner)
    sink = RecordingSink(guard)
    packets = [json.loads((a.observations / f'{i:04d}.json').read_text()) for i in range(a.frames)]
    body = Worker(a.endpoint, a.session)
    images = Worker(a.actor_endpoint, a.session, hello=True)
    timings = []
    image_timings = []
    heights, tilts, xy = [], [], []
    reason = 'duration_completed'
    b_pending = None
    i_pending = None
    b_seq = 1
    i_seq = 0
    b_wait_steps = i_wait_steps = 0
    last_image_send = -float('inf')
    wall_start = None
    max_lag = max_command_age = 0.
    origin = data.qpos[:2].copy()
    pelvis = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'pelvis')
    def snapshot():
        return WbcState(float(data.time), names, data.qpos[7:], data.qvel[6:], data.qpos[:7], data.qvel[:6]).validate(names).packet()
    def approve(response):
        c = response['command']
        if c['seq'] != guard.accepted: raise ValueError('Command sequence mismatch')
        frame = guard.approve(owner=owner, seq=c['seq'], now=float(data.time), state_time=c['time'],
            state_q=data.qpos[7:], names=c['joint_names'], **{key: c[key] for key in ('q', 'dq', 'tau', 'kp', 'kd')})
        sink.append(frame)
        return {key: np.asarray(frame[key]) for key in ('q', 'dq', 'tau', 'kp', 'kd')}, c['time']
    try:
        ready = images.results.get(timeout=3)
        if isinstance(ready, BaseException): raise ready
        policy_root = a.policy_root or a.root
        expected_hash = hashlib.sha256((policy_root / 'artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model/model.safetensors').read_bytes()).hexdigest()
        if (ready.get('device') != 'cuda' or ready.get('session') != a.session
                or ready.get('frames') != a.frames or ready.get('model_sha256') != expected_hash):
            raise ValueError('Image service provenance mismatch')
        body.begin({'session': a.session, 'seq': 0, 'body': snapshot()})
        bootstrap = body.results.get(timeout=2)
        if isinstance(bootstrap, BaseException): raise bootstrap
        command, command_time = approve(bootstrap[0])
        wall_start = time.monotonic()  # Only bootstrap waits before simulation begins.
        command_sent = wall_start
        for step in range(round(a.seconds / .005)):
            now = time.monotonic()
            lag = now - wall_start - float(data.time)
            max_lag = max(max_lag, lag)
            if lag > .05: raise TimeoutError('Physics wall-clock lag exceeded 50ms')
            response = body.poll()
            if response is not None:
                result, sent, received = response
                if now - sent >= .1: raise TimeoutError('WBC response freshness deadline')
                command, command_time = approve(result)
                command_sent = sent
                timings.append({'seq': result['seq'], 'roundtrip_ms': (received - sent) * 1000,
                                'application_age_ms': (now - sent) * 1000, 'wbc_ms': result['wbc_ms'],
                                'actor_roundtrip_ms': 0., 'with_image': False})
                b_pending = None
            response = images.poll()
            if response is not None:
                result, sent, received = response
                if now - sent >= .5: raise TimeoutError('Image response deadline')
                image_timings.append({'seq': result['seq'], 'roundtrip_ms': (received - sent) * 1000})
                i_seq += 1
                i_pending = None
            age = max(float(data.time) - command_time, now - command_sent)
            max_command_age = max(max_command_age, age)
            if age >= .1: raise TimeoutError('WBC command freshness deadline')
            if b_pending is not None and now - b_pending >= .1: raise TimeoutError('WBC response freshness deadline')
            if i_pending is not None and now - i_pending >= .5: raise TimeoutError('Image response deadline')
            if step > 0 and step % 4 == 0 and b_pending is None:
                b_pending = body.begin({'session': a.session, 'seq': b_seq, 'body': snapshot()})
                b_seq += 1
            if (data.time >= 2 + i_seq / 30 and i_pending is None and i_seq < a.frames
                    and now - last_image_send >= 1 / 30):
                packet = dict(packets[i_seq])
                packet.update(session=a.session, body=snapshot())
                i_pending = images.begin(packet)
                last_image_send = now
            b_wait_steps += b_pending is not None
            i_wait_steps += i_pending is not None
            data.ctrl[:] = command['kp'] * (command['q'] - data.qpos[7:]) + command['kd'] * (command['dq'] - data.qvel[6:]) + command['tau']
            mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)
            heights.append(float(data.qpos[2]))
            tilts.append(float(np.arccos(np.clip(data.xmat[pelvis].reshape(3, 3)[2, 2], -1, 1))))
            xy.append(float(np.linalg.norm(data.qpos[:2] - origin)))
            if not np.isfinite(data.qpos).all() or heights[-1] < .45 or tilts[-1] > .8 or xy[-1] > .25:
                raise ValueError('Plant balance bound')
            time.sleep(max(0, wall_start + float(data.time) - time.monotonic()))
    except (OSError, ValueError, KeyError, RuntimeError, queue.Empty, queue.Full) as exc:
        reason = type(exc).__name__ + ': ' + str(exc)
    finally:
        wall_seconds = time.monotonic() - wall_start if wall_start is not None else None
        for worker in [images, body]:
            try: worker.close()
            except RuntimeError as exc: reason = str(exc)
    report = {'passed': reason == 'duration_completed' and i_seq == a.frames, 'termination': reason,
              'hardware_ready': False, 'robot_commands_sent': False, 'wbc_location': 'GPU_PC_CPU_process',
              'timing_scope': 'wall_clock_paced_physics_nonblocking_network_not_hard_realtime',
              'sim_seconds': float(data.time), 'wall_seconds': wall_seconds,
              'accepted_commands': guard.accepted, 'received_images': i_seq,
              'physics_steps_with_body_pending': b_wait_steps, 'physics_steps_with_image_pending': i_wait_steps,
              'worker_shutdown_confirmed': {'body': body.shutdown_confirmed, 'images': images.shutdown_confirmed},
              'max_physics_lag_s': max_lag, 'max_command_age_s': max_command_age,
              'height_min': min(heights, default=0), 'tilt_max': max(tilts, default=0),
              'xy_max': max(xy, default=0), 'mujoco_warnings': int(sum(data.warning.number)),
              'timings': timings, 'image_timings': image_timings}
    a.report.write_text(json.dumps(report, indent=2))
    a.report.with_name('commands.json').write_text(json.dumps(sink.frames))
    print(json.dumps({k: v for k, v in report.items() if k not in ('timings', 'image_timings')}, indent=2))
    return 0 if report['passed'] else 1
