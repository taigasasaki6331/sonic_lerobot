"""Lifecycle sequencing and local watchdog fixtures; no physics or hardware IO."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import BodyLifecycle, LifecycleFault, ACK_KIND, DEFAULT
from sonic_process import strict_message


def profile():
    return dict(names=['joint_'+str(i) for i in range(29)],defaults=[0.]*29,kp=[10.]*29,kd=[1.]*29,
                lower=[-2.]*29,upper=[2.]*29,velocity=[10.]*29)


def body(tick, q=0., dq=0.):
    # Deliberately unrelated remote clock: it must never be compared with caller now.
    return dict(q=[q]*29+[0.]*6,dq=[dq]*29+[0.]*6,gyroscope=[0.]*3,quaternion=[1.,0.,0.,0.],
                tick=tick,receive_monotonic_s=1e9+tick*.02,crc_verified=False)


class Tests(unittest.TestCase):
    def setUp(self):
        self.config = strict_message(DEFAULT.read_bytes())
        self.config.update(init_duration_s=.1,settle_duration_s=.04)
        self.c = BodyLifecycle('session',profile(),self.config)

    def owned(self, q=0., dq=0.):
        self.c.observe(body(0,q,dq),now=0.,source_age_s=0.)
        self.c.request_takeover(now=0.)
        self.c.confirm_takeover(session='session',kind=ACK_KIND,now=0.)

    def ready(self):
        self.owned(); self.c.begin_initialization(now=0.)
        # Only unit-test tensors are declared at the endpoint; no physics is modeled.
        for i in range(81):
            now=i*.002
            if i and i%10==0:
                self.c.observe(body(i//10),now=now,source_age_s=0.)
                self.c.refresh_ownership(session='session',kind=ACK_KIND,now=now)
            self.c.writer_tick(now=now)
        self.assertEqual(self.c.phase,'ready')

    def target(self, **updates):
        values=dict(session='session',seq=0,q=[.01]*29,now=.162,source_age_s=0.)
        values.update(updates); self.c.accept_target(**values)

    def test_full_diagnostic_lifecycle_and_no_physical_claim(self):
        self.ready(); self.target(); command=self.c.writer_tick(now=.162)
        self.assertEqual(command['schema'],'abstract_29_joint_record_NOT_Unitree_LowCmd')
        self.assertEqual(command['dq'],[0.]*29)
        self.c.request_stop(); self.c.acknowledge_stop(session='session',kind=ACK_KIND)
        self.c.confirm_return(session='session',kind=ACK_KIND)
        state=self.c.status(); self.assertEqual(state['phase'],'closed')
        for key in ('hardware_output_enabled','hardware_ready','robot_commands_sent','physical_ownership_confirmed',
                    'physical_stop_validated','physical_return_confirmed','stop_adapter_implemented'):
            self.assertIs(state[key],False)

    def test_construction_cannot_enable_hardware(self):
        for key,value in (('mode','hardware'),('hardware_output_enabled',True),('schema_version',True),('max_body_age_s',True)):
            bad=dict(self.config); bad[key]=value
            with self.assertRaises(ValueError): BodyLifecycle('session',profile(),bad)

    def test_no_implicit_takeover_or_initialization(self):
        self.assertEqual(len(self.c.events),0)
        self.c.observe(body(0),now=0.,source_age_s=0.)
        self.assertEqual(self.c.phase,'observing'); self.assertEqual(len(self.c.events),0)
        with self.assertRaises(LifecycleFault): self.c.begin_initialization(now=0.)
        self.assertEqual(self.c.reason,'operation_not_allowed_in_observing')

    def test_no_control_before_pose_confirmation(self):
        self.owned(); self.c.begin_initialization(now=0.)
        with self.assertRaises(LifecycleFault): self.target(now=0.)
        self.assertEqual(len(self.c.commands),0)

    def test_elapsed_initial_reference_is_not_pose_confirmation(self):
        self.owned(q=.2); self.c.begin_initialization(now=0.)
        for i in range(101):
            if i and i%10==0: self.c.observe(body(i//10,q=.2),now=i*.002,source_age_s=0.)
            self.c.writer_tick(now=i*.002)
        self.assertEqual(self.c.phase,'settling')
        self.assertIsNone(self.c.settle_since)

    def test_settle_dwell_resets_on_motion(self):
        self.ready(); self.c.phase='settling'; self.c.settle_since=.14
        self.c.observe(body(9,dq=.1),now=.18,source_age_s=0.)
        self.assertIsNone(self.c.settle_since)

    def test_tick_wrap_and_no_remote_clock_subtraction(self):
        self.c.observe(body(0xfffffffe),now=0.,source_age_s=0.)
        self.c.observe(body(0),now=.02,source_age_s=0.)
        self.assertEqual(self.c.body['tick'],0)

    def test_repeated_or_reversed_ticks_latch(self):
        for tick in (0,0xffffffff):
            self.setUp(); self.c.observe(body(0),now=0.,source_age_s=0.)
            with self.assertRaises(LifecycleFault): self.c.observe(body(tick),now=.02,source_age_s=0.)

    def test_fresh_packet_cannot_rearm_expired_local_watchdog(self):
        self.owned()
        with self.assertRaises(LifecycleFault): self.c.observe(body(1),now=.101,source_age_s=0.)
        with self.assertRaises(LifecycleFault): self.c.observe(body(2),now=.102,source_age_s=0.)
        self.assertEqual(self.c.reason,'body_watchdog_expired')

    def test_invalid_source_age_or_state(self):
        for frame,age in ((body(0),True),(body(0),-.1),(body(0),.101),({**body(0),'quaternion':[0.]*4},0.),
                          ({**body(0),'q':[float('nan')]*35},0.),(body(0,q=2.1),0.)):
            self.setUp()
            with self.assertRaises(LifecycleFault): self.c.observe(frame,now=0.,source_age_s=age)

    def test_takeover_and_ownership_timeout_are_independent(self):
        for field,reason in (('max_takeover_wait_s','takeover_ack_timeout'),('max_ownership_ack_age_s','ownership_ack_expired')):
            self.setUp(); self.c.config[field]=.01
            self.c.observe(body(0),now=0.,source_age_s=0.); self.c.request_takeover(now=0.)
            if field=='max_ownership_ack_age_s': self.c.confirm_takeover(session='session',kind=ACK_KIND,now=0.)
            with self.assertRaises(LifecycleFault): self.c.poll(.02)
            self.assertEqual(self.c.reason,reason)

    def test_bad_ack_session_or_physical_claim_rejected(self):
        for session,kind in (('other',ACK_KIND),('session','physical_verified'),('session',True)):
            self.setUp(); self.c.observe(body(0),now=0.,source_age_s=0.); self.c.request_takeover(now=0.)
            with self.assertRaises(LifecycleFault): self.c.confirm_takeover(session=session,kind=kind,now=0.)

    def test_initial_reference_extrema_velocity_rejected(self):
        self.c.profile['velocity']=[.01]*29; self.owned(q=.2)
        with self.assertRaises(LifecycleFault): self.c.begin_initialization(now=0.)
        self.assertEqual(len(self.c.commands),0)

    def test_target_identity_bounds_step_and_nan(self):
        for update,reason in ((dict(session='other'),'target_identity'),(dict(seq=True),'target_identity'),
            (dict(seq=1),'target_identity'),(dict(q=[2.1]*29),'target_outside_model_bounds'),
            (dict(q=[.051]*29),'target_step_exceeded'),(dict(q=[float('nan')]*29),'Invalid finite vector')):
            self.setUp(); self.ready()
            with self.assertRaises(LifecycleFault): self.target(**update)
            self.assertEqual(self.c.reason,reason)

    def test_late_command_rejected_by_local_tick_without_gpu_call(self):
        self.ready(); self.target()
        for i in range(1,6): self.c.observe(body(8+i),now=.16+i*.02,source_age_s=0.)
        with self.assertRaises(LifecycleFault): self.c.poll(.263)
        self.assertEqual(self.c.reason,'command_watchdog_expired')
        self.assertIsNone(self.c.target)

    def test_writer_gap_and_reversed_clock(self):
        for stamp,reason in ((.16,'writer_clock_not_increasing'),(.175,'writer_watchdog_expired'),(.1,'invalid_local_clock')):
            self.setUp(); self.ready()
            with self.assertRaises(LifecycleFault): self.c.writer_tick(now=stamp)
            self.assertEqual(self.c.reason,reason)

    def test_fast_target_steps_checked_against_model_velocity(self):
        self.ready(); self.target()
        with self.assertRaises(LifecycleFault): self.target(seq=1,q=[.029]*29,now=.163)
        self.assertEqual(self.c.reason,'target_reference_model_velocity')

    def test_new_sequence_cannot_share_previous_target_clock(self):
        self.ready(); self.target()
        with self.assertRaises(LifecycleFault): self.target(seq=1)
        self.assertEqual(self.c.reason,'target_clock_not_increasing')

    def test_operator_stop_does_not_wait_for_clock_or_gpu(self):
        self.ready(); self.target(); count=len(self.c.commands)
        self.c.request_stop()
        with self.assertRaises(LifecycleFault): self.c.writer_tick(now=float('nan'))
        self.assertEqual(len(self.c.commands),count)
        self.assertEqual(self.c.reason,'operator_stop')

    def test_return_requires_stop_ack_and_no_auto_restart(self):
        self.ready()
        with self.assertRaises(LifecycleFault): self.c.confirm_return(session='session',kind=ACK_KIND)
        self.c.acknowledge_stop(session='session',kind=ACK_KIND); self.c.confirm_return(session='session',kind=ACK_KIND)
        with self.assertRaises(LifecycleFault): self.c.request_takeover(now=.18)

    def test_caller_mutation_does_not_change_body_profile_or_records(self):
        p=profile(); self.c=BodyLifecycle('session',p,self.config); p['defaults'][0]=1.
        b=body(0); self.c.observe(b,now=0.,source_age_s=0.); b['q'][0]=1.
        self.c.request_takeover(now=0.); self.c.confirm_takeover(session='session',kind=ACK_KIND,now=0.)
        self.c.begin_initialization(now=0.); frame=self.c.writer_tick(now=0.); frame['q'][0]=1.
        self.assertEqual(self.c.profile['defaults'][0],0.); self.assertEqual(self.c.body['q'][0],0.)
        self.assertEqual(self.c.commands[0]['q'][0],0.)

    def test_pinned_profile_compiles_data_only(self):
        from body_lifecycle_profile import load_profile
        from sonic_observation import ObservationBuilder
        p=load_profile(); self.assertEqual(p['defaults'],ObservationBuilder().defaults.tolist())
        BodyLifecycle('session',p)

    def test_record_buffers_are_bounded_independent_of_total_ticks(self):
        self.owned(); self.c.begin_initialization(now=0.)
        for i in range(1000):
            if i and i%10==0:
                self.c.observe(body(i//10),now=i*.002,source_age_s=0.)
                self.c.refresh_ownership(session='session',kind=ACK_KIND,now=i*.002)
            self.c.writer_tick(now=i*.002)
        self.assertEqual(len(self.c.commands),256)
        self.assertEqual(self.c.status()['command_records'],1000)


if __name__=='__main__': unittest.main()
