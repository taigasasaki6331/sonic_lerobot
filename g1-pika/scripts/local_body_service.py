"""G1-side record-only boundary with an independent same-host LowState monitor.

Feed receive_state --stream on stdin. ZMQ accepts GPU hello/record/stop, NEVER
local_state, takeover, INIT or execute. No publisher, serial or actuator code.
Not launched by default/offline commands; no real-time or physical-stop claim.
"""
import argparse
import faulthandler
import ipaddress
import json
import os
from pathlib import Path
import select
import signal
import sys
import threading
import time
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import BodyLifecycle,settings
from local_body_monitor import LocalBodyMonitor
from sonic_body_bridge import LocalSonicBodyBridge
from sonic_process import strict_message
from state_history import validate_state


class LocalBodyRecordWorker:
    def __init__(self,profile,config,clock=time.monotonic,*,require_crc=False):
        self.profile=profile; self.config=settings(config); self.clock=clock
        self.monitor=LocalBodyMonitor(max_age_s=self.config['max_body_age_s'],require_crc=require_crc)
        self.bridge=None; self.phase='idle'

    def ingest_local(self,frame):
        # Only the supplying local receiver invokes this; not a peer operation.
        if self.phase in {'fault','stopped'}: raise ValueError('Local body worker closed')
        if self.bridge: return self.bridge.observe_local(frame,now=self.clock())
        if self.monitor.frame is None:
            # Interpreter startup can leave old pipe samples. Discard only
            # before the FIRST accepted sample/handshake; never renew an active
            # watchdog or pretend an old packet was received now.
            validate_state(frame)
            if self.clock()-frame['receive_monotonic_s']>self.monitor.max_age_s: return False
        return self.monitor.ingest_local(frame,now=self.clock())

    def poll(self):
        try:
            if self.bridge: self.bridge.poll(now=self.clock())
            else: self.monitor.snapshot(now=self.clock())
        except Exception:
            self.fail('local_body_poll_failed'); raise

    def fail(self,reason):
        if self.bridge: self.bridge.bridge.lifecycle.request_stop(reason)
        self.phase='fault'

    def handle(self,message):
        try:
            self.poll()
            if self.phase=='idle':
                if (set(message)!={'op','session','schema','mode'} or message['op']!='hello'
                        or type(message['schema']) is not int or message['schema']!=1
                        or message['mode']!='record_only'): raise ValueError('Local body hello schema')
                lifecycle=BodyLifecycle(message['session'],self.profile,self.config)
                self.bridge=LocalSonicBodyBridge(lifecycle)
                self.bridge.monitor=self.monitor
                frame,age=self.monitor.snapshot(now=self.clock())
                lifecycle.observe(frame,now=self.clock(),source_age_s=age)
                self.phase='running'
                return dict(ready=True,session=lifecycle.session,schema=1,mode='record_only',hardware_output_enabled=False)
            if self.phase!='running' or message.get('session')!=self.bridge.bridge.lifecycle.session:
                raise ValueError('Local body session/phase')
            if message==dict(op='stop',session=message['session']):
                self.bridge.bridge.stop(); self.phase='stopped'
                return dict(stopped=True,session=message['session'])
            if (set(message)!={'op','session','seq','payload'} or message['op']!='record'
                    or type(message['seq']) is not int or message['seq']!=message['payload']['seq']):
                raise ValueError('Local body record schema')
            result=self.bridge.consume(message['payload'],now=self.clock())
            return dict(session=message['session'],seq=message['seq'],result=result,hardware_output_enabled=False)
        except Exception:
            self.fail('local_body_peer_rejected'); raise


