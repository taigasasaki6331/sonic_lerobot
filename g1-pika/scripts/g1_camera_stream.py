"""Bounded request/reply camera stream; persistent readers, no serial/SDK."""
import base64
import argparse
import json
from pathlib import Path
import sys
import subprocess
import threading
import time
import cv2
from collections import deque


def fresh_pair(latest,previous,now):
    return all(role in latest and latest[role][2]>previous.get(role,0)
               and 0<=now-latest[role][1]<=.025 for role in ('fisheye','realsense_rgb'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-reader')
    parser.add_argument('--state-history',action='store_true')
    parser.add_argument('--max-frames',type=int,default=30,choices=range(1,904))
    parser.add_argument('--zmq',action='store_true')
    parser.add_argument('--fisheye-device',type=Path)
    parser.add_argument('--realsense-device',type=Path)
    parser.add_argument('--gripper-state',action='store_true',help='Receive only; serial open may reset MCU')
    args=parser.parse_args()
    if args.state_history and not args.state_reader: parser.error('State history requires state reader')
    if args.state_history:
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from state_history import validate_history
    channel=None
    if args.zmq:
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from zmq_transport import ZmqChannel
        channel=ZmqChannel('tcp://192.0.2.11:6158',server=True,
                           timeout_ms=15000,accept_filter='192.0.2.12/32')
    fish=[p for p in Path('/sys/bus/usb/devices').iterdir() if (p/'idVendor').exists()
          and (p/'idVendor').read_text().strip()=='1bcf'
          and (p/'idProduct').read_text().strip()=='2cd1']
    if args.fisheye_device:
        if not args.realsense_device: raise ValueError('Explicit fish path requires paired D405 path')
        node=args.fisheye_device.resolve(strict=True).name
        hardware=(Path('/sys/class/video4linux')/node/'device').resolve(strict=True)
        if not any(p.resolve() in hardware.parents for p in fish):
            raise ValueError('Selected fisheye is not a DECXIN USB device')
    elif len(fish)!=1: raise RuntimeError('Require exactly one DECXIN; no guessing sides')
    ids=Path('/dev/v4l/by-id')
    patterns={'realsense_rgb':'*405*EXAMPLE_DEVICE_SERIAL-video-index4',
              'fisheye':'*DECXIN*01.00.00-video-index0'}
    if args.realsense_device:
        serial_paths=list(ids.glob(patterns['realsense_rgb']))
        if len(serial_paths)!=1 or serial_paths[0].resolve(strict=True)!=args.realsense_device.resolve(strict=True):
            raise ValueError('D405 port does not match verified right-camera serial')
    latest={}; errors={}; lock=threading.Condition(); stopped=threading.Event(); threads=[]
    body={}; state_process=None; gripper=None
    history=deque(maxlen=10)
    def state_reader():
        try:
            for line in state_process.stdout:
                state=json.loads(line)
                if len(state['q'])!=35 or len(state['dq'])!=35: raise ValueError('Invalid body state')
                with lock:
                    body['latest']=state
                    history.append(state)
            if not stopped.is_set():
                with lock: errors['body']='State reader exited'
        except Exception as exc:
            with lock: errors['body']=str(exc)
    def reader(role,path):
        cap=cv2.VideoCapture(str(path),cv2.CAP_V4L2)
        try:
            if not cap.isOpened(): raise RuntimeError('Camera open failed')
            cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*('MJPG' if role=='fisheye' else 'YUYV')))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            # On the verified DECXIN camera one V4L2 buffer halves actual
            # delivery to 15Hz despite a 30fps format. A dedicated reader drains
            # four buffers continuously and exposes only its latest frame.
            cap.set(cv2.CAP_PROP_FPS,30)
            if not cap.set(cv2.CAP_PROP_BUFFERSIZE,4):
                raise RuntimeError('Camera receive buffer configuration rejected')
            count=0
            while not stopped.is_set():
                ok,frame=cap.read(); stamp=time.monotonic()
                if not ok or frame.shape!=(480,640,3): raise RuntimeError('Camera read failed')
                # Encode on the dedicated per-camera reader, concurrently with
                # the other camera and GPU inference. Keep the original receive
                # timestamp; encoding must not make old pixels appear newer.
                ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,90])
                if not ok: raise RuntimeError('Encode failed')
                encoded=base64.b64encode(jpeg).decode()
                count+=1
                with lock:
                    latest[role]=(encoded,stamp,count)
                    lock.notify_all()
        except Exception as exc:
            with lock:
                errors[role]=str(exc)
                lock.notify_all()
        finally: cap.release()
    for role,pattern in patterns.items():
        selected=args.fisheye_device if role=='fisheye' else args.realsense_device
        paths=[selected] if selected else list(ids.glob(pattern))
        if len(paths)!=1: raise RuntimeError('Missing camera '+role)
        thread=threading.Thread(target=reader,args=(role,paths[0]),daemon=True)
        threads.append(thread); thread.start()
    try:
        if args.gripper_state:
            sys.path.insert(0,str(Path(__file__).resolve().parent))
            from gripper_observation import open_observer
            gripper=open_observer(Path(__file__).resolve().parent)
        if args.state_reader:
            state_process=subprocess.Popen([args.state_reader,'--stream'],stdout=subprocess.PIPE,text=True)
            thread=threading.Thread(target=state_reader,daemon=True)
            threads.append(thread); thread.start()
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            with lock:
                if errors: raise RuntimeError(str(errors))
                ready=len(latest)==2 and all(v[2]>=15 for v in latest.values()) and (not args.state_reader or 'latest' in body)
                if args.state_history: ready=ready and len(history)==10
            if ready: break
            time.sleep(.02)
        if not ready: raise RuntimeError('Camera startup timeout')
        print(json.dumps({'ready':True,'scope':'right_live_images_no_robot_commands',
                          'opencv_version':cv2.__version__,
                          'transport':'ZMQ' if channel else 'SSH',
                          'libzmq':channel.version() if channel else None}),flush=True)
        expected=0; sent_counts={}
        def requests():
            if channel:
                while True: yield channel.read()
            else:
                for line in sys.stdin: yield json.loads(line)
        for request in requests():
            request_received=time.monotonic()
            if request.get('stop'):
                if channel: channel.send({'stopped':True})
                break
            if type(request.get('seq')) is not int or request['seq']!=expected or expected>=args.max_frames:
                raise ValueError('Invalid camera request sequence')
            with lock:
                deadline=time.monotonic()+.1
                # Do not phase-lock requests to the end of the previous frame's
                # lifetime. Wait for a genuinely fresh encoded pair, preserving
                # receive timestamps and the independent 100ms end-to-end gate.
                while not fresh_pair(latest,sent_counts,time.monotonic()):
                    if errors: raise RuntimeError(str(errors))
                    remaining=deadline-time.monotonic()
                    if remaining<=0: raise TimeoutError('No new paired camera frames within 100ms')
                    lock.wait(remaining)
                if errors: raise RuntimeError(str(errors))
                snapshot=dict(latest)
                sent_counts={role:value[2] for role,value in snapshot.items()}
                state=body.get('latest')
                history_snapshot=list(history)
            packet={'seq':expected,'images':{},'robot_commands_sent':False}
            if gripper is not None:
                packet['gripper']=gripper.snapshot()
            if args.state_reader:
                if state is None or not 0<=time.monotonic()-state['receive_monotonic_s']<=.1:
                    raise RuntimeError('Missing or stale G1 state')
                packet['g1_state']=state
                if args.state_history: packet['g1_state_history']=validate_history(history_snapshot)
            stamps=[]
            for role,(encoded,stamp,count) in snapshot.items():
                age=time.monotonic()-stamp
                if age>.5: raise RuntimeError('Stale camera frame')
                packet['images'][role]={'jpeg':encoded,
                    'frame_counter':count,'read_age_s':age,'read_monotonic_s':stamp}
                stamps.append(stamp)
            packet['read_time_skew_s']=abs(stamps[0]-stamps[1])
            if gripper is not None:
                packet['image_gripper_receive_skew_s']=max(abs(s-packet['gripper']['receive_monotonic_s']) for s in stamps)
                if packet['image_gripper_receive_skew_s']>.25:
                    raise RuntimeError('Gripper/image receive-time mismatch')
            if args.state_reader:
                skew=max(abs(stamp-state['receive_monotonic_s']) for stamp in stamps)
                if skew>.1: raise RuntimeError('Image/state receive-time mismatch')
                packet['image_state_receive_skew_s']=skew
            # Same-host receive ages, measured after encoding. GPU adds local RTT;
            # it must not subtract its clock from these G1 monotonic timestamps.
            relevant_stamps=list(stamps)
            if args.state_reader: relevant_stamps.append(state['receive_monotonic_s'])
            if gripper is not None: relevant_stamps.append(packet['gripper']['receive_monotonic_s'])
            completed=time.monotonic()
            packet['schema_version']=2
            packet['capture_age_s']=completed-min(relevant_stamps)
            packet['request_processing_s']=completed-request_received
            if channel: channel.send(packet)
            else: print(json.dumps(packet),flush=True)
            expected+=1
    finally:
        stopped.set()
        if gripper is not None: gripper.disconnect()
        if state_process is not None:
            if state_process.poll() is None:
                state_process.terminate()
                try: state_process.wait(timeout=2)
                except subprocess.TimeoutExpired: state_process.kill(); state_process.wait()
            state_process.stdout.close()
        for thread in threads: thread.join(timeout=1)
        if channel: channel.close()


if __name__=='__main__': main()
