"""SONIC -> body lifecycle RECORD-ONLY boundary. No SDK, sockets or actuator IO.

The source age is a local conservative bound; no remote timestamps are compared.
PIKA width is metadata only, never a Dex3 or motor target. This boundary does not
implement a writer scheduler, ownership transfer, physical stop or robot output.
"""
import copy
import math
from body_lifecycle import BodyLifecycle, LifecycleFault
from sonic_startup_ablation import vector

SCHEMA = 'sonic_to_body_record_v1'


def envelope(session, seq, frame, result, *, source_age_s, joint_names):
    """Wrap the existing SONIC hardware-order output without altering values."""
    return dict(schema=SCHEMA,session=session,seq=seq,mode='record_only',
        hardware_output_enabled=False,robot_commands_sent=False,
        source_body_tick=frame['tick'],body=copy.deepcopy(frame),source_age_s=source_age_s,
        joint_names=list(joint_names),sonic=copy.deepcopy(result))


class SonicBodyBridge:
    def __init__(self, lifecycle):
        if not isinstance(lifecycle,BodyLifecycle): raise ValueError('BodyLifecycle required')
        self.lifecycle=lifecycle; self.next_seq=0; self.accepted=0; self.gated=0
        self.last=None

    def consume(self, message, *, now, observe_carried_body=True):
        c=self.lifecycle
        try:
            required={'schema','session','seq','mode','hardware_output_enabled','robot_commands_sent',
                      'source_body_tick','body','source_age_s','joint_names','sonic'}
            if (set(message)!=required or message['schema']!=SCHEMA or message['session']!=c.session
                    or type(message['seq']) is not int or message['seq']!=self.next_seq
                    or message['mode']!='record_only' or message['hardware_output_enabled'] is not False
                    or message['robot_commands_sent'] is not False):
                raise ValueError('Body envelope identity/mode/sequence')
            if message['joint_names']!=c.profile['names']: raise ValueError('Hardware joint order mismatch')
            if (type(message['source_body_tick']) is not int or
                    message['source_body_tick']!=message['body']['tick']): raise ValueError('Body endpoint tick mismatch')
            result=message['sonic']; q=result['q_target_hardware']; vector(q,29)
            if type(result['seq']) is not int or result['seq']!=message['seq']: raise ValueError('SONIC result sequence')
            # These worker results normally omit output flags. If present, reject
            # a physical claim rather than concealing it inside a false envelope.
            for key in ('hardware_output_enabled','robot_commands_sent','hardware_ready'):
                if key in result and result[key] is not False: raise ValueError('SONIC physical output claim')
            width=result['gripper_width_m']
            if (type(width) not in (float,int) or not math.isfinite(width) or not 0<=width<=.1
                    or result.get('gripper_actuated') is not False): raise ValueError('PIKA width metadata required')
            age=message['source_age_s']
            if type(age) not in (float,int) or not math.isfinite(age) or not 0<=age<=c.config['max_command_age_s']:
                raise ValueError('Body command source age')
            # The body and computed target are carried together. Body age must
            # include inference time before leaving the coordinator.
            if observe_carried_body: c.observe(message['body'],now=now,source_age_s=age)
            else: c.poll(now)  # LocalSonicBodyBridge is the only local observation owner.
            outside=[name for name,v,low,high in zip(c.profile['names'],q,c.profile['lower'],c.profile['upper'])
                     if not low<=v<=high]
            decision='gated_initial_pose_not_ready'
            if c.phase in {'ready','tracking'}:
                c.accept_target(session=c.session,seq=c.control_seq+1,q=q,now=now,source_age_s=age)
                self.accepted+=1; decision='accepted_abstract_target_NOT_sent'
            else: self.gated+=1
            self.next_seq+=1
            self.last=dict(seq=message['seq'],source_body_tick=message['source_body_tick'],decision=decision,
                target_limit_violations=outside,phase=c.phase,gripper_width_m=width,
                gripper_actuated=False,hardware_ready=False,robot_commands_sent=False)
            return copy.deepcopy(self.last)
        except (ValueError,TypeError,KeyError,LifecycleFault) as exc:
            c.request_stop('body_boundary_rejected: '+str(exc))
            raise

    def stop(self):
        return self.lifecycle.request_stop('body_boundary_end')

    def status(self):
        return dict(received=self.next_seq,accepted_abstract_targets=self.accepted,gated_targets=self.gated,
                    lifecycle=self.lifecycle.status(),physical_stop_validated=False,robot_commands_sent=False)


