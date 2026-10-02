"""Capture one local preview per PIKA camera. No robot/serial/network access."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def discover():
    found = {'fisheye': [], 'realsense_rgb': []}
    for path in sorted(Path('/sys/class/video4linux').glob('video*')):
        name = (path / 'name').read_text().strip()
        if not ('DECXIN' in name or 'RealSense' in name):
            continue
        device = '/dev/' + path.name
        result = subprocess.run(['v4l2-ctl', '-d', device, '--list-formats'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError(f'Cannot query {device}: {result.stderr}')
        if 'DECXIN' in name and "'MJPG'" in result.stdout:
            found['fisheye'].append(device)
        # Select the color-only interface, not depth/infrared or metadata.
        if 'RealSense' in name and "'YUYV'" in result.stdout and result.stdout.count("[0]") == 1:
            if '[1]' not in result.stdout:
                found['realsense_rgb'].append(device)
    for role, devices in found.items():
        if len(devices) != 1:
            raise RuntimeError(f'Expected one {role} capture node, found {devices}')
    return {role: devices[0] for role, devices in found.items()}


def main():
    base = ROOT / 'artifacts' / 'camera-check'
    base.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='run-', dir=base))
    report = {'scope': 'camera_capture_only_not_policy_input_validation',
              'passed': False, 'robot_commands_sent': False,
              'serial_opened': False, 'captures': {},
              'limitations': ['Sequential captures, not synchronized',
                              'No depth stream or camera calibration validation',
                              'No learned-policy input preprocessing validation']}
    try:
        for role, device in discover().items():
            image = output / (role + '.png')
            fmt = 'mjpeg' if role == 'fisheye' else 'yuyv422'
            args = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-f', 'v4l2', '-input_format', fmt, '-video_size', '640x480',
                    '-framerate', '30', '-i', device, '-vf', r'select=eq(n\,29)',
                    '-frames:v', '1', '-threads', '1', str(image)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=20)
            if result.returncode or not image.exists() or image.stat().st_size == 0:
                raise RuntimeError(f'{role} capture failed: {result.stderr}')
            report['captures'][role] = {'device': device, 'image': str(image),
                                       'selected_frame_zero_based': 29,
                                       'requested_size': [640, 480], 'requested_fps': 30,
                                       'stderr': result.stderr}
        report['passed'] = True
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report['error'] = str(exc)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print(f'Report: {output / "report.json"}')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
