"""SONIC/body boundary integration fixtures; no physics, devices or sockets."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import BodyLifecycle, DEFAULT, LifecycleFault
import check_body_lifecycle as fixtures
from check_body_lifecycle import profile, body
from sonic_body_bridge import SonicBodyBridge, BodyRecordWorker, BodyRecordClient, envelope
from sonic_process import strict_message
from record_session import RecordSession


def result(seq=0, q=.01):
    return dict(seq=seq,q_target_hardware=[q]*29,gripper_width_m=.04,gripper_actuated=False)


class Tests(unittest.TestCase):
    def setUp(self):
        self.config=strict_message(DEFAULT.read_bytes())
        self.c=BodyLifecycle('session',profile(),self.config); self.bridge=SonicBodyBridge(self.c)

    def message(self,seq=0,tick=0,value=None):
        return envelope('session',seq,body(tick),result(seq) if value is None else value,
                        source_age_s=.001,joint_names=self.c.profile['names'])

    def test_observational_delivery_never_takes_over(self):
        reply=self.bridge.consume(self.message(),now=0.)
        self.assertEqual(reply['decision'],'gated_initial_pose_not_ready')
        self.assertEqual(self.c.phase,'observing'); self.assertIsNone(self.c.target)
        self.assertEqual(len(self.c.events),0); self.assertEqual(len(self.c.commands),0)

    def test_fixture_ready_routes_exact_target_and_separate_width(self):
        fixture=fixtures.Tests(); fixture.setUp(); fixture.ready()
        self.c=fixture.c; self.bridge=SonicBodyBridge(self.c)
        value=result(); original=copy.deepcopy(value)
        reply=self.bridge.consume(self.message(tick=9,value=value),now=.18)
        self.assertEqual(reply['decision'],'accepted_abstract_target_NOT_sent')
        self.assertEqual(self.c.target,original['q_target_hardware'])
        self.assertEqual(self.c.control_seq,0)
        self.assertEqual(reply['gripper_width_m'],.04); self.assertFalse(reply['gripper_actuated'])
        value['q_target_hardware'][0]=1.; self.assertEqual(self.c.target[0],.01)

    def test_unsafe_value_logged_before_ready_but_rejected_when_ready(self):
        reply=self.bridge.consume(self.message(value=result(q=2.1)),now=0.)
        self.assertEqual(len(reply['target_limit_violations']),29)
        self.assertIsNone(self.c.target)
        fixture=fixtures.Tests(); fixture.setUp(); fixture.ready()
        self.c=fixture.c; self.bridge=SonicBodyBridge(self.c)
        with self.assertRaises(LifecycleFault): self.bridge.consume(self.message(tick=9,value=result(q=2.1)),now=.18)
        self.assertEqual(self.c.reason,'target_outside_model_bounds')

    def test_bad_contract_stops_and_cannot_rearm(self):
        for mutate in (
            lambda m:m.update(hardware_output_enabled=True),lambda m:m.update(seq=True),
            lambda m:m['joint_names'].reverse(),lambda m:m.update(source_body_tick=99),
            lambda m:m['sonic'].update(seq=1),lambda m:m['sonic'].update(gripper_actuated=True),
            lambda m:m['sonic'].update(hardware_ready=True),lambda m:m['sonic'].update(q_target_hardware=[float('nan')]*29),
            lambda m:m.update(source_age_s=.101)):
            self.setUp(); message=self.message(); mutate(message)
            with self.assertRaises((ValueError,LifecycleFault)): self.bridge.consume(message,now=0.)
            self.assertIsNone(self.c.target)
            with self.assertRaises(LifecycleFault): self.bridge.consume(self.message(),now=.02)

    def test_duplicate_or_reversed_sequence_stops(self):
        self.bridge.consume(self.message(),now=0.)
        with self.assertRaises(ValueError): self.bridge.consume(self.message(tick=1),now=.02)
        self.assertEqual(self.c.phase,'stop_required')

    def test_recordsession_handler_and_client_exchange(self):
        worker=BodyRecordWorker(profile(),self.config,lambda:0.)
        class Channel:
            closed=False
            def send(channel,value): channel.reply=worker.handle(value)
            def read(channel): return channel.reply
            def close(channel): channel.closed=True
        channel=Channel()
        transport=RecordSession(channel,'session',dict(max_source_age_s=.1,max_roundtrip_s=.1,max_tick_gap_s=.1),clock=lambda:0.)
        client=BodyRecordClient(transport,profile()['names']); client.start()
        reply=client.receive(0,body(0),result(),source_age_s=.001)
        self.assertEqual(reply['decision'],'gated_initial_pose_not_ready')
        client.stop(); self.assertTrue(channel.closed)
        self.assertEqual(worker.phase,'stopped'); self.assertEqual(worker.bridge.lifecycle.phase,'stop_required')
        self.assertFalse(worker.bridge.status()['physical_stop_validated'])

    def test_sender_validates_body_reply_even_if_transport_identity_matches(self):
        class Transport:
            gate=type('Gate',(),{'session':'session'})(); closed=False
            def query(self,*args): return dict(seq=0,source_body_tick=1,robot_commands_sent=False,
                hardware_ready=False,gripper_actuated=False,gripper_width_m=.04,decision='gated_initial_pose_not_ready')
            def close(self): self.closed=True
        transport=Transport(); client=BodyRecordClient(transport,profile()['names'])
        with self.assertRaises(ValueError): client.receive(0,body(0),result(),source_age_s=.001)
        self.assertTrue(transport.closed)


if __name__=='__main__': unittest.main()
