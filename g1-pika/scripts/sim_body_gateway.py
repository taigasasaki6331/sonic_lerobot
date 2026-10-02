"""SIM ONLY native LowCmd gateway -> float32 motor fields -> MuJoCo torque.

No hardware backend can be selected. Startup/ownership/CRC/health acknowledgements
are artificial simulation facts. Physical WriterMailbox gates remain unchanged;
this sim path does not claim those gates passed or validate physical readiness.
"""
import ctypes as C
import hashlib
import struct
import numpy as np


class SimBodyGateway:
    def __init__(self, library, profile):
        self.lib=C.CDLL(str(library)); self.handle=None; self.stopped=False; self.sequence=0
        self.digest=hashlib.sha256(); self.samples=[]; self.max_target_step=0.; self.previous=None
        double=C.POINTER(C.c_double)
        self.lib.g1_pika_sim_create.argtypes=[double]*5; self.lib.g1_pika_sim_create.restype=C.c_void_p
        self.lib.g1_pika_sim_error.restype=C.c_char_p
        for name in ('begin','stop','delete'):
            fn=getattr(self.lib,'g1_pika_sim_'+name); fn.argtypes=[C.c_void_p]
        self.lib.g1_pika_sim_delete.restype=None
        self.lib.g1_pika_sim_reference.argtypes=[C.c_void_p,C.c_double,C.c_uint64,double]
        self.lib.g1_pika_sim_tick.argtypes=[C.c_void_p,C.c_double,C.POINTER(C.c_ubyte)]
        self.lib.g1_pika_sim_counts.argtypes=[C.c_void_p,C.POINTER(C.c_uint64)]
        arrays=[self.vector(profile[name]) for name in ('lower','upper','kp','kd','defaults')]
        self.handle=self.lib.g1_pika_sim_create(*(a.ctypes.data_as(double) for a in arrays))
        if not self.handle: raise ValueError(self.lib.g1_pika_sim_error().decode())
        try: self.checked(self.lib.g1_pika_sim_begin(self.handle))
        except BaseException: self.lib.g1_pika_sim_delete(self.handle); self.handle=None; raise

    @staticmethod
    def vector(v):
        a=np.ascontiguousarray(v,dtype=np.float64)
        if a.shape!=(29,) or not np.isfinite(a).all(): raise ValueError('Finite 29-motor vector required')
        return a

    def checked(self, status):
        if status: raise ValueError(self.lib.g1_pika_sim_error().decode())

    def reference(self, now, target):
        q=self.vector(target)
        self.checked(self.lib.g1_pika_sim_reference(self.handle,float(now),self.sequence,q.ctypes.data_as(C.POINTER(C.c_double))))
        if self.previous is not None: self.max_target_step=max(self.max_target_step,float(np.max(abs(q-self.previous))))
        self.previous=q.copy(); self.sequence+=1

    def tick(self, now, q, dq):
        measured_q=self.vector(q); measured_dq=self.vector(dq)
        packet=(C.c_ubyte*1004)(); self.checked(self.lib.g1_pika_sim_tick(self.handle,float(now),packet))
        data=bytes(packet); self.digest.update(data)
        motors=[struct.unpack_from('<B3x5fI',data,4+28*i) for i in range(29)]
        # These are the published native float32 fields, not the Python target.
        values=np.asarray([m[1:6] for m in motors],dtype=float)
        if data[:4]!=bytes([0,5,0,0]) or any(m[0]!=1 or m[6]!=0 for m in motors):
            raise ValueError('Native simulation LowCmd layout invalid')
        if len(self.samples)<4: self.samples.append(dict(sim_time_s=float(now),native_memory_hex=data.hex()))
        torque=values[:,3]*(values[:,0]-measured_q)+values[:,4]*(values[:,1]-measured_dq)+values[:,2]
        if not np.isfinite(torque).all(): raise ValueError('Nonfinite native simulation torque')
        return torque

    def stop(self):
        if self.handle and not self.stopped:
            self.checked(self.lib.g1_pika_sim_stop(self.handle)); self.stopped=True

    def report(self):
        counts=(C.c_uint64*5)(); self.checked(self.lib.g1_pika_sim_counts(self.handle,counts))
        return dict(scope='SIMULATION_ONLY_native_adapter_writer_LowCmd_fields_MuJoCo',
            references=counts[0],writer_ticks=counts[1],memory_publications=counts[2],
            simulated_releases=counts[3],simulated_restores=counts[4],stop_completed=self.stopped,
            native_lowcmd_stream_sha256=self.digest.hexdigest(),max_reference_step_rad=self.max_target_step,
            physical_step_gate_passed=self.max_target_step<=.05,physical_ready=False,
            physical_stop_confirmed=False,hardware_transport_linked=False,robot_commands_sent=False,
            local_evidence='artificial_simulation_NOT_actual_LowState_or_ownership',samples=self.samples)

    def close(self):
        if self.handle:
            self.lib.g1_pika_sim_delete(self.handle); self.handle=None
