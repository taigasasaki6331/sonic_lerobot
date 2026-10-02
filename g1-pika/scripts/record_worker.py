"""Protocol handler for saved SONIC results. No sockets or actuator imports.

This worker REPLAYS files; it does not run live inference. It validates identity
and returns file results only. A caller owns the bounded ZMQ channel lifetime.
"""
import math


class RecordWorker:
    def __init__(self, request, result):
        if result.get('hardware_ready') is not False or result.get('robot_commands_sent') is not False:
            raise ValueError('Not a record-only SONIC result')
        if request['source_sha256'] != result['source_sha256']:
            raise ValueError('Source mismatch')
        self.rows=result['outputs']
        if len(self.rows)!=len(request['frames']) or not self.rows: raise ValueError('Result count mismatch')
        for before,after in zip(request['frames'],self.rows):
            if before['seq']!=after['seq']: raise ValueError('Result sequence mismatch')
            q=after['q_target_hardware']
            if len(q)!=29 or not all(type(v) in (int,float) and math.isfinite(v) for v in q):
                raise ValueError('Invalid joint output')
            if 'gripper_width_m' in before:
                width=before['gripper_width_m']
                if type(width) not in (int,float) or not math.isfinite(width) or not 0<=width<=.1:
                    raise ValueError('Invalid width value')
                if after.get('gripper_actuated') is not False or before['gripper_width_m']!=after.get('gripper_width_m'):
                    raise ValueError('Invalid width side-channel')
        self.session=None; self.next=0; self.phase='idle'

    def handle(self, message):
        if self.phase=='idle':
            if (message.get('op')!='hello' or message.get('schema')!=1 or message.get('mode')!='record_only'
                    or not isinstance(message.get('session'),str) or not message['session']):
                self.phase='fault'; raise ValueError('Invalid hello')
            self.session=message['session']; self.phase='running'
            return dict(ready=True,session=self.session,schema=1,mode='record_only',hardware_output_enabled=False)
        if self.phase!='running' or message.get('session')!=self.session:
            self.phase='fault'; raise ValueError('Worker session/phase mismatch')
        if message.get('op')=='stop':
            self.phase='stopped'; return dict(stopped=True,session=self.session)
        if (message.get('op')!='record' or type(message.get('seq')) is not int
                or message['seq']!=self.next or self.next>=len(self.rows)):
            self.phase='fault'; raise ValueError('Worker request sequence')
        row=self.rows[self.next]
        # Transport sequence is consecutive; original capture sequence remains inside result.
        response=dict(session=self.session,seq=self.next,result=row,hardware_output_enabled=False,
                      source='saved_SONIC_output_not_live_inference')
        self.next+=1
        return response
