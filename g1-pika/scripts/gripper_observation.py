"""Receive-only lifecycle around the unchanged pinned LeRobot PikaGripper.

Width geometry translated from pika_ros 0f7f6b75a349ceccb252628f5f48a28aaf5c7b6b,
serial_gripper_imu.cpp getDistance/receiving. See LICENSE.pika_geometry.
"""
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import time


def legacy_width(raw_angle):
    if type(raw_angle) not in (int, float) or not math.isfinite(raw_angle):
        raise ValueError('Invalid encoder angle')
    angle = max(0., min(1.67, raw_angle))
    def f32(x): return struct.unpack('f', struct.pack('f', x))[0]
    def distance(a):
        a = (180. - 43.99) / 180. * math.pi - a
        h = .0325 * math.sin(a)
        return f32(math.sqrt(f32(.058**2 - (h - .01456)**2))) + .0325 * math.cos(a)
    return dict(width_m=2*(distance(angle)-distance(0.)), raw_angle_rad=raw_angle,
                angle_rad=angle, legacy_range_error=angle != raw_angle,
                width_source='encoder_with_legacy_linkage_geometry', calibrated=False)


def open_observer(folder):
    folder = Path(folder)
    source = folder / 'pika_gripper.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != 'ef7c397ec33ada894fb164bea633b560e178b7fa1778e5bf89eeb1001be8e63e':
        raise ValueError('Existing driver hash mismatch')
    wheel = folder / 'pyserial-3.5-py2.py3-none-any.whl'
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != 'c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0':
        raise ValueError('pyserial hash mismatch')
    sys.path.insert(0, str(wheel))
    spec = importlib.util.spec_from_file_location('existing_pika_gripper', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class Observer(module.PikaGripper):
        latest = None
        count = 0

        def _send(self, *args, **kwargs):
            raise RuntimeError('Commands forbidden in observation-only lifecycle')

        def _parse_frame(self, frame):
            super()._parse_frame(frame)
            try:
                data = json.loads(frame)
                width = legacy_width(data['motor']['Position'])
                data['motorstatus']['Status']
                stamp = time.monotonic()
                state = asdict(self.get_state())
                json.dumps(state, allow_nan=False)
            except (ValueError, KeyError, TypeError):
                return
            self.count += 1
            self.latest = dict(**width, state=state, receive_monotonic_s=stamp, seq=self.count)

        def snapshot(self):
            value = self.latest
            if value is None or not 0 <= time.monotonic()-value['receive_monotonic_s'] <= .25:
                raise RuntimeError('Gripper state absent or stale')
            return dict(value, read_age_s=time.monotonic()-value['receive_monotonic_s'])

        def disconnect(self):
            # Intentional minimal difference: do not send legacy disable.
            self._shutdown_event.set()
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=1)
            if self._serial is not None:
                self._serial.close()
                self._serial = None

    port = Path('/dev/pika/right/gripper')
    paired = Path('/dev/serial/by-path/platform-3610000.usb-usb-0:2.1.4.4.4:1.0-port0')
    if port.resolve(strict=True) != paired.resolve(strict=True):
        raise ValueError('Right gripper path mismatch')
    observer = Observer(str(port))
    try:
        observer.connect()
        observer._serial.exclusive = True
        observer.wait_for_state(timeout=3)
        observer.snapshot()
        return observer
    except BaseException:
        observer.disconnect()
        raise