def endpoint_filter(endpoint,peer_ip):
    endpoint=urlsplit(endpoint)
    if endpoint.scheme=='ipc' and endpoint.path.startswith('/') and not peer_ip: return None
    if endpoint.scheme!='tcp' or not endpoint.port or not peer_ip:
        raise ValueError('Require absolute IPC, or explicit TCP IP/port and allowed peer IPv4')
    for value in (endpoint.hostname,peer_ip):
        address=ipaddress.IPv4Address(value)
        if address.is_unspecified or address.is_multicast: raise ValueError('Require explicit unicast IPv4')
    return str(ipaddress.IPv4Address(peer_ip))+'/32'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True); parser.add_argument('--peer-ip')
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--seconds',type=int,choices=range(1,61),default=30)
    parser.add_argument('--report',type=Path,help='Optional diagnostic journal; no physical-stop claim')
    parser.add_argument('--require-crc',action='store_true',help='Reject legacy/unchecked local LowState')
    parser.add_argument('--native-runtime',type=Path,
        help='Record-only native owner library: rehearse local INIT/writer/stop; NEVER hardware IO')
    args=parser.parse_args()
    if args.native_runtime:
        faulthandler.enable()
        faulthandler.register(signal.SIGUSR1,all_threads=True)
    try: accept_filter=endpoint_filter(args.endpoint,args.peer_ip)
    except ValueError as exc: parser.error(str(exc))
    worker_type=LocalBodyRecordWorker
    if args.native_runtime:
        from local_body_runtime import LocalBodyRuntimeWorker
        worker_type=LocalBodyRuntimeWorker
    worker=worker_type(strict_message(args.profile.read_bytes()),strict_message(args.config.read_bytes()),
        require_crc=args.require_crc or bool(args.native_runtime),
        **(dict(library=args.native_runtime) if args.native_runtime else {}))
    stop=threading.Event(); initial=threading.Event(); lock=threading.RLock(); errors=[]; channel=None
    fault_at=[]
    def fail(exc):
        with lock:
            if not fault_at: fault_at.append(time.monotonic())
            errors.append(type(exc).__name__+': '+str(exc)); worker.fail(errors[-1])
        initial.set(); stop.set()
    def ingest():
        pending=b''
        try:
            while not stop.is_set():
                if not select.select([sys.stdin.buffer],[],[],.1)[0]: continue
                chunk=os.read(sys.stdin.fileno(),65536)
                if not chunk: raise RuntimeError('Local LowState receiver EOF')
                pending+=chunk
                if len(pending)>2000000: raise ValueError('Oversized local LowState buffer')
                while b'\n' in pending and not stop.is_set():
                    line,pending=pending.split(b'\n',1)
                    with lock:
                        if stop.is_set(): break
                        worker.ingest_local(strict_message(line))
                    if worker.monitor.frame is not None: initial.set()
        except Exception as exc: fail(exc)
    def watchdog():
        # Independent of ZMQ requests, joins, GPU inference and SSH. Python
        # 10ms polling is diagnostic only, NOT a guaranteed actuator stop time.
        try:
            next_reference=time.monotonic()
            while not stop.wait(.005 if args.native_runtime else .01):
                with lock:
                    worker.poll()
                    if args.native_runtime and time.monotonic()>=next_reference:
                        worker.control_tick()
                        # No catch-up burst after interpreter scheduling delay.
                        next_reference=time.monotonic()+.02
        except Exception as exc: fail(exc)
    reader=threading.Thread(target=ingest); watch=threading.Thread(target=watchdog)
    reader.start()
    try:
        if not initial.wait(5) or errors: raise RuntimeError('No valid local LowState: '+str(errors))
        watch.start()
        from zmq_transport import ZmqChannel
        # Real LowState + SONIC arrays exceed the transport's 4KiB server
        # default. Still bound input; never truncate a record envelope.
        channel=ZmqChannel(args.endpoint,server=True,timeout_ms=100,accept_filter=accept_filter,
                           max_message_bytes=65536)
        print(json.dumps(dict(ready=True,scope='local_body_boundary_record_only',robot_commands_sent=False)),flush=True)
        deadline=time.monotonic()+args.seconds
        while not stop.is_set() and time.monotonic()<deadline:
            try: request=channel.read()
            except OSError as exc:
                if exc.errno in (11,4): continue  # timeout or diagnostic SIGUSR1 dump
                raise
            with lock:
                response=worker.handle(request)
                if worker.phase=='stopped': stop.set()
            channel.send(response)
            if worker.phase=='stopped': break
        if worker.phase!='stopped': raise RuntimeError('Local body service terminated without diagnostic stop ACK: '+str(errors))
    finally:
        stop.set()
        with lock:
            if worker.bridge: worker.bridge.bridge.stop()
            if args.native_runtime: worker.stop_native('local_service_end')
        if channel: channel.close()
        reader.join(2)
        if watch.ident is not None: watch.join(2)
        if args.report:
            args.report.write_text(json.dumps(dict(scope='record_only_local_monitor',phase=worker.phase,
                errors=errors,fault_observed_monotonic_s=fault_at[0] if fault_at else None,
                last_receive_monotonic_s=worker.monitor.frame['receive_monotonic_s'] if worker.monitor.frame else None,
                monitor=worker.monitor.status(),
                boundary=worker.bridge.bridge.status() if worker.bridge else None,
                native_runtime=worker.native_status() if args.native_runtime else None,
                reader_exited=not reader.is_alive(),watchdog_exited=not watch.is_alive(),
                robot_commands_sent=False,physical_stop_validated=False),indent=2)+'\n')
        if reader.is_alive() or watch.is_alive(): raise RuntimeError('Local body service thread did not exit')
        if args.native_runtime: worker.close_native()


if __name__=='__main__': main()
