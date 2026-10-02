"""Bounded online input -> ACT/IK -> measured SONIC observation -> log ONLY.

The caller owns four workers (ACT, IK, observation, SONIC) and two receive-only
ZMQ channels. This module cannot send robot/PIKA commands. No fallback to saved
or synthetic body history is permitted. Hardware readiness is never asserted.
"""
import copy
import gc
import math
import queue
import threading
import time
import uuid
from reference_mailbox import ReferenceMailbox
from state_history import validate_history


def camera_age(packet,seq,previous,sent,received):
    if (packet.get('schema_version')!=2 or type(packet.get('schema_version')) is not int
            or type(packet.get('seq')) is not int or packet['seq']!=seq
            or packet.get('robot_commands_sent') is not False): raise ValueError('Camera schema/sequence/mode')
    age=packet['capture_age_s']
    if any(type(v) not in (float,int) or not math.isfinite(v) for v in (age,sent,received)):
        raise ValueError('Camera age values')
    elapsed=received-sent
    processing=packet.get('request_processing_s',0.)
    if type(processing) not in (float,int) or not math.isfinite(processing) or not 0<=processing<=elapsed:
        raise ValueError('Invalid camera processing duration')
    # Source age is measured AFTER encoding. Subtract only the measured server
    # processing already included in RTT to avoid counting it twice. No clocks
    # from different hosts are subtracted; all remaining RTT stays conservative.
    bounded_age=age+elapsed-processing
    if not 0<=age or not 0<=elapsed or bounded_age>.1:
        raise ValueError(f'Camera packet expired in transport: age={bounded_age:.9f}s source={age:.9f}s RTT={elapsed:.9f}s processing={processing:.9f}s')
    if set(packet['images'])!={'realsense_rgb','fisheye'}: raise ValueError('Camera roles')
    updated={}
    for role,image in packet['images'].items():
        count=image['frame_counter']
        if type(count) is not int or count<=previous.get(role,0): raise ValueError('Repeated camera frame')
        if not isinstance(image.get('jpeg'),str) or not image['jpeg']: raise ValueError('Missing image payload')
        updated[role]=count
    history=validate_history(packet['g1_state_history'])
    if history[-1]!=packet['g1_state']: raise ValueError('Image/body history endpoint mismatch')
    gripper=packet['gripper']; width=gripper['width_m']
    if type(width) not in (float,int) or not math.isfinite(width) or not 0<=width<=.1:
        raise ValueError('Measured width range')
    if gripper['width_source']!='encoder_with_legacy_linkage_geometry': raise ValueError('Measured width required')
    previous.update(updated)
    return bounded_age