class LocalSonicBodyBridge:
    """G1-side core: carried GPU body data cannot refresh local sensor liveness.

    Pure preparation only. Owner must schedule poll independently of network IO;
    no device process, takeover, physical stop or 500Hz writer is launched here.
    """
    def __init__(self, lifecycle):
        from local_body_monitor import LocalBodyMonitor
        self.bridge=SonicBodyBridge(lifecycle)
        self.monitor=LocalBodyMonitor(max_age_s=lifecycle.config['max_body_age_s'])

    def observe_local(self, frame, *, now):
        try:
            fresh=self.monitor.ingest_local(frame,now=now)
            if fresh:
                local,age=self.monitor.snapshot(now=now)
                self.bridge.lifecycle.observe(local,now=now,source_age_s=age)
            return fresh
        except (ValueError,KeyError,TypeError,LifecycleFault) as exc:
            self.bridge.lifecycle.request_stop('local_body_rejected: '+str(exc)); raise

    def poll(self, *, now):
        try:
            self.monitor.snapshot(now=now)
            return self.bridge.lifecycle.poll(now)
        except (ValueError,LifecycleFault) as exc:
            self.bridge.lifecycle.request_stop('local_body_watchdog: '+str(exc)); raise

    def consume(self, message, *, now):
        try:
            local,_=self.monitor.snapshot(now=now)
            tick=message['source_body_tick']
            if type(tick) is not int or not 0<=tick<=0xffffffff:
                raise ValueError('Invalid source body tick')
            if ((local['tick']-tick)&0xffffffff)>=0x80000000:
                raise ValueError('GPU source tick ahead of local LowState')
            return self.bridge.consume(message,now=now,observe_carried_body=False)
        except (ValueError,KeyError,TypeError,LifecycleFault) as exc:
            self.bridge.lifecycle.request_stop('local_boundary_rejected: '+str(exc)); raise

    def status(self):
        return dict(boundary=self.bridge.status(),local_monitor=self.monitor.status(),
            deployed_to_G1=False,physical_writer_implemented=False)


class BodyRecordWorker:
    """RecordSession-compatible handler; deliberately no takeover/INIT operation.

    Receiver clock is injected by the owner. Saved replays must label that clock
    diagnostic, not pretend that old observations are live sensor inputs.
    """
    def __init__(self, profile, config, clock):
        self.profile=profile; self.config=config; self.clock=clock
        self.bridge=None; self.phase='idle'

    def handle(self, message):
        try:
            if self.phase=='idle':
                if (set(message)!={'op','session','schema','mode'} or message.get('op')!='hello' or type(message.get('schema')) is not int or message['schema']!=1
                        or message.get('mode')!='record_only'): raise ValueError('Body worker handshake')
                c=BodyLifecycle(message['session'],self.profile,self.config)
                self.bridge=SonicBodyBridge(c); self.phase='running'
                return dict(ready=True,session=c.session,schema=1,mode='record_only',hardware_output_enabled=False)
            if self.phase!='running' or message.get('session')!=self.bridge.lifecycle.session:
                raise ValueError('Body worker session/phase')
            if message.get('op')=='stop':
                if set(message)!={'op','session'}: raise ValueError('Body worker stop schema')
                self.bridge.stop(); self.phase='stopped'
                return dict(stopped=True,session=self.bridge.lifecycle.session)
            if (set(message)!={'op','session','seq','payload'} or message.get('op')!='record' or type(message.get('seq')) is not int
                    or message['seq']!=self.bridge.next_seq or message['payload']['seq']!=message['seq']):
                raise ValueError('Body worker sequence')
            result=self.bridge.consume(message['payload'],now=self.clock())
            return dict(session=message['session'],seq=message['seq'],result=result,hardware_output_enabled=False)
        except (ValueError,KeyError,TypeError,LifecycleFault):
            if self.bridge: self.bridge.lifecycle.request_stop('body_worker_rejected')
            self.phase='fault'; raise


class BodyRecordClient:
    """Connect an existing online coordinator to RecordSession (record-only)."""
    def __init__(self, record_session, joint_names):
        self.transport=record_session; self.names=list(joint_names)

    def start(self): self.transport.start()

    def receive(self, seq, frame, result, *, source_age_s):
        message=envelope(self.transport.gate.session,seq,frame,result,
                         source_age_s=source_age_s,joint_names=self.names)
        reply=self.transport.query(seq,message,source_age_s)
        if (type(reply.get('seq')) is not int or reply['seq']!=seq
                or type(reply.get('source_body_tick')) is not int or reply['source_body_tick']!=frame['tick']
                or reply.get('robot_commands_sent') is not False or reply.get('hardware_ready') is not False
                or reply.get('gripper_actuated') is not False
                or reply.get('gripper_width_m')!=result['gripper_width_m']
                or reply.get('decision') not in {'gated_initial_pose_not_ready','accepted_abstract_target_NOT_sent'}):
            self.transport.close(); raise ValueError('Body boundary reply')
        return reply

    def stop(self): self.transport.stop()
    def close(self): self.transport.close()
