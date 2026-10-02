"""Offline tests using the actual pinned driver and a substituted serial port.

No device is opened and no physical/simulation controller is started.
"""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
from types import ModuleType
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_pika_gripper as control

REPORTED_JUMP_FRAME = json.dumps(dict(
    motor=dict(Speed=17.964, Current=-340, Position=1.7857),
    motorstatus=dict(Voltage=23.7, DriverTemp=44, MotorTemp=35, Status='0x40', BusCurrent=0))).encode()
CORRUPT_USER_FRAME = json.dumps(dict(
    motor=dict(Speed=2., Current=-1082348536, Position=2.),
    motorstatus=dict(Voltage=23.8, DriverTemp=38, MotorTemp=32, Status='0x40', BusCurrent=0))).encode()


class SerialDouble:
    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.enabled = False
        self.position = 0.
        self.speed = 0.
        self.packets = []
        self.obstructed = False
        self.reader = None

    def frame(self):
        return json.dumps(dict(motor=dict(Position=self.position, Speed=self.speed, Current=.1),
                               motorstatus=dict(Status='0x40' if self.enabled else '0x00'))).encode()

    def read(self, size):
        time.sleep(.005)
        return self.frame()

    def reset_input_buffer(self):
        pass

    def write(self, payload):
        self.packets.append(payload)
        code = payload[0]
        if code in (10, 11):
            self.enabled = code == 11
            if code == 10:
                self.speed = 0.
        elif code == 22 and not self.obstructed:
            self.position = struct.unpack('<f', payload[1:5])[0]
        return len(payload)

    def close(self):
        self.is_open = False


