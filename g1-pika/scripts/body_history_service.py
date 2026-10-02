"""Serve receive_state --stream stdin as bounded read-only ZMQ body histories.

Does not launch DDS, cameras, serial devices, or a control program. The supplying
receiver must be independently bounded. Do not invoke on G1 before input-read
authorization. This file is not executed by make's default/offline targets.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import select
import sys
import threading
import time
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_history_transport import BodyHistoryBuffer,BodyHistoryServer
from sonic_process import strict_message
from zmq_transport import ZmqChannel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--peer-ip',help='Required for TCP; single allowed IPv4 peer')
    parser.add_argument('--max-frames',type=int,default=1500,choices=range(1,1501))
    parser.add_argument('--seconds',type=int,default=60,choices=range(1,91))
    args=parser.parse_args()
    endpoint=urlsplit(args.endpoint); accept_filter=None
    if endpoint.scheme=='tcp':
        local=ipaddress.IPv4Address(endpoint.hostname)
        if local.is_unspecified or local.is_multicast or not endpoint.port: parser.error('Explicit unicast bind IP/port required')
        if not args.peer_ip: parser.error('TCP requires --peer-ip')
        peer=ipaddress.IPv4Address(args.peer_ip)
        if peer.is_unspecified or peer.is_multicast: parser.error('Explicit unicast peer required')
        accept_filter=str(peer)+'/32'
    elif endpoint.scheme!='ipc' or not endpoint.path.startswith('/'):
        parser.error('Explicit TCP or absolute IPC endpoint required')
    buffer=BodyHistoryBuffer(); server=BodyHistoryServer(buffer,args.max_frames)
    stop=threading.Event(); channel=None
    def ingest():
        pending=b''
        try:
            while not stop.is_set():
                if not select.select([sys.stdin.buffer],[],[],.1)[0]: continue
                chunk=os.read(sys.stdin.fileno(),65536)
                if not chunk: raise RuntimeError('Body receiver EOF')
                pending+=chunk
                if len(pending)>2000000: raise ValueError('Body input too large')
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1); buffer.push(strict_message(line))
        except Exception as exc: buffer.fail(type(exc).__name__+': '+str(exc))
    thread=threading.Thread(target=ingest); thread.start()
    try:
        channel=ZmqChannel(args.endpoint,server=True,timeout_ms=1000,accept_filter=accept_filter)
        buffer.snapshot(timeout_s=5,allow_warmup=True)
        print(json.dumps(dict(ready=True,scope='body_history_input_only',robot_commands_sent=False)),flush=True)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline and not server.closed:
            try: request=channel.read()
            except OSError as exc:
                if exc.errno==11: continue
                raise
            try: response=server.handle(request)
            except Exception as exc:
                channel.send(dict(error=type(exc).__name__+': '+str(exc),robot_commands_sent=False)); raise
            channel.send(response)
        if not server.closed: raise TimeoutError('Body service lifetime expired')
    finally:
        stop.set(); buffer.close(); thread.join(2)
        if channel: channel.close()
        if thread.is_alive(): raise RuntimeError('Body input thread did not exit')


if __name__=='__main__': main()
