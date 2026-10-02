"""Bounded right-only open/return test using the unchanged pinned PikaGripper.

Requires explicit operator permission. Does not import Unitree SDK or robot class.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

DRIVER_SHA = 'ef7c397ec33ada894fb164bea633b560e178b7fa1778e5bf89eeb1001be8e63e'
PORT = '/dev/pika/right/gripper'
EXPECTED = '/dev/serial/by-path/platform-3610000.usb-usb-0:2.1.4.4.4:1.0-port0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-right-gripper-motion', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--opening-angle', type=float, choices=[.15, .6], default=.15)
    args = parser.parse_args()
    if not args.allow_right_gripper_motion:
        parser.error('Explicit right-only motion permission required')
    root = Path(__file__).resolve().parent
    source = root / 'pika_gripper.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != DRIVER_SHA:
        raise ValueError('Pinned existing driver checksum mismatch')
    if Path(PORT).resolve(strict=True) != Path(EXPECTED).resolve(strict=True):
        raise ValueError('Right device mismatch')
    wheel = root / 'pyserial-3.5-py2.py3-none-any.whl'
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != 'c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0':
        raise ValueError('pyserial wheel checksum mismatch')
    sys.path.insert(0, str(wheel))
    import serial
    if serial.__version__ != '3.5':
        raise ValueError('pyserial 3.5 required')
    spec = importlib.util.spec_from_file_location('existing_pika_gripper', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, scope='right_gripper_only_open_return',
                  body_commands_sent=False, left_gripper_opened=False,
                  driver_sha256=DRIVER_SHA, pyserial_version=serial.__version__,
                  targets_rad=([.15, 0.0] if args.opening_angle == .15 else [.2, .4, .6, .4, .2, 0.0]),
                  peak_hold_s=(.2 if args.opening_angle == .15 else 3.0),
                  commands=[], samples=[], disable_confirmed=False)

    class Observed(module.PikaGripper):
        last_stamp = 0.0
        fault = None

        def _parse_frame(self, frame):
            # Reuse actual parser. Hook only measures freshness for this test.
            super()._parse_frame(frame)
            try:
                data = json.loads(frame)
                p = data['motor']['Position']
                data['motorstatus']['Status']
                if type(p) not in (float, int) or not math.isfinite(p) or not -.05 <= p <= args.opening_angle + .1:
                    self.fault = 'Position outside this small test envelope'
                    return
            except (ValueError, KeyError, TypeError):
                return
            self.last_stamp = time.monotonic()
            if len(report['samples']) < 5000:
                report['samples'].append(dict(t=self.last_stamp, **asdict(self.get_state())))

        def _send(self, cmd, *values, flush=True):
            if cmd not in (10, 11, 22):
                raise ValueError('Command outside approved test')
            if cmd == 22:
                if len(values) != 1 or not 0 <= values[0] <= args.opening_angle:
                    raise ValueError('Target outside approved small movement')
                if self.fault or time.monotonic() - self.last_stamp > .25:
                    raise RuntimeError(self.fault or 'Telemetry stale')
            report['commands'].append(dict(t=time.monotonic(), code=cmd, values=values))
            super()._send(cmd, *values, flush=flush)

    grip = Observed(PORT)
    def fresh():
        if grip.fault or time.monotonic() - grip.last_stamp > .25:
            raise RuntimeError(grip.fault or 'Telemetry stale')
        return grip.get_state()
    try:
        grip.connect()
        grip._serial.write_timeout = .5
        grip._serial.exclusive = True
        grip.wait_for_state(timeout=3)
        initial = fresh()
        report['initial'] = asdict(initial)
        if initial.enabled or not -.03 <= initial.position <= .05:
            raise RuntimeError('Expected initially disabled, nearly closed gripper')
        grip.enable(retries=10, retry_period=.2)
        if not fresh().enabled:
            raise RuntimeError('Enable not confirmed')
        report['moves'] = []
        for target in report['targets_rad']:
            state = grip.set_angle_and_wait(target, tolerance=.025, timeout=2, resend_period=.1)
            state = fresh()
            record = dict(target=target, **asdict(state))
            report['moves'].append(record)
            if not state.enabled or abs(state.position - target) > .025:
                raise RuntimeError('Target tracking not confirmed')
            time.sleep(report['peak_hold_s'] if target == args.opening_angle else .2)
        report['motion_completed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if grip.is_connected:
            try:
                grip.disable(retries=10, retry_period=.2, settle_timeout=.5)
                final = fresh()
                report['final'] = asdict(final)
                report['disable_confirmed'] = not final.enabled
            except Exception as exc:
                report['disable_error'] = str(exc)
            finally:
                # Use upstream cleanup too, including its best-effort disable.
                grip.disconnect()
        report['port_closed'] = not grip.is_connected
        report['passed'] = bool(report.get('motion_completed') and report['disable_confirmed']
                                and report['port_closed'] and not report.get('error'))
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'samples'}, indent=2))
    print('Recorded telemetry samples:', len(report['samples']))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
