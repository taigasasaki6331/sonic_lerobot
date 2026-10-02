"""Bounded JSON request/reply via installed libzmq; no pickle or robot APIs."""
import ctypes as C
import ctypes.util
import json
import math


class ZmqChannel:
    def __init__(self,endpoint,server=False,timeout_ms=5000,accept_filter=None,max_message_bytes=None,kind=None):
        self.limit=(4096 if server else 2000000) if max_message_bytes is None else max_message_bytes
        if type(self.limit) is not int or not 1 <= self.limit <= 2000000:
            raise ValueError('Invalid message bound')
        self.lib=C.CDLL(ctypes.util.find_library('zmq') or 'libzmq.so.5')
        for name,restype,argtypes in [
            ('zmq_ctx_new',C.c_void_p,[]),('zmq_ctx_term',C.c_int,[C.c_void_p]),
            ('zmq_socket',C.c_void_p,[C.c_void_p,C.c_int]),('zmq_close',C.c_int,[C.c_void_p]),
            ('zmq_bind',C.c_int,[C.c_void_p,C.c_char_p]),('zmq_connect',C.c_int,[C.c_void_p,C.c_char_p]),
            ('zmq_setsockopt',C.c_int,[C.c_void_p,C.c_int,C.c_void_p,C.c_size_t]),
            ('zmq_send',C.c_int,[C.c_void_p,C.c_void_p,C.c_size_t,C.c_int]),
            ('zmq_recv',C.c_int,[C.c_void_p,C.c_void_p,C.c_size_t,C.c_int]),
            ('zmq_errno',C.c_int,[]),('zmq_strerror',C.c_char_p,[C.c_int]),
            ('zmq_version',None,[C.POINTER(C.c_int)]*3)]:
            fn=getattr(self.lib,name); fn.restype=restype; fn.argtypes=argtypes
        self.context=self.lib.zmq_ctx_new(); self.socket=None
        try:
            if not self.context: raise RuntimeError('ZMQ context failed')
            if kind not in (None, 'pub', 'sub'): raise ValueError('Invalid socket kind')
            self.socket=self.lib.zmq_socket(self.context,{'pub':1,'sub':2}.get(kind,4 if server else 3))
            if not self.socket: raise RuntimeError('ZMQ socket failed')
            for key,value in [(17,0),(23,1),(24,1),(27,timeout_ms),(28,timeout_ms)]:
                self.option(key,C.c_int(value))
            self.option(22,C.c_int64(self.limit))
            if kind=='sub': self.check(self.lib.zmq_setsockopt(self.socket,6,b'',0))
            if accept_filter:
                value=accept_filter.encode()
                self.check(self.lib.zmq_setsockopt(self.socket,38,value,len(value)))
            fn=self.lib.zmq_bind if server else self.lib.zmq_connect
            self.check(fn(self.socket,endpoint.encode()))
        except BaseException:
            self.close(); raise
    def check(self,result):
        if result<0:
            code=self.lib.zmq_errno()
            raise OSError(code,self.lib.zmq_strerror(code).decode())
        return result
    def option(self,key,value):
        self.check(self.lib.zmq_setsockopt(self.socket,key,C.byref(value),C.sizeof(value)))
    def version(self):
        a,b,c=C.c_int(),C.c_int(),C.c_int()
        self.lib.zmq_version(C.byref(a),C.byref(b),C.byref(c))
        return f'{a.value}.{b.value}.{c.value}'
    def send(self,value):
        payload=json.dumps(value,allow_nan=False).encode()
        if len(payload)>2000000: raise ValueError('Oversized ZMQ output')
        self.check(self.lib.zmq_send(self.socket,payload,len(payload),0))
    def read(self):
        buffer=C.create_string_buffer(self.limit)
        size=self.check(self.lib.zmq_recv(self.socket,buffer,self.limit,0))
        if size>self.limit: raise ValueError('Oversized ZMQ message')
        def reject_constant(value): raise ValueError('Nonfinite JSON constant: '+value)
        value=json.loads(buffer.raw[:size],parse_constant=reject_constant)
        def finite(item):
            if isinstance(item,float) and not math.isfinite(item): raise ValueError('Nonfinite JSON number')
            if isinstance(item,dict):
                for nested in item.values(): finite(nested)
            elif isinstance(item,list):
                for nested in item: finite(nested)
        finite(value)
        if not isinstance(value,dict): raise ValueError('Expected JSON object')
        return value
    def finish(self):
        self.send({'stop':True})
        if self.read()!={'stopped':True}: raise ValueError('Invalid shutdown response')
    def close(self):
        if self.socket: self.lib.zmq_close(self.socket); self.socket=None
        if self.context: self.lib.zmq_ctx_term(self.context); self.context=None
