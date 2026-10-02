"""Explicitly authorized, temporary right-fisheye exposure/FPS diagnostic.

No DDS, serial, robot SDK or motion commands. Run on G1; restores original
exposure controls and frame interval in finally, including SIGTERM/SIGINT.
"""
import argparse
import array
import fcntl
import json
import os
from pathlib import Path
import signal
import statistics
import time

DEVICE='/dev/v4l/by-path/platform-3610000.usb-usb-0:2.1.4.4.1:1.0-video-index0'
AUTO=0x009a0901
EXPOSURE=0x009a0902


def control(fd, key, value=None):
    data=array.array('i',[key,0 if value is None else value])
    fcntl.ioctl(fd,0xc008561b if value is None else 0xc008561c,data,True)
    return data[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-temporary-camera-settings',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.allow_temporary_camera_settings: parser.error('Camera setting permission required')
    args.output.mkdir(exist_ok=False)
    import cv2
    fd=os.open(DEVICE,os.O_RDWR|os.O_NONBLOCK); cap=None
    report=dict(scope='temporary_right_fisheye_exposure_only',robot_commands_sent=False,trials=[])
    def interrupted(signum,frame): raise RuntimeError('Interrupted: '+str(signum))
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    original=dict(auto_exposure=control(fd,AUTO),exposure_absolute=control(fd,EXPOSURE))
    # G_PARM / G_FMT structs are fixed-size Linux V4L2 ABI. Save before open.
    parm=bytearray(204); parm[:4]=(1).to_bytes(4,'little')
    fcntl.ioctl(fd,0xc0cc5615,parm,True)
    original['interval']=[int.from_bytes(parm[12:16],'little'),int.from_bytes(parm[16:20],'little')]
    fmt=bytearray(208); fmt[:4]=(1).to_bytes(4,'little')
    fcntl.ioctl(fd,0xc0d05604,fmt,True)
    original['format_hex']=fmt.hex(); original['parm_hex']=parm.hex()
    (args.output/'original.json').write_text(json.dumps(original,indent=2)+'\n')
    report['original']=original
    try:
        cap=cv2.VideoCapture(DEVICE,cv2.CAP_V4L2)
        if not cap.isOpened(): raise RuntimeError('Camera open failed')
        for key,value in ((cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG')),
                          (cv2.CAP_PROP_FRAME_WIDTH,640),(cv2.CAP_PROP_FRAME_HEIGHT,480),
                          (cv2.CAP_PROP_FPS,30),(cv2.CAP_PROP_BUFFERSIZE,1)):
            if not cap.set(key,value): raise RuntimeError('Capture setting rejected: '+str(key))
        for label,exposure,buffers,fps in (('baseline_auto',None,1,30),('manual_10ms',100,1,30),
                ('manual_5ms',50,1,30),('auto_30fps_buffer4',None,4,30),('auto_60fps_buffer4',None,4,60)):
            cap.set(cv2.CAP_PROP_BUFFERSIZE,buffers); cap.set(cv2.CAP_PROP_FPS,fps)
            if exposure is not None:
                control(fd,AUTO,1); control(fd,EXPOSURE,exposure)
            else:
                control(fd,AUTO,1); control(fd,EXPOSURE,original['exposure_absolute']); control(fd,AUTO,original['auto_exposure'])
            stamps=[]; means=[]
            for i in range(45):
                ok,frame=cap.read(); stamp=time.monotonic()
                if not ok: raise RuntimeError('Frame acquisition failed')
                if i>=15: stamps.append(stamp); means.append(float(frame.mean()))
            gaps=[b-a for a,b in zip(stamps,stamps[1:])]
            trial=dict(label=label,auto_exposure=control(fd,AUTO),exposure_absolute=control(fd,EXPOSURE),
                       requested_fps=fps,buffer_count=cap.get(cv2.CAP_PROP_BUFFERSIZE),
                       reported_fps=cap.get(cv2.CAP_PROP_FPS),measured_hz=29/(stamps[-1]-stamps[0]),
                       gap_min_s=min(gaps),gap_max_s=max(gaps),mean_pixel=statistics.mean(means),receive_times=stamps)
            report['trials'].append(trial)
            cv2.imwrite(str(args.output/(label+'.jpg')),frame)
            print(json.dumps(trial),flush=True)
    except Exception as exc: report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if cap: cap.release()
        errors=[]
        for key,value in ((AUTO,1),(EXPOSURE,original['exposure_absolute']),(AUTO,original['auto_exposure'])):
            try: control(fd,key,value)
            except Exception as exc: errors.append(str(exc))
        for request,data in ((0xc0d05605,fmt),(0xc0cc5616,parm)):
            try: fcntl.ioctl(fd,request,data,True)
            except Exception as exc: errors.append(str(exc))
        try:
            restored=dict(auto_exposure=control(fd,AUTO),exposure_absolute=control(fd,EXPOSURE))
            check=bytearray(204); check[:4]=(1).to_bytes(4,'little'); fcntl.ioctl(fd,0xc0cc5615,check,True)
            restored['interval']=[int.from_bytes(check[12:16],'little'),int.from_bytes(check[16:20],'little')]
            report['restored']=restored
            report['restore_confirmed']=not errors and all(restored[k]==original[k] for k in restored)
            check_format=bytearray(208); check_format[:4]=(1).to_bytes(4,'little')
            fcntl.ioctl(fd,0xc0d05604,check_format,True)
            report['format_restored']=check_format[8:20]==bytes.fromhex(original['format_hex'])[8:20]
            report['restore_confirmed']=report['restore_confirmed'] and report['format_restored']
        except Exception as exc: errors.append(str(exc)); report['restore_confirmed']=False
        report['restore_errors']=errors; os.close(fd)
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    return 0 if report['restore_confirmed'] and 'error' not in report else 1


if __name__=='__main__': raise SystemExit(main())
