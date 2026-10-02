"""Record-only G1 native owner loop binding. No selectable hardware backend."""
import ctypes as C
import math
import time
from pathlib import Path
import numpy as np


class NativeBodyRecordRuntime:
    def __init__(self, library, profile, session):
        self.lib=C.CDLL(str(Path(library).resolve())); self.handle=None; self.session=session; self.seq=0
        ptr=C.POINTER(C.c_double)
        self.lib.g1_pika_record_create.argtypes=[C.c_char_p]+[ptr]*4
        self.lib.g1_pika_record_create.restype=C.c_void_p
        self.lib.g1_pika_record_error.restype=C.c_char_p
        self.lib.g1_pika_record_now.restype=C.c_double
        self.lib.g1_pika_record_body.argtypes=[C.c_void_p,C.c_double,C.c_uint32,C.c_uint8,C.c_uint8,C.POINTER(C.c_uint32)]
        self.lib.g1_pika_record_reference.argtypes=[C.c_void_p,C.c_char_p,C.c_uint64,C.c_double,C.c_double]+[ptr]*5
        self.lib.g1_pika_record_begin.argtypes=[C.c_void_p]
        self.lib.g1_pika_record_stop.argtypes=[C.c_void_p,C.c_char_p]
        self.lib.g1_pika_record_snapshot.argtypes=[C.c_void_p,C.POINTER(C.c_ubyte),C.POINTER(C.c_uint64),ptr,C.c_char_p,C.c_size_t]
        self.lib.g1_pika_record_delete.argtypes=[C.c_void_p]; self.lib.g1_pika_record_delete.restype=None
        # Linux steady_clock and local Python CLOCK_MONOTONIC must share epoch.
        before=time.monotonic(); native=self.lib.g1_pika_record_now(); after=time.monotonic()
        if not before-.001<=native<=after+.001: raise ValueError('Local monotonic clock mismatch')
        arrays=[self.vector(profile[name]) for name in ('lower','upper','velocity','kd')]
        self.handle=self.lib.g1_pika_record_create(session.encode(),*(a.ctypes.data_as(ptr) for a in arrays))
        if not self.handle: raise ValueError(self.lib.g1_pika_record_error().decode())

    @staticmethod
    def vector(value):
        a=np.ascontiguousarray(value,dtype=np.float64)
        if a.shape!=(29,) or not np.isfinite(a).all(): raise ValueError('Finite 29-vector required')
        return a

    def checked(self,status):
        if status: raise ValueError(self.lib.g1_pika_record_error().decode())

    def local_body(self,frame):
        if (frame.get('crc_verified') is not True or type(frame.get('crc_received')) is not int
                or frame['crc_received']!=frame.get('crc_calculated') or frame.get('crc_native_size_bytes')!=2092):
            raise ValueError('Strict local LowState CRC required')
        raw=frame.get('raw_motor_state')
        if not isinstance(raw,list) or len(raw)!=35 or any(type(v) is not int or not 0<=v<=0xffffffff for v in raw):
            raise ValueError('Local receiver raw_motor_state[35] required; legacy input is insufficient')
        for key in ('mode_pr','mode_machine'):
            if type(frame.get(key)) is not int or not 0<=frame[key]<=255: raise ValueError('Local body mode invalid')
        stamp=frame['receive_monotonic_s']
        if type(stamp) not in (int,float) or not math.isfinite(stamp): raise ValueError('Local body timestamp required')
        values=(C.c_uint32*29)(*raw[:29])
        self.checked(self.lib.g1_pika_record_body(self.handle,stamp,frame['tick'],frame['mode_pr'],frame['mode_machine'],values))

    def reference(self,ref,*,now):
        arrays=[self.vector(ref[key]) for key in ('q','dq','tau','kp','kd')]
        self.checked(self.lib.g1_pika_record_reference(self.handle,self.session.encode(),self.seq,now,ref['source_age_s'],
            *(a.ctypes.data_as(C.POINTER(C.c_double)) for a in arrays)))
        self.seq+=1

    def begin(self): self.checked(self.lib.g1_pika_record_begin(self.handle))

    def snapshot(self):
        packet=(C.c_ubyte*1004)(); counts=(C.c_uint64*6)(); timings=(C.c_double*2)(); reason=C.create_string_buffer(512)
        self.checked(self.lib.g1_pika_record_snapshot(self.handle,packet,counts,timings,reason,len(reason)))
        return dict(memory_publications=counts[0],owner_exited=bool(counts[1]),stop_latched=bool(counts[2]),
            normal_publications_final=counts[3],record_stop_attempted=bool(counts[4]),record_stop_write_accepted=bool(counts[5]),
            max_start_gap_s=timings[0],max_memory_write_s=timings[1],reason=reason.value.decode(),
            references=self.seq,last_native_memory_hex=bytes(packet).hex(),robot_commands_sent=False,
            hardware_transport_linked=False,physical_stop_confirmed=False,physical_ownership_confirmed=False,
            motor_health_criterion='record-only raw zero bits; NOT firmware health certification')

    def stop(self,reason='local_record_stop'):
        if self.handle: self.checked(self.lib.g1_pika_record_stop(self.handle,reason.encode()))

    def close(self):
        if self.handle: self.lib.g1_pika_record_delete(self.handle); self.handle=None