class TelemetryFramerTests(unittest.TestCase):
    FRAME = json.dumps(dict(motor=dict(Position=.5897, Speed=.024, Current=99),
                            motorstatus=dict(Status='0x40', Voltage=23.8))).encode()

    def test_every_split_and_bytewise_input_preserve_strings_and_escapes(self):
        data = json.loads(self.FRAME)
        data['note'] = 'brace } {, quote ", backslash \\, 日本語'
        frame = json.dumps(data, ensure_ascii=False).encode()
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                framer = control.TelemetryFramer()
                self.assertEqual(framer.feed(frame[:split]), [])
                self.assertEqual(framer.feed(frame[split:]), [frame])
                self.assertEqual(framer.resync_count, 0)
        framer = control.TelemetryFramer()
        result = []
        for byte in frame:
            result.extend(framer.feed(bytes([byte])))
        self.assertEqual(result, [frame])

    def test_missing_braces_and_truncated_string_recover_at_next_header(self):
        broken_frames = (self.FRAME[:-1], self.FRAME[:self.FRAME.index(b'"motorstatus"')],
                         b'{"motor":{"Position":"dropped string', b'partial telemetry }\r\n')
        for broken in broken_frames:
            for split in range(1, len(self.FRAME)):
                with self.subTest(broken=broken, split=split):
                    framer = control.TelemetryFramer()
                    result = framer.feed(broken + self.FRAME[:split])
                    result += framer.feed(self.FRAME[split:])
                    self.assertEqual(result, [self.FRAME])
                    self.assertGreater(framer.resync_count, 0)
                    self.assertEqual(framer.buffer, b'')

    def test_large_good_burst_is_parsed_before_buffer_limit(self):
        burst = (self.FRAME + b'\r\n') * 100
        self.assertGreater(len(burst), control.TelemetryFramer.MAX_BYTES)
        framer = control.TelemetryFramer()
        self.assertEqual(framer.feed(burst), [self.FRAME] * 100)
        self.assertEqual(framer.resync_count, 0)
        self.assertEqual(framer.buffer, b'')

    def test_oversized_partial_is_bounded_and_split_next_header_survives(self):
        framer = control.TelemetryFramer()
        broken = b'{"motor":{"Position":"' + b'x' * 9000
        for offset in range(0, len(broken), 256):
            self.assertEqual(framer.feed(broken[offset:offset + 256]), [])
            self.assertLessEqual(len(framer.buffer), framer.MAX_BYTES)
        self.assertEqual(framer.feed(b'x' * 5000 + self.FRAME[:8]), [])
        self.assertLessEqual(len(framer.buffer), framer.MAX_BYTES)
        self.assertEqual(framer.feed(self.FRAME[8:]), [self.FRAME])

    def test_nested_motor_key_does_not_split_valid_object(self):
        data = json.loads(self.FRAME)
        data['extra'] = dict(motor=dict(test='nested'))
        frame = json.dumps(data).encode()
        framer = control.TelemetryFramer()
        self.assertEqual(framer.feed(frame + self.FRAME), [frame, self.FRAME])
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                framer = control.TelemetryFramer()
                self.assertEqual(framer.feed(frame[:split]), [])
                self.assertEqual(framer.feed(frame[split:]), [frame])
                self.assertEqual(framer.resync_count, 0)

    def test_status_first_and_invalid_complete_json_keep_frame_boundaries(self):
        data = json.loads(self.FRAME)
        frame = json.dumps(dict(motorstatus=data['motorstatus'], motor=data['motor'])).encode()
        invalid = b'{"motor":{"Position":broken},"motorstatus":{"Status":"0x40"}}'
        framer = control.TelemetryFramer()
        self.assertEqual(framer.feed(invalid + frame), [invalid, frame])


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The transport alone is replaced. Parser, encoding, reader thread
        # and enable/disable/retry methods remain the pinned source.
        serial_module = ModuleType('serial')
        serial_module.__version__ = '3.5'
        serial_module.Serial = SerialDouble
        serial_module.SerialException = OSError
        with patch.dict(sys.modules, serial=serial_module):
            cls.module = control.load_driver(control.DEFAULT_DRIVER)

    def setUp(self):
        self.serial = SerialDouble()
        self.gripper = control.monitored_driver(self.module)('/not/a/device')
        self.fault_logs = tempfile.TemporaryDirectory(prefix='pika-control-test-')
        self.addCleanup(self.fault_logs.cleanup)

    def args(self, *argv):
        return control.parse_args([*argv, '--hold', '.01', '--timeout', '.03',
                                   '--fault-log-dir', self.fault_logs.name])

    def run_control(self, args):
        with patch.object(self.module.serial, 'Serial', return_value=self.serial), redirect_stdout(io.StringIO()):
            return control.run(self.gripper, args)

    def prime(self, enabled=False):
        self.serial.enabled = enabled
        self.gripper._serial = self.serial
        self.gripper._parse_frame(self.serial.frame())

    def test_preview_never_loads_driver_or_checks_port(self):
        with patch.object(control, 'load_driver', side_effect=AssertionError('must not import serial')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('must not access device')), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(control.main(['cycle', '--current-limit-a', '.2']), 0)

    def test_cycle_current_packet_and_cleanup(self):
        report = self.run_control(self.args('cycle', '--current-limit-a', '.2'))
        self.assertTrue(report['passed'], report)
        codes = [p[0] for p in self.serial.packets]
        self.assertEqual(codes[0], 15)  # Configure current before enabling.
        self.assertLess(codes.index(15), codes.index(11))
        self.assertEqual(self.serial.packets[0], b'\x0f' + struct.pack('<f', .2) + b'\r\n')
        self.assertTrue(set(codes) <= {10, 11, 15, 22})
        self.assertEqual([m['target_rad'] for m in report['moves']], [.6, 0.])
        self.assertEqual(codes[-1], 10)
        self.assertFalse(self.serial.is_open)
        self.assertFalse(self.gripper._reader_thread.is_alive())
        self.assertFalse(report['limit_readback_available'])

    def test_limit_only_does_not_enable_or_move(self):
        report = self.run_control(self.args('limit', '--current-limit-a', '.3'))
        self.assertTrue(report['passed'], report)
        self.assertEqual({p[0] for p in self.serial.packets}, {10, 15})

    def test_without_limit_never_sends_effort_command(self):
        report = self.run_control(self.args('close'))
        self.assertTrue(report['passed'], report)
        self.assertNotIn(15, [p[0] for p in self.serial.packets])

    def test_obstruction_is_failure_and_disables(self):
        self.serial.obstructed = True
        report = self.run_control(self.args('open'))
        self.assertFalse(report['passed'])
        self.assertIn('error', report)
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def test_interruption_does_not_send_position_and_closes(self):
        with patch.object(self.gripper, 'set_angle_and_wait', side_effect=KeyboardInterrupt):
            report = self.run_control(self.args('open'))
        self.assertFalse(report['passed'])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertNotIn(22, [p[0] for p in self.serial.packets])

    def test_stale_feedback_blocks_motion_but_allows_disable(self):
        self.prime(enabled=True)
        stamp, state = self.gripper.latest
        self.gripper.latest = (stamp - 1., state)
        with self.assertRaises(RuntimeError):
            self.gripper.set_angle(.3)
        with self.assertRaises(RuntimeError):
            control.set_current_limit(self.gripper, .2)
        self.assertEqual(self.serial.packets, [])
        self.gripper._send(10, 0.)
        self.assertEqual(self.serial.packets[-1][0], 10)

    def test_invalid_frame_cannot_refresh_feedback_or_clear_fault(self):
        self.prime(enabled=True)
        previous = self.gripper.latest
        for frame in (b'{broken', b'{"motor":{"Position":0.2}}'):
            self.gripper._parse_frame(frame)
            self.assertEqual(self.gripper.latest, previous)
        self.gripper._parse_frame(b'{"motor":{"Position":2.0},"motorstatus":{"Status":"0x40"}}')
        self.gripper._parse_frame(self.serial.frame())
        with self.assertRaises(RuntimeError):
            self.gripper.set_angle(.2)
        self.assertEqual(self.serial.packets, [])

    def test_grossly_corrupt_frame_never_updates_state_or_triggers_release(self):
        self.serial.position = .0904
        self.prime(enabled=True)
        previous = self.gripper.latest
        with patch.object(control.LOGGER, 'warning'):
            self.gripper._parse_frame(CORRUPT_USER_FRAME)
        self.assertEqual(self.gripper.latest, previous)
        self.assertIsNone(self.gripper.fault)
        self.assertEqual(self.serial.packets, [])
        self.assertAlmostEqual(self.gripper.fresh_state().position, .0904)
        self.gripper._parse_frame(self.serial.frame())
        self.gripper.set_angle(.09)
        self.assertEqual([p[0] for p in self.serial.packets], [22])
        diagnostics = self.gripper.rx_diagnostics()
        self.assertEqual(diagnostics['corrupt_frames'], 1)
        self.assertEqual(diagnostics['rejected_frames'], 1)
        self.assertEqual(diagnostics['corrupt_samples'][0]['raw_frame'], CORRUPT_USER_FRAME.decode())

    def test_repeated_corrupt_frames_cannot_extend_feedback_deadline(self):
        self.prime(enabled=True)
        stamp, state = self.gripper.latest
        with patch.object(control.LOGGER, 'warning'), patch.object(control.time, 'monotonic', return_value=stamp + .251):
            for _ in range(5):
                self.gripper._parse_frame(CORRUPT_USER_FRAME)
            self.assertEqual(self.gripper.latest, (stamp, state))
            with self.assertRaisesRegex(RuntimeError, '250ms'):
                self.gripper.set_angle(.2)
            self.assertEqual(self.serial.packets, [])
            self.gripper._send(10, 0.)
        self.assertEqual([p[0] for p in self.serial.packets], [10])

    def test_console_recovers_corrupt_frame_and_reports_integrity_separately(self):
        stages = 0
        def inject():
            nonlocal stages
            stages += 1
            if stages == 3:
                self.gripper._parse_frame(CORRUPT_USER_FRAME)
        with patch.object(control.LOGGER, 'warning'):
            report = self.run_console(['grip .2', 'grip 1.5', 'status', 'quit'], inject)
        self.assertTrue(report['completed'])
        self.assertTrue(report['passed'])  # Operation/cleanup, not transport integrity.
        self.assertFalse(report['telemetry_numeric_integrity_ok'])
        self.assertEqual(report['rx']['corrupt_frames'], 1)
        self.assertNotIn('fault_detail', report)
        self.assertEqual(report['last_operation_phase'], 'grip_hold')
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def test_corrupt_current_cannot_mask_driver_fault_or_clear_angle_fault(self):
        self.prime(enabled=True)
        data = json.loads(CORRUPT_USER_FRAME)
        data['motorstatus']['Status'] = '0x44'
        self.gripper._parse_frame(json.dumps(data).encode())
        self.assertEqual(self.gripper.fault_detail['field'], 'motorstatus.Status')
        self.assertEqual(self.gripper._corrupt_frames, 0)
        self.gripper = control.monitored_driver(self.module)('/not/a/device')
        self.prime(enabled=True)
        self.gripper._parse_frame(REPORTED_JUMP_FRAME)
        with patch.object(control.LOGGER, 'warning'):
            self.gripper._parse_frame(CORRUPT_USER_FRAME)
        self.gripper._parse_frame(self.serial.frame())
        with self.assertRaisesRegex(RuntimeError, '1.7857'):
            self.gripper.set_angle(.2)

    def test_recovered_complete_invalid_position_still_latches_fault_details(self):
        self.prime(enabled=True)
        invalid = b'{"motor":{"Position":-0.08},"motorstatus":{"Status":"0x40"}}'
        self.gripper._buf = self.serial.frame()[:-1] + invalid + self.serial.frame()
        with patch.object(control.LOGGER, 'warning') as warning:
            self.gripper._consume_buffer()
        self.assertEqual(warning.call_count, 1)
        self.assertEqual(self.gripper.fault_detail['value'], '-0.08')
        self.assertEqual(self.gripper.fault_detail['raw_frame'], invalid.decode())
        with self.assertRaisesRegex(RuntimeError, r'motor.Position=-0.08'):
            self.gripper.set_angle(.2)
        self.assertTrue(self.gripper.fresh_state(for_cleanup=True).enabled)
        self.assertEqual(self.serial.packets, [])

    def test_damaged_stream_recovers_during_console_and_warning_is_bounded(self):
        class DamagedSerial(SerialDouble):
            pending = b''

            def read(self, size):
                time.sleep(.005)
                if not self.pending:
                    self.pending = self.frame()[:-1] + self.frame() + b'\r\n'
                chunk, self.pending = self.pending[:size], self.pending[size:]
                return chunk

        self.serial = DamagedSerial()
        with patch.object(control.LOGGER, 'warning') as warning:
            report = self.run_console(['open .6', 'grip .5', 'current .3', 'open .4', 'stop', 'quit'])
        self.assertTrue(report['passed'], report)
        self.assertGreater(report['rx']['resync_count'], 10)
        self.assertGreater(report['rx']['valid_frames'], 10)
        self.assertEqual(report['rx']['rejected_frames'], 0)
        self.assertEqual(warning.call_count, 1)
        self.assertTrue(report['disable_confirmed'])
        self.assertFalse(self.gripper._reader_thread.is_alive())

    def test_fault_report_has_actual_value_and_cleanup_confirmation(self):
        def inject_fault():
            self.gripper._parse_frame(b'{"motor":{"Position":NaN},"motorstatus":{"Status":"0x00"}}')
        report = self.run_console(['open .6'], inject_fault)
        self.assertFalse(report['passed'])
        self.assertIn('motor.Position=nan', report['error'])
        self.assertEqual(report['fault_detail']['field'], 'motor.Position')
        self.assertEqual(report['fault_detail']['value'], 'nan')
        self.assertGreaterEqual(report['rx']['rejected_frames'], 1)
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertTrue(Path(report['fault_log']).is_file())
        json.dumps(report, allow_nan=False)

    def test_reported_jump_keeps_history_and_disables_without_speed_settle(self):
        stages = 0
        def jump_after_grip():
            nonlocal stages
            stages += 1
            if stages == 3:
                self.serial.speed = 17.964
                self.gripper._parse_frame(self.serial.frame())
                self.gripper._parse_frame(REPORTED_JUMP_FRAME)
        report = self.run_console(['open .6', 'grip 1.0', 'params'], jump_after_grip)
        self.assertFalse(report['passed'])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertEqual(report['fault_detail']['value'], '1.7857')
        self.assertAlmostEqual(report['fault_detail']['previous_position_rad'], .6, places=5)
        self.assertAlmostEqual(report['fault_detail']['last_position_target_rad'], .6, places=5)
        trace = json.loads(Path(report['fault_log']).read_text())
        self.assertTrue(trace['before_rx'])
        self.assertTrue(trace['before_tx'])
        self.assertLessEqual(len(trace['before_rx']), 256)
        self.assertLessEqual(len(trace['before_tx']), 64)
        first_disable = next(event for event in trace['after_tx'] if event['cmd'] == 10)
        self.assertLess(first_disable['t_s'] - trace['fault_time_s'], .2)
        self.assertTrue(all(event['cmd'] == 10 for event in trace['after_tx']))
        self.assertTrue(any(event['status'] == 0 for event in trace['after_rx'] if event['accepted']))
        self.assertEqual(trace['fault_detail']['value'], '1.7857')
        self.assertIsNotNone(self.gripper.fault)  # Good cleanup frames never clear it.

    def test_fault_log_failure_does_not_skip_disable_or_close(self):
        args = self.args('interactive')
        args.fault_log_dir = Path(self.fault_logs.name) / 'a-file'
        args.fault_log_dir.write_text('existing file')
        def reader(prompt, check):
            self.gripper._parse_frame(b'{"motor":{"Position":1.7857},"motorstatus":{"Status":"0x40"}}')
            check()
        with patch.object(self.module.serial, 'Serial', return_value=self.serial), redirect_stdout(io.StringIO()):
            report = control.run(self.gripper, args, reader)
        self.assertFalse(report['passed'])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertIn('fault_log_error', report)
        self.assertEqual(args.fault_log_dir.read_text(), 'existing file')

    def test_fault_first_seen_during_cleanup_cannot_pass_completed_operation(self):
        original_write = self.serial.write
        injected = False
        def fault_on_disable(payload):
            nonlocal injected
            result = original_write(payload)
            if payload[0] == 10 and not injected:
                injected = True
                self.gripper._parse_frame(json.dumps(dict(
                    motor=dict(Position=-2., Speed=0., Current=-500),
                    motorstatus=dict(Status='0x40'))).encode())
            return result
        self.serial.write = fault_on_disable
        report = self.run_control(self.args('open'))
        self.assertTrue(report['completed'])
        self.assertFalse(report['passed'])
        self.assertEqual(report['fault_detail']['phase'], 'cleanup')
        self.assertIn('motor.Position=-2.0', report['error'])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def test_disabled_feedback_blocks_position(self):
        self.prime()
        with self.assertRaises(RuntimeError):
            self.gripper.set_angle(.3)
        self.assertEqual(self.serial.packets, [])

    def test_fault_during_send_lock_wait_blocks_queued_position(self):
        self.prime(enabled=True)
        requested = threading.Event()
        failures = []
        original_record = self.gripper.record
        def record(kind, **fields):
            original_record(kind, **fields)
            if kind == 'tx_request':
                requested.set()
        self.gripper.record = record
        def queued_send():
            try:
                self.gripper.set_angle(.3)
            except Exception as exc:
                failures.append(exc)
        with self.gripper._serial_lock:
            worker = threading.Thread(target=queued_send)
            worker.start()
            self.assertTrue(requested.wait(timeout=1.))
            self.gripper._parse_frame(REPORTED_JUMP_FRAME)
        worker.join(timeout=1.)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIn('1.7857', str(failures[0]))
        self.assertEqual(self.serial.packets, [])

    def test_diagnostic_separates_current_change_from_closure_and_records(self):
        args = self.args('diagnose', '--angle', '.05', '--current-limit-a', '1', '--grip-speed', '2')
        report = self.run_control(args)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['diagnostic_result'], 'no_abort_in_this_run')
        events = [json.loads(line) for line in (Path(report['session_log']) / 'events.jsonl').read_text().splitlines()]
        self.assertEqual([e['seq'] for e in events], list(range(len(events))))
        phases = [e['phase'] for e in events if e['kind'] == 'phase']
        self.assertEqual(phases, ['baseline_current', 'baseline_open', 'baseline_hold',
                                  'current_change_hold', 'close_ramp', 'closed_hold', 'cleanup'])
        currents = [e for e in events if e['kind'] == 'tx_written' and e['cmd'] == 15]
        self.assertEqual([(e['phase'], e['values']) for e in currents],
                         [('baseline_current', [.2]), ('current_change_hold', [1.])])
        self.assertFalse(any(e['kind'] == 'tx_written' and e['cmd'] == 22
                             and e['phase'] == 'current_change_hold' for e in events))
        raw = (Path(report['session_log']) / 'raw.bin').read_bytes()
        reads = [e for e in events if e['kind'] == 'rx_bytes']
        self.assertEqual(sum(e['size'] for e in reads), len(raw))
        self.assertTrue(len(raw) > 0)
        self.assertEqual(events[-1]['kind'], 'session_end')

    def test_diagnostic_current_only_excursion_aborts_before_closing(self):
        original_write = self.serial.write
        def current_causes_excursion(payload):
            count = original_write(payload)
            if payload[0] == 15 and struct.unpack('<f', payload[1:5])[0] == 1.:
                # A deliberately faulty transport fixture, not a motor model.
                # Still inside the general receive range: diagnostic guard
                # must latch the unexpected movement while target is fixed.
                self.serial.position = .3
                self.gripper._parse_frame(self.serial.frame())
            return count
        self.serial.write = current_causes_excursion
        report = self.run_control(self.args('diagnose', '--angle', '.05', '--current-limit-a', '1', '--grip-speed', '2'))
        self.assertFalse(report['passed'])
        self.assertEqual(report['fault_detail']['phase'], 'current_change_hold')
        self.assertEqual(report['last_operation_phase'], 'current_change_hold')
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        events = [json.loads(line) for line in (Path(report['session_log']) / 'events.jsonl').read_text().splitlines()]
        self.assertFalse(any(e['kind'] == 'phase' and e['phase'] == 'close_ramp' for e in events))
        self.assertTrue(any(e['kind'] == 'rx_rejected' and e['value'] == '0.3' for e in events))

    def test_record_failure_aborts_commands_but_still_disables(self):
        args = self.args('interactive')
        args.record_dir = Path(self.fault_logs.name)
        def reader(prompt, check):
            self.gripper.recorder.error = 'disk full'
            check()
            return 'open .6'
        with patch.object(self.module.serial, 'Serial', return_value=self.serial), redirect_stdout(io.StringIO()):
            report = control.run(self.gripper, args, reader)
        self.assertFalse(report['passed'])
        self.assertIn('disk full', report['error'])
        self.assertEqual(report['session_log_error'], 'disk full')
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertEqual({p[0] for p in self.serial.packets}, {10})

    def test_diagnostic_parameters_cannot_make_unbounded_trial(self):
        for argv in ([], ['--current-limit-a', '1', '--grip-speed', '.001'],
                     ['--current-limit-a', '1', '--hold', '6'],
                     ['--current-limit-a', '1', '--timeout', '11'],
                     ['--current-limit-a', '1', '--diagnostic-baseline-a', '1.1'],
                     ['--current-limit-a', '1', '--diagnostic-baseline-a', '3']):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                control.parse_args(['diagnose', *argv])

    def test_driver_error_bits_latch_but_enable_and_homed_bits_do_not(self):
        for status in ('0x40', '0x80', '0xc0'):
            with self.subTest(status=status):
                frame = json.loads(self.serial.frame())
                frame['motorstatus']['Status'] = status
                self.gripper._parse_frame(json.dumps(frame).encode())
                self.assertIsNone(self.gripper.fault)
        for bit in (1, 2, 4, 8, 16, 32):
            with self.subTest(bit=bit):
                gripper = control.monitored_driver(self.module)('/not/a/device')
                frame['motorstatus']['Status'] = hex(64 | bit)
                gripper._parse_frame(json.dumps(frame).encode())
                self.assertIsNotNone(gripper.fault)
                self.assertEqual(gripper.fault_detail['field'], 'motorstatus.Status')
                gripper.set_phase('cleanup')
                frame['motorstatus']['Status'] = hex(bit)
                gripper._parse_frame(json.dumps(frame).encode())
                self.assertFalse(gripper.fresh_state(for_cleanup=True).enabled)
                self.assertIsNotNone(gripper.fault)

    def test_torque_requires_constant_and_converts_to_current(self):
        args = self.args('limit', '--torque-limit-nm', '.04', '--torque-constant-nm-per-a', '.2')
        self.assertAlmostEqual(args.current_limit_a, .2)  # Arbitrary test constant, not PIKA calibration.
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args('limit', '--torque-limit-nm', '.04')

    def test_invalid_limits_rejected_before_any_device_access(self):
        for value in ('0', '-1', 'nan', 'inf', '2.0001', '3', '1e100', '1e-100'):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.args('open', '--current-limit-a', value)
        for value in (0, -1, 2.0001, 3, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.set_current_limit(self.gripper, value)
        self.assertEqual(self.serial.packets, [])

    def test_failed_disable_not_reported_as_success(self):
        # A fresh enabled frame after DISABLE must produce a failed report.
        original_write = self.serial.write
        def keep_enabled(payload):
            result = original_write(payload)
            if payload[0] == 10:
                self.serial.enabled = True
            return result
        self.serial.write = keep_enabled
        with patch.object(self.gripper, 'disable', side_effect=TimeoutError('no disable ACK')):
            report = self.run_control(self.args('close'))
        self.assertFalse(report['passed'])
        self.assertFalse(report['disable_confirmed'])
        self.assertIn('disable_error', report)
        self.assertTrue(report['port_closed'])

    def test_old_disabled_state_cannot_confirm_disable(self):
        self.prime()
        with patch.object(self.gripper, 'connect'), patch.object(self.gripper, 'wait_for_state'), \
             redirect_stdout(io.StringIO()):
            report = control.run(self.gripper, self.args('limit', '--current-limit-a', '.2'))
        self.assertFalse(report['passed'])
        self.assertFalse(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def run_console(self, commands, before_command=None):
        lines = iter(commands)
        def read(prompt, check):
            if before_command is not None:
                before_command()
            check()
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        with patch.object(self.module.serial, 'Serial', return_value=self.serial), redirect_stdout(io.StringIO()):
            return control.run(self.gripper, self.args('interactive'), read)

    def test_console_reuses_one_connection_and_keeps_enabled_between_moves(self):
        stages = []
        def stage():
            stages.append((self.serial.enabled, self.serial.is_open))
        with patch.object(self.gripper, 'connect', wraps=self.gripper.connect) as connect:
            report = self.run_console(['current .2', 'open .6', 'current .3', 'move .25', 'close', 'quit'], stage)
        self.assertTrue(report['passed'], report)
        connect.assert_called_once()
        self.assertTrue(all(opened for _, opened in stages))
        self.assertEqual([enabled for enabled, _ in stages], [False, False, True, True, True, True])
        self.assertEqual([m['target_rad'] for m in report['moves']], [.6, .25, 0.])
        self.assertEqual(report['move_count'], 3)
        currents = [struct.unpack('<f', p[1:5])[0] for p in self.serial.packets if p[0] == 15]
        self.assertAlmostEqual(currents[0], .2)
        self.assertAlmostEqual(currents[1], .3)
        self.assertEqual(len(currents), 2)
        self.assertFalse(self.gripper._reader_thread.is_alive())

    def test_console_invalid_input_recovers_without_writes(self):
        report = self.run_console(['move nan', 'open 2', 'current -1', 'current 1e100',
                                   'current 1e-100', 'torque .04', 'set timeout 0', 'set hold 61',
                                   'enable extra', 'open "', 'unknown', 'quit'])
        self.assertTrue(report['passed'], report)
        self.assertEqual({p[0] for p in self.serial.packets}, {10})

    def test_two_amp_boundary_and_torque_conversion_limit(self):
        self.assertEqual(self.args('limit', '--current-limit-a', '2').current_limit_a, 2.)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args('limit', '--torque-limit-nm', '.3', '--torque-constant-nm-per-a', '.1')
        self.prime()
        console = control.GripperConsole(self.gripper, self.args('interactive'),
                                          dict(limit_command_sent=False))
        with redirect_stdout(io.StringIO()):
            console.command('kt .1')  # Arbitrary test value, not a measured PIKA constant.
        for line in ('current 2.0001', 'torque .3'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                console.command(line)
        self.assertEqual(self.serial.packets, [])
        self.assertIsNone(console.current_a)
        with redirect_stdout(io.StringIO()):
            console.command('current 2')
        self.assertEqual(self.serial.packets[-1], b'\x0f' + struct.pack('<f', 2.) + b'\r\n')

    def test_console_settings_torque_cycle_and_disable_resume(self):
        report = self.run_console(['set angle .4', 'set hold 0', 'set timeout .3',
                                   'kt .2', 'torque .04', 'cycle', 'disable', 'open', 'stop', 'quit'])
        self.assertTrue(report['passed'], report)
        self.assertEqual([m['target_rad'] for m in report['moves']], [.4, 0., .4])
        self.assertEqual([p[0] for p in self.serial.packets].count(11), 2)
        self.assertAlmostEqual(report['current_limit_a'], .2)
        self.assertEqual(report['console_parameters']['cycle_hold_s'], 0.)
        self.assertEqual(report['console_parameters']['open_angle_rad'], .4)

    def test_console_eof_closes_and_disables(self):
        report = self.run_console(['open .2'])
        self.assertTrue(report['passed'], report)
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def test_console_interruption_while_waiting_disables(self):
        stages = 0
        def interrupt():
            nonlocal stages
            stages += 1
            if stages == 2:
                raise KeyboardInterrupt
        report = self.run_console(['open .2', 'close'], interrupt)
        self.assertFalse(report['passed'])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertEqual([m['target_rad'] for m in report['moves']], [.2])

    def test_console_idle_stale_state_exits_without_another_position_command(self):
        stages = 0
        def lose_feedback():
            nonlocal stages
            stages += 1
            if stages == 2:
                self.gripper._shutdown_event.set()
                self.gripper._reader_thread.join(timeout=1.)
                stamp, state = self.gripper.latest
                self.gripper.latest = (stamp - 1., state)
        report = self.run_console(['open .2', 'close'], lose_feedback)
        self.assertFalse(report['passed'])
        self.assertIn('古い', report['error'])
        self.assertEqual([m['target_rad'] for m in report['moves']], [.2])
        self.assertFalse(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])
        self.assertEqual(self.serial.packets[-1][0], 10)

    def test_console_preview_never_imports_serial_and_accepts_live_parameters(self):
        lines = iter(['current .2', 'set angle .4', 'open', 'move .1', 'close', 'status', 'params', 'quit'])
        def reader(self_reader, prompt, check):
            check()
            return next(lines)
        output = io.StringIO()
        with patch.object(control.ConsoleInput, 'read', reader), \
             patch.object(control, 'load_driver', side_effect=AssertionError('must not import serial')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('must not check devices')), \
             redirect_stdout(output):
            self.assertEqual(control.main(['interactive', '--port', '/not/a/device']), 0)
        self.assertIn('未接続', output.getvalue())
        self.assertIn('目標 0.400 rad', output.getvalue())
        self.assertIn('"hardware_execution": false', output.getvalue())

    def test_console_input_paste_and_eof(self):
        rfd, wfd = os.pipe()
        os.write(wfd, b'params\nopen .3\nquit')
        os.close(wfd)
        with os.fdopen(rfd, encoding='utf-8') as stream, redirect_stdout(io.StringIO()):
            reader = control.ConsoleInput(stream)
            self.assertEqual(reader.read('', lambda: None), 'params')
            self.assertEqual(reader.read('', lambda: None), 'open .3')
            self.assertEqual(reader.read('', lambda: None), 'quit')
            with self.assertRaises(EOFError):
                reader.read('', lambda: None)

    def test_console_input_checks_health_while_no_line_is_entered(self):
        rfd, wfd = os.pipe()
        calls = 0
        def failed_check():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError('feedback expired')
        try:
            with os.fdopen(rfd, encoding='utf-8') as stream, redirect_stdout(io.StringIO()):
                started = time.monotonic()
                with self.assertRaisesRegex(RuntimeError, 'feedback expired'):
                    control.ConsoleInput(stream).read('', failed_check)
                self.assertLess(time.monotonic() - started, .5)
        finally:
            os.close(wfd)

    def test_grip_contact_returns_to_input_and_can_adjust_then_open(self):
        self.serial.position = .35
        self.serial.obstructed = True
        stages = 0
        def release_for_open():
            nonlocal stages
            stages += 1
            if stages == 5:
                self.serial.obstructed = False
        report = self.run_console(['grip .2', 'current .3', 'status', 'params', 'open .6', 'quit'],
                                  release_for_open)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['grip_count'], 1)
        self.assertEqual([m['target_rad'] for m in report['moves']], [.6])
        self.assertTrue(report['disable_confirmed'])
        self.assertTrue(report['port_closed'])

    def test_grip_resends_while_idle_and_stop_cancels(self):
        self.serial.position = .35
        self.prime(enabled=True)
        self.serial.obstructed = True
        console = control.GripperConsole(self.gripper, self.args('interactive'),
                                          dict(limit_command_sent=False, moves=[], move_count=0))
        with redirect_stdout(io.StringIO()):
            console.command('grip .2')
        self.assertTrue(console.grip_active)
        self.assertEqual([p[0] for p in self.serial.packets], [15, 22])
        console.last_grip_sent = 0.
        console.check()
        self.assertEqual([p[0] for p in self.serial.packets], [15, 22, 22])
        # Cancel the grip flag before disable, then new checks cannot re-close.
        with patch.object(control, 'disable_and_confirm'), redirect_stdout(io.StringIO()):
            console.command('stop')
        self.assertFalse(console.grip_active)
        count = len(self.serial.packets)
        console.last_grip_sent = 0.
        console.check()
        self.assertEqual(len(self.serial.packets), count)

    def test_closed_grip_holds_without_resending_or_retargeting_on_current_change(self):
        self.serial.position = .09  # Object prevents reaching the closed angle.
        self.serial.obstructed = True
        self.prime(enabled=True)
        console = control.GripperConsole(self.gripper, self.args('interactive'), dict(limit_command_sent=False))
        with redirect_stdout(io.StringIO()):
            console.command('grip .2')
        console.grip_target = .001
        console.last_grip_sent = 0.
        console.check()
        self.assertEqual(struct.unpack('<f', self.serial.packets[-1][1:5])[0], 0.)
        self.assertEqual(self.gripper.phase, 'grip_hold')
        count = len(self.serial.packets)
        for _ in range(5):
            console.last_grip_sent = 0.
            console.check()
        self.assertEqual(len(self.serial.packets), count)
        with redirect_stdout(io.StringIO()):
            console.command('grip 1.5')
        self.assertEqual([p[0] for p in self.serial.packets[count:]], [15])
        self.assertEqual(console.grip_target, 0.)
        self.assertTrue(console.grip_active)
        self.assertEqual(self.gripper.last_position_target, 0.)
        self.assertEqual(self.gripper.phase, 'grip_hold')
        # Health monitoring stays active despite the absence of position writes.
        stamp, state = self.gripper.latest
        with patch.object(control.time, 'monotonic', return_value=stamp + .251):
            with self.assertRaisesRegex(RuntimeError, '250ms'):
                console.check()

    def test_current_change_during_grip_keeps_ramp_target_and_clock(self):
        self.serial.position = .6
        self.serial.obstructed = True
        self.prime(enabled=True)
        console = control.GripperConsole(self.gripper, self.args('interactive'), dict(limit_command_sent=False))
        with redirect_stdout(io.StringIO()):
            console.command('grip .2')
        console.grip_target = .4
        previous_clock = console.last_grip_sent
        count = len(self.serial.packets)
        with redirect_stdout(io.StringIO()):
            console.command('grip 1.8')
        self.assertEqual([p[0] for p in self.serial.packets[count:]], [15])
        self.assertEqual(console.grip_target, .4)
        self.assertEqual(console.last_grip_sent, previous_clock)

    def test_grip_starts_at_measured_angle_and_caps_each_step_even_after_delay(self):
        self.serial.position = .6
        self.prime(enabled=True)
        console = control.GripperConsole(self.gripper, self.args('interactive'), dict(limit_command_sent=False))
        with redirect_stdout(io.StringIO()):
            console.command('grip .2')
        self.assertAlmostEqual(struct.unpack('<f', self.serial.packets[-1][1:5])[0], .6)
        now = console.last_grip_sent + .06
        for elapsed in (.06, 10., .06):
            now += elapsed
            previous = console.grip_target
            with patch.object(control.time, 'monotonic', return_value=now):
                self.gripper._parse_frame(self.serial.frame())
                console.check()
            target = struct.unpack('<f', self.serial.packets[-1][1:5])[0]
            self.assertAlmostEqual(target, previous - .5 * control.GRIP_PERIOD, places=6)
            self.assertLess(target, previous)
            self.assertGreaterEqual(target, 0.)
        # Reaching zero does not reverse direction or terminate input waiting.
        console.grip_target = .001
        now += .06
        with patch.object(control.time, 'monotonic', return_value=now):
            self.gripper._parse_frame(self.serial.frame())
            console.check()
        self.assertEqual(struct.unpack('<f', self.serial.packets[-1][1:5])[0], 0.)
        self.assertTrue(console.grip_active)

    def test_grip_speed_setting_is_validated_without_sending(self):
        self.prime(enabled=True)
        console = control.GripperConsole(self.gripper, self.args('interactive'), dict(limit_command_sent=False))
        with redirect_stdout(io.StringIO()):
            console.command('set grip-speed .2')
        self.assertEqual(console.grip_speed, .2)
        for value in ('0', '-1', 'nan', 'inf', '2.01'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                console.command(f'set grip-speed {value}')
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.args('interactive', '--grip-speed', value)
        self.assertEqual(console.grip_speed, .2)
        self.assertEqual(self.serial.packets, [])

    def test_invalid_grip_does_not_send_or_enable(self):
        self.prime()
        console = control.GripperConsole(self.gripper, self.args('interactive'),
                                          dict(limit_command_sent=False))
        for line in ('grip', 'grip 0', 'grip -1', 'grip nan', 'grip 2.01', 'grip .2 extra'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                console.command(line)
        self.assertFalse(console.grip_active)
        self.assertEqual(self.serial.packets, [])


if __name__ == '__main__':
    unittest.main()
