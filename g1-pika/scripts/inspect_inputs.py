"""Read-only local device inventory; no robot SDK, discovery or streaming."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def command(args):
    if not shutil.which(args[0]):
        return {'available': False}
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return {'available': True, 'returncode': result.returncode,
                'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'available': True, 'error': str(exc)}


def inspect():
    video = [{'device': '/dev/' + p.name, 'name': read(p / 'name')}
             for p in sorted(Path('/sys/class/video4linux').glob('video*'))]
    usb = [{'vendor_id': read(p / 'idVendor'), 'product_id': read(p / 'idProduct'),
            'product': read(p / 'product')}
           for p in sorted(Path('/sys/bus/usb/devices').glob('*'))
           if (p / 'idVendor').exists()]
    net = [{'name': p.name, 'operstate': read(p / 'operstate'),
            'carrier': read(p / 'carrier')}
           for p in sorted(Path('/sys/class/net').iterdir())
           if (p / 'device').exists()]
    return {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'local_read_only_inventory_not_robot_or_camera_readiness',
            'robot_commands_sent': False, 'camera_stream_started': False,
            'video_devices': video, 'usb_devices': usb, 'physical_network': net,
            'addresses': command(['ip', '-brief', 'address']),
            'v4l2_devices': command(['v4l2-ctl', '--list-devices']),
            'limitations': ['No camera frames or calibration checked',
                            'No G1 state subscription or network discovery',
                            'Missing devices or permission failures do not imply readiness']}


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2, ensure_ascii=False))