def run_online_loop(actor,ik,observer,sonic,camera,body,*,seconds,clock=time.monotonic,capture_recorder=None,body_recorder=None,joint_interpolation_s=None,body_sink=None):
    if type(seconds) is not int or not 1<=seconds<=30: raise ValueError('Duration must be 1..30 seconds')
    session=str(uuid.uuid4()); mailbox=ReferenceMailbox(session,.1)
    stop=threading.Event(); first=threading.Event(); errors=[]; actions=[]; outputs=[]
    # Finite diagnostic: acquisition starts before the first reference exists.
    # Keep three additional real policy frames through the control tail; do not
    # extend reference validity or duplicate the final sensor measurement.
    counts={}; policy_count=seconds*30+3; control_count=seconds*50; control_times=[]
    policy_timings=[]; body_timings=[]; captures=queue.Queue(maxsize=1)
    gc_started={}; gc_events=[]
    def track_gc(phase,info):
        generation=info['generation']
        if phase=='start': gc_started[generation]=time.monotonic()
        elif generation in gc_started:
            start=gc_started.pop(generation)
            gc_events.append(dict(generation=generation,started_at=start,duration_s=time.monotonic()-start))
    gc.callbacks.append(track_gc)
    def observe_operation(op,**values):
        observer.send(dict(op=op,**values)); reply=observer.read()
        if reply.get('hardware_output_enabled') is not False: raise ValueError('Observation worker output mode')
        return reply['result']
    def camera_loop():
        try:
            for seq in range(policy_count):
                if stop.is_set(): break
                # The 30fps source blocks until a new pair exists. An extra
                # independent 30Hz request clock can miss that window as its
                # phase drifts, producing occasional two-frame gaps.
                issued=clock(); camera.send(dict(seq=seq)); packet=camera.read(); received=clock()
                age=camera_age(packet,seq,counts,issued,received)
                while not stop.is_set():
                    try:
                        captures.put((packet,issued,received,age),timeout=.05); break
                    except queue.Full: pass
        except BaseException as exc:
            errors.append('camera: '+type(exc).__name__+': '+str(exc)); stop.set(); first.set()
    def policy_loop():
        try:
            for seq in range(policy_count):
                while not stop.is_set():
                    try:
                        packet,issued,received,age=captures.get(timeout=.05); break
                    except queue.Empty: pass
                else: break
                actor_started=clock()
                if actor_started-received+age>.1: raise ValueError('Queued camera input expired')
                actor.send(packet); action=actor.read(timeout=1); actor_done=clock()
                if type(action.get('seq')) is not int or action['seq']!=seq: raise ValueError('ACT sequence')
                frame=copy.deepcopy(action); frame['capture']=packet
                ik.send(dict(op='infer',seq=seq,frame=frame)); candidate=ik.read(timeout=1)
                if candidate.get('seq')!=seq or candidate.get('hardware_output_enabled') is not False:
                    raise ValueError('IK response identity')
                ik_done=clock()
                policy_timings.append(dict(seq=seq,camera_roundtrip_s=received-issued,
                    source_age_at_receive_s=age,queue_wait_s=actor_started-received,
                    actor_roundtrip_s=actor_done-actor_started,
                    ik_roundtrip_s=ik_done-actor_done,reference_age_at_publish_s=ik_done-received+age))
                reference=candidate['result']['absolute_reference']
                # issued_at carries a conservative local-clock bound on original sensor age.
                mailbox.publish(session=session,seq=seq,issued_at=received-age,finished_at=clock(),reference=reference)
                captured=capture_recorder(packet) if capture_recorder else None
                actions.append(dict(seq=seq,action=action,ik=candidate['result']['ik'],source_age_at_receive_s=age,capture=captured))
                first.set()
        except BaseException as exc:
            errors.append('policy: '+type(exc).__name__+': '+str(exc)); stop.set(); first.set()
    producer=threading.Thread(target=policy_loop)
    acquisition=threading.Thread(target=camera_loop)
    try:
        if actor.ready.get('ready') is not True: raise ValueError('ACT not ready')
        if ik.ready!=dict(ready=True,mode='measured_input_record_only',hardware_output_enabled=False): raise ValueError('IK input mode')
        if observer.ready!=dict(ready=True,mode='measured_record_only',hardware_output_enabled=False): raise ValueError('Observation mode')
        if body_sink is not None: body_sink.start()
        start_options={} if joint_interpolation_s is None else dict(joint_interpolation_s=joint_interpolation_s)
        observe_operation('start',session=session,**start_options); body.start(); acquisition.start(); producer.start()
        if not first.wait(5) or errors: raise RuntimeError('Initial policy reference unavailable: '+str(errors))
        epoch=clock(); last_reference=-1
        for seq in range(control_count):
            if stop.wait(max(0,epoch+seq/50-clock())): raise RuntimeError(str(errors))
            body_started=clock(); packet=body.read(); now=clock()
            body_timings.append(dict(seq=seq,roundtrip_s=now-body_started,source_age_s=packet['source_age_s']))
            reference=mailbox.read(now)
            control_times.append(now)
            if reference is None: raise ValueError('Missing reference')
            if reference['seq']!=last_reference:
                observe_operation('reference',session=session,seq=reference['seq'],reference=reference['reference'],
                                  issued_at=reference['issued_at'],finished_at=reference['finished_at'])
                last_reference=reference['seq']
            row=observe_operation('observe',session=session,seq=seq,body_history=packet['body_history'],now=now,
                                  source_age_s=packet['source_age_s']+now-packet['received_at'])
            result=sonic.infer(row)
            boundary={}
            if body_sink is not None:
                boundary['body_boundary']=body_sink.receive(seq,packet['body_history'][-1],result,
                    source_age_s=packet['source_age_s']+clock()-packet['received_at'])
            # Reject late inference before committing recurrent action history.
            if clock()-now>.02: raise TimeoutError('SONIC control computation exceeded 20ms')
            observe_operation('commit',session=session,seq=seq,result=result)
            body_record=body_recorder(seq,packet['body_history']) if body_recorder else packet['body_history']
            outputs.append(dict(seq=seq,policy_seq=last_reference,source_body_tick=packet['body_history'][-1]['tick'],
                                body_input_record=body_record,diagnostic_output=result,robot_commands_sent=False,**boundary))
        producer.join(3)
        acquisition.join(3)
        if acquisition.is_alive(): raise RuntimeError('Camera acquisition failed to stop')
        if producer.is_alive() or errors or len(actions)!=policy_count: raise RuntimeError(str(errors))
        body.stop(); camera.finish(); sonic.stop()
        actor.send(dict(stop=True))
        if actor.process.wait(timeout=3)!=0: raise RuntimeError('ACT shutdown')
        for worker in (ik,observer):
            worker.send(dict(op='stop'))
            if worker.read()!=dict(stopped=True) or worker.process.wait(timeout=3)!=0: raise RuntimeError('Worker shutdown')
        gaps=[b-a for a,b in zip(control_times,control_times[1:])]
        return dict(passed=True,scope='online_measured_inputs_SONIC_record_only',hardware_ready=False,
                    robot_commands_sent=False,policy_count=len(actions),control_count=len(outputs),
                    policy_records=actions,outputs=outputs,physical_stop_validated=False,
                    coordinator_gap_min_s=min(gaps),coordinator_gap_max_s=max(gaps),
                    coordinator_gaps_outside_20ms_plusminus_2ms=sum(not .018<=gap<=.022 for gap in gaps),
                    realtime_guaranteed=False,policy_timings=policy_timings,body_timings=body_timings,
                    reference_mode='IK_endpoint_hold' if joint_interpolation_s is None else 'causal_quintic_joint_reference_not_balance_plan',
                    joint_interpolation_s=joint_interpolation_s,
                    gc_pause_max_s=max((e['duration_s'] for e in gc_events),default=0.))
    except Exception as exc:
        return dict(passed=False,scope='online_measured_inputs_SONIC_record_only',hardware_ready=False,
                    robot_commands_sent=False,error=type(exc).__name__+': '+str(exc),worker_errors=errors,
                    reference_mode='IK_endpoint_hold' if joint_interpolation_s is None else 'causal_quintic_joint_reference_not_balance_plan',
                    joint_interpolation_s=joint_interpolation_s,
                    policy_records=actions,outputs=outputs,physical_stop_validated=False,
                    policy_timings=policy_timings,body_timings=body_timings,
                    coordinator_long_gaps=[dict(started_at=a,duration_s=b-a) for a,b in zip(control_times,control_times[1:]) if b-a>.022],
                    gc_long_pauses=[event for event in gc_events if event['duration_s']>.002])
    finally:
        # The optional downstream sink is still record-only. Closing it is NOT a
        # physical stop. Do this before waiting for GPU/input worker threads.
        sink_stop_error=None
        if body_sink is not None:
            try: body_sink.stop()
            except Exception as exc: sink_stop_error=exc
            finally:
                try: body_sink.close()
                except Exception as exc:
                    if sink_stop_error is None: sink_stop_error=exc
        stop.set(); mailbox.stop()
        gc.callbacks.remove(track_gc)
        # Each IO path has one owner; close only after its thread has stopped.
        if producer.ident: producer.join(4)
        if acquisition.ident: acquisition.join(4)
        body.close()
        if not acquisition.is_alive(): camera.close()
        if not producer.is_alive():
            actor.close(); ik.close()
        observer.close(); sonic.close()
        if producer.is_alive() or acquisition.is_alive(): raise RuntimeError('Input threads failed to stop within bounded IO timeouts')
        if sink_stop_error is not None: raise RuntimeError('Record-only body sink shutdown: '+str(sink_stop_error))
