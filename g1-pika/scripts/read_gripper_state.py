"""Five-second right-PIKA RX diagnostic. No application writes to serial.

Protocol reference: pinned LeRobot 79edf6a95948d0f0d75df1d54d0a5aad305f75a8,
unitree_g1_pika/pika_gripper.py (460800 baud, concatenated motor JSON).
Opening/closing a TTY can reset hardware; explicit operator consent required.
Does not instantiate the legacy driver (whose disconnect sends disable).
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import select
import stat
import termios
import time


class Frames:
    def __init__(self):
        self.buffer = bytearray()
        self.depth = 0
        self.quoted = False
        self.escaped = False
        self.invalid = 0

    def feed(self, chunk):
        result = []
        for byte in chunk:
            if not self.buffer:
                if byte != 123:
                    continue
                self.depth = 0
                self.quoted = self.escaped = False
            self.buffer.append(byte)
            if self.quoted:
                if self.escaped:
                    self.escaped = False
                elif byte == 92:
                    self.escaped = True
                elif byte == 34:
                    self.quoted = False
            elif byte == 34:
                self.quoted = True
            elif byte == 123:
                self.depth += 1
            elif byte == 125:
                self.depth -= 1
            if self.depth == 0:
                try:
                    value = json.loads(self.buffer)
                    # Reject nonfinite JSON, including Python's permissive NaN.
                    json.dumps(value, allow_nan=False)
                    result.append(value)
                except (ValueError, UnicodeDecodeError):
                    self.invalid += 1
                self.buffer.clear()
            elif len(self.buffer) > 4096:
                self.invalid += 1
                self.buffer.clear()
        return result


def position(frame):
    motor = frame.get('motor')
    value = motor.get('Position') if isinstance(motor, dict) else None
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return value


def plausible_position(value):
    # Diagnostic gate only: legacy nominal 0..1.67 rad with 0.05 rad
    # tolerance for uncalibrated zero. Not a calibrated mechanical limit.
    return value is not None and -.05 <= value <= 1.72


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-connection-reset', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.allow_connection_reset:
        parser.error('Operator must secure empty gripper and permit connection reset')
    # Refuse reuse, wrong side, or an unexpected device before opening any TTY.
    args.output.mkdir(parents=True, exist_ok=False)
    port = Path('/dev/pika/right/gripper')
    expected = Path('/dev/serial/by-path/platform-3610000.usb-usb-0:2.1.4.4.4:1.0-port0')
    report = dict(passed=False, application_serial_bytes_written=0,
                  motion_commands_sent=False, connection_reset_possible=True,
                  width_calibrated=False, port=str(port), duration_s=5,
                  scope='raw_gripper_telemetry_not_control_readiness')
    fd = None
    exclusive = False
    raw = bytearray()
    frames = []
    decoder = Frames()
    try:
        resolved = port.resolve(strict=True)
        if resolved != expected.resolve(strict=True) or not stat.S_ISCHR(resolved.stat().st_mode):
            raise ValueError('Right PIKA path mismatch')
        usb = Path('/sys/bus/usb/devices/1-2.1.4.4.4')
        if (usb / 'idVendor').read_text().strip() != '1a86' or (usb / 'idProduct').read_text().strip() != '7522':
            raise ValueError('USB identity mismatch')
        # O_RDONLY prevents application serial writes; termios/ioctls still
        # configure hardware and cannot promise unchanged DTR/RTS at open.
        fd = os.open(str(resolved), os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        exclusive = True
        config = termios.tcgetattr(fd)
        config[0] = 0  # no software flow-control responses
        config[1] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[3] = 0  # no line discipline echo
        config[4] = config[5] = termios.B460800
        config[6][termios.VMIN] = 0
        config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        # Leave raw mode/HUPCL off on close; do not restore echo or explicitly
        # toggle DTR/RTS. This does not eliminate the opening reset risk.
        start = time.monotonic()
        total = 0
        while time.monotonic() - start < 5:
            if not select.select([fd], [], [], min(.1, max(0, 5 - (time.monotonic() - start))))[0]:
                continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError('Serial EOF/disconnect')
            total += len(chunk)
            if total > 2_000_000:
                raise RuntimeError('Receive byte budget exceeded')
            raw.extend(chunk)
            stamp = time.monotonic()
            for frame in decoder.feed(chunk):
                frames.append(dict(receive_monotonic_s=stamp, data=frame))
        samples = [position(f['data']) for f in frames]
        samples = [p for p in samples if p is not None]
        rejected = [dict(index=i, position_raw=position(f['data']))
                    for i, f in enumerate(frames) if not plausible_position(position(f['data']))]
        report.update(bytes_received=total, json_frames=len(frames),
                      invalid_json_frames=decoder.invalid, position_samples=len(samples),
                      rejected_position_samples=rejected,
                      diagnostic_position_bounds_rad=[-.05, 1.72],
                      position_raw_min=min(samples) if samples else None,
                      position_raw_max=max(samples) if samples else None,
                      last_frames=frames[-3:], elapsed_s=time.monotonic()-start,
                      passed=len(samples) >= 10 and decoder.invalid == 0 and not rejected)
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if fd is not None:
            try:
                if exclusive:
                    fcntl.ioctl(fd, termios.TIOCNXCL)
            finally:
                os.close(fd)
        (args.output / 'raw.bin').write_bytes(raw)
        (args.output / 'frames.json').write_text(json.dumps(frames, allow_nan=False) + '\n')
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
