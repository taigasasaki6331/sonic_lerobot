"""Right-camera snapshot over SSH; no SDK, serial port or motion commands."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def remote():
    import cv2
    usb=Path('/sys/bus/usb/devices')
    fish=[p for p in usb.iterdir() if (p/'idVendor').exists()
          and (p/'idVendor').read_text().strip()=='1bcf'
          and (p/'idProduct').read_text().strip()=='2cd1']
    if len(fish)!=1:
        raise RuntimeError('Right fisheye not uniquely identified; require one DECXIN')
    ids=Path('/dev/v4l/by-id')
    cameras={
        'realsense_rgb':list(ids.glob('*405*EXAMPLE_DEVICE_SERIAL-video-index4')),
        'fisheye':list(ids.glob('*DECXIN*01.00.00-video-index0'))}
    result={'scope':'right_camera_snapshot_not_synchronized',
            'robot_commands_sent':False,'serial_opened':False,
            'opencv_version':cv2.__version__,'captures':{}}
    for role,paths in cameras.items():
        if len(paths)!=1: raise RuntimeError('Missing or ambiguous '+role)
        start=time.monotonic()
        cap=cv2.VideoCapture(str(paths[0]),cv2.CAP_V4L2)
        try:
            if not cap.isOpened(): raise RuntimeError('Cannot open '+role)
            fourcc='MJPG' if role=='fisheye' else 'YUYV'
            cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*fourcc))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            cap.set(cv2.CAP_PROP_FPS,30)
            for _ in range(30):
                ok,frame=cap.read()
                if not ok: raise RuntimeError('No frame from '+role)
            if frame.shape!=(480,640,3): raise RuntimeError('Unexpected image shape')
            ok,png=cv2.imencode('.png',frame)
            if not ok: raise RuntimeError('PNG encoding failed')
            result['captures'][role]={'device':str(paths[0]),'resolved':str(paths[0].resolve()),
                'shape':list(frame.shape),'frames_read':30,
                'elapsed_s':time.monotonic()-start,'png_base64':base64.b64encode(png).decode()}
        finally: cap.release()
    print(json.dumps(result),flush=True)


def local():
    root=Path(__file__).resolve().parents[1]
    base=root/'artifacts/g1-camera'; base.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=base))
    command=['ssh','-i','/home/developer/.ssh/g1_pika_g1_ed25519','-o','IdentitiesOnly=yes',
             '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',
             'unitree@192.0.2.7','timeout 30s python3 -I - --remote']
    try:
        run=subprocess.run(command,input=Path(__file__).read_text(),capture_output=True,text=True,timeout=40)
        (out/'stderr.log').write_text(run.stderr)
        if run.returncode: raise RuntimeError('Capture failed: '+run.stderr[-2000:])
        report=json.loads(run.stdout)
        for role,item in report['captures'].items():
            path=out/(role+'.png')
            path.write_bytes(base64.b64decode(item.pop('png_base64'),validate=True))
            item['image']=str(path)
        report['passed']=True
        report['transport']='SSH via current Wi-Fi route; not production latency validation'
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        report={'passed':False,'error':str(exc),'robot_commands_sent':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    print('Report:',out/'report.json')
    return 0 if report['passed'] else 1


if __name__=='__main__':
    if sys.argv[1:]==['--remote']: remote()
    else: raise SystemExit(local())
