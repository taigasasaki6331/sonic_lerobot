#!/usr/bin/env python3
"""Read PIKA telemetry, optionally issuing only the official GET_INFO query.

No enable/disable/current/position commands. Opening a tty can reset the MCU.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import select
import stat
import sys
import termios
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_gripper_state import Frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--duration', type=float, default=3.)
    parser.add_argument('--query-version', action='store_true')
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'artifacts/gripper-rx')
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 10:
        parser.error('durationは1〜10秒にしてください')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='inspect-', dir=args.output_dir))
    report = dict(port=args.port, motion_commands_sent=False, query_bytes_written=0,
                  connection_reset_possible=True, scope='telemetry_and_device_info_only',
                  frames=0, invalid_json=0, versions=[], output=str(output))
    decoder = Frames()
    fd = None
    exclusive = False
    raw = bytearray()
    samples = []
    try:
        port = Path(args.port).resolve(strict=True)
        if not stat.S_ISCHR(port.stat().st_mode):
            raise ValueError('シリアルポートではありません')
        # O_RDONLY is used unless a GET_INFO query was explicitly requested.
        mode = os.O_RDWR if args.query_version else os.O_RDONLY
        fd = os.open(port, mode | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        exclusive = True
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B460800
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        start = time.monotonic()
        query_sent = False
        while time.monotonic() - start < args.duration:
            if args.query_version and not query_sent and time.monotonic() - start >= 1.:
                # Official SerialComm.get_device_info_command() exact bytes.
                # No generic serial write or motor command API is exposed.
                payload = b'GET_INFO\r\n'
                written = os.write(fd, payload)
                report['query_bytes_written'] += written
                if written != len(payload):
                    raise IOError('GET_INFOの送信が完了しませんでした')
                query_sent = True
            if not select.select([fd], [], [], .05)[0]:
                continue
            chunk = os.read(fd, 4096)
            raw.extend(chunk)
            for frame in decoder.feed(chunk):
                samples.append(dict(t_s=time.monotonic() - start, frame=frame))
                if isinstance(frame, dict) and 'Version' in frame:
                    report['versions'].append(frame['Version'])
        positions = [s['frame'].get('motor', {}).get('Position') for s in samples
                     if isinstance(s['frame'], dict)]
        positions = [p for p in positions if type(p) in (int, float) and math.isfinite(p)]
        report.update(frames=len(samples), invalid_json=decoder.invalid, raw_bytes=len(raw),
                      duration_s=time.monotonic() - start,
                      position_min_rad=min(positions) if positions else None,
                      position_max_rad=max(positions) if positions else None,
                      latest=samples[-1]['frame'] if samples else None)
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if fd is not None:
            try:
                if exclusive:
                    fcntl.ioctl(fd, termios.TIOCNXCL)
            finally:
                os.close(fd)
        report['port_closed'] = True
        (output / 'raw.bin').write_bytes(raw)
        (output / 'frames.json').write_text(json.dumps(samples, ensure_ascii=False, allow_nan=False) + '\n')
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if 'error' in report or not report['frames'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
