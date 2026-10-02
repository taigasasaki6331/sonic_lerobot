#!/usr/bin/env python3
"""PIKA standalone open/close and current (torque) limit control.

Without --execute this prints a plan without importing serial or opening a port.
Uses the unchanged pinned LeRobot driver, not the G1/SONIC robot controller.
"""
import argparse
from collections import deque
from dataclasses import asdict
import hashlib
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import re
import select
import shlex
import signal
import stat
import struct
import sys
import tempfile
import threading
import time

DRIVER_SHA256 = 'ef7c397ec33ada894fb164bea633b560e178b7fa1778e5bf89eeb1001be8e63e'
DEFAULT_DRIVER = Path(__file__).resolve().parents[1] / 'assets/pika/gripper/pika_gripper.py'
RIGHT_PORT = '/dev/pika/right/gripper'
RIGHT_DEVICE = '/dev/serial/by-path/platform-3610000.usb-usb-0:2.1.4.4.4:1.0-port0'
MAX_ANGLE = 1.67
MAX_CURRENT_A = 2.0  # CLI cap; SDK code says 0..2 A, API_Doc says typical 0..8 A.
STATE_MAX_AGE = .25
GRIP_PERIOD = .05
# A gross corruption check, not a motor rating or permitted current. SDK
# telemetry is in mA; billion-valued integers also occur with no host writes.
CORRUPT_CURRENT_MA = 1_000_000
DEFAULT_FAULT_LOG_DIR = Path(__file__).resolve().parents[1] / 'artifacts/gripper-control'
LOGGER = logging.getLogger('pika_gripper_control')
DIAGNOSTIC_EXCURSION = .1  # Experiment abort rule, not a manufacturer motion limit.


class SessionRecorder:
    """Complete host-side journal; a write is not a firmware ACK.

    Capture raw read chunks before framing, including discarded/broken JSON.
    File errors latch and abort subsequent control, while cleanup stays usable.
    """
    def __init__(self, directory, start):
        directory.mkdir(parents=True, exist_ok=True)
        self.output = Path(tempfile.mkdtemp(prefix='session-', dir=directory))
        self.start = start
        self.lock = threading.Lock()
        self.error = None
        self.seq = 0
        self.offset = 0
        self.events = (self.output / 'events.jsonl').open('w', encoding='utf-8')
        try:
            self.raw = (self.output / 'raw.bin').open('wb')
        except BaseException:
            self.events.close()
            raise

    def record(self, kind, *, chunk=None, **fields):
        with self.lock:
            if self.error is not None:
                return
            try:
                event = dict(seq=self.seq, t_s=time.monotonic() - self.start, kind=kind, **fields)
                if chunk is not None:
                    event.update(offset=self.offset, size=len(chunk))
                    self.raw.write(chunk)
                    self.offset += len(chunk)
                    self.raw.flush()
                self.events.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
                self.events.flush()
                self.seq += 1
            except Exception as exc:
                self.error = str(exc)

    def close(self):
        with self.lock:
            for stream in (self.raw, self.events):
                try:
                    stream.close()
                except Exception as exc:
                    self.error = self.error or str(exc)


class TelemetryFramer:
    """Recover streamed PIKA JSON after a partial read or input-buffer flush.

    The firmware's outer objects begin with motor or motorstatus. A new such
    header lets us discard a truncated preceding object without waiting for
    4 KiB of otherwise valid telemetry to accumulate. Strings/escapes must not
    contribute braces. Keep this adapter separate from the pinned driver.
    """
    HEADER = re.compile(rb'\{\s*"(?:motor|motorstatus)"\s*:\s*\{')
    MAX_BYTES = 4096

    def __init__(self):
        self.buffer = b''
        self.resync_count = 0
        self.discarded_bytes = 0

    @staticmethod
    def object_end(data):
        depth, in_string, escaped = 0, False, False
        for index, byte in enumerate(data):
            if in_string:
                if escaped:
                    escaped = False
                elif byte == 92:  # backslash
                    escaped = True
                elif byte == 34:  # quote
                    in_string = False
            elif byte == 34:
                in_string = True
            elif byte == 123:
                depth += 1
            elif byte == 125:
                depth -= 1
                if depth == 0:
                    return index
        return None

    def discard(self, count):
        discarded, self.buffer = self.buffer[:count], self.buffer[count:]
        if discarded.strip():  # Ordinary CR/LF between frames isn't damage.
            self.resync_count += 1
            self.discarded_bytes += len(discarded)

    def bound_partial(self):
        if len(self.buffer) > self.MAX_BYTES:
            # Preserve a possibly split next header, but never an oversized
            # partial object. The next complete header remains recoverable.
            last_open = self.buffer.rfind(b'{')
            if last_open > 0 and len(self.buffer) - last_open <= self.MAX_BYTES:
                self.discard(last_open)
            else:
                self.discard(len(self.buffer))

    @staticmethod
    def is_telemetry_object(frame):
        try:
            data = json.loads(frame)
            return (isinstance(data, dict) and isinstance(data.get('motor'), dict)
                    and 'Position' in data['motor'] and isinstance(data.get('motorstatus'), dict)
                    and 'Status' in data['motorstatus'])
        except ValueError:
            return False

    def feed(self, chunk):
        self.buffer += chunk
        frames = []
        while self.buffer:
            header = self.HEADER.search(self.buffer)
            if header is None:
                last_open = self.buffer.rfind(b'{')
                if last_open < 0:
                    self.discard(len(self.buffer))
                elif last_open > 0:
                    self.discard(last_open)
                self.bound_partial()
                break
            if header.start():
                self.discard(header.start())
                header = self.HEADER.match(self.buffer)
            end = self.object_end(self.buffer)
            next_header = self.HEADER.search(self.buffer, header.end())
            if next_header is not None and (end is None or next_header.start() < end):
                # A valid nested object could also contain this key. Prefer
                # a complete valid object; resync only a broken predecessor.
                complete = False
                if end is not None:
                    try:
                        json.loads(self.buffer[:end + 1])
                        complete = True
                    except ValueError:
                        pass
                if not complete:
                    recovered = False
                    while next_header is not None:
                        candidate = self.buffer[next_header.start():]
                        candidate_end = self.object_end(candidate)
                        if (candidate_end is not None
                                and self.is_telemetry_object(candidate[:candidate_end + 1])):
                            self.discard(next_header.start())
                            recovered = True
                            break
                        next_header = self.HEADER.search(self.buffer, next_header.end())
                    if recovered:
                        continue
            if end is None:
                self.bound_partial()
                break
            if end + 1 > self.MAX_BYTES:
                self.discard(end + 1)
                continue
            frames.append(self.buffer[:end + 1])
            self.buffer = self.buffer[end + 1:]
        return frames


def positive_float(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('有限の正数を指定してください')
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['open', 'close', 'cycle', 'limit', 'interactive', 'diagnose'])
    parser.add_argument('--port', default=RIGHT_PORT,
                        help='接続PC上のシリアルポート。既定はG1搭載PC用。tigerでは例: /dev/ttyUSB0')
    parser.add_argument('--driver', type=Path, default=DEFAULT_DRIVER)
    parser.add_argument('--angle', type=positive_float, default=.6, help='開く角度 rad (0 < angle <= 1.67)')
    parser.add_argument('--hold', type=positive_float, default=1., help='到達後の待機秒数 (最大60)')
    parser.add_argument('--timeout', type=positive_float, default=3., help='各目標の到達期限 秒 (最大30)')
    parser.add_argument('--grip-speed', type=positive_float, default=.5,
                        help='gripの閉じ目標の変化率 rad/s (0 < 値 <= 2、既定0.5)。実測速度の制限ではない')
    parser.add_argument('--fault-log-dir', type=Path, default=DEFAULT_FAULT_LOG_DIR,
                        help='異常時の受信/送信履歴の保存先')
    parser.add_argument('--record-dir', type=Path,
                        help='全受信バイト・指令・入力を保存。diagnoseでは省略しても保存する')
    parser.add_argument('--diagnostic-baseline-a', type=positive_float, default=.2,
                        help='diagnoseの開く段階で使用する電流 A（既定0.2、確認済み安全値ではない）')
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument('--current-limit-a', type=positive_float, help='電流上限 A (0 < A <= 2)。省略時は変更しない')
    limits.add_argument('--torque-limit-nm', type=positive_float, help='トルク上限 N·m。確認済みトルク定数が必要')
    parser.add_argument('--torque-constant-nm-per-a', type=positive_float,
                        help='指定する軸で確認済みの実効トルク定数 N·m/A')
    parser.add_argument('--execute', action='store_true', help='実際に接続し、グリッパ指令を送る')
    args = parser.parse_args(argv)
    if args.angle > MAX_ANGLE or args.hold > 60 or args.timeout > 30:
        parser.error('angle <= 1.67、hold <= 60、timeout <= 30 が必要です')
    if args.grip_speed > 2:
        parser.error('grip-speed <= 2 が必要です（ソフトウェア側の目標変化率）')
    if args.torque_limit_nm is not None:
        if args.torque_constant_nm_per_a is None:
            parser.error('--torque-limit-nm には --torque-constant-nm-per-a が必要です')
        args.current_limit_a = args.torque_limit_nm / args.torque_constant_nm_per_a
    elif args.torque_constant_nm_per_a is not None and args.action != 'interactive':
        parser.error('トルク定数は --torque-limit-nm と一緒に指定してください')
    if args.current_limit_a is not None:
        try:
            validate_current_limit(args.current_limit_a)
        except ValueError as exc:
            parser.error(str(exc))
    if args.action == 'limit' and args.current_limit_a is None:
        parser.error('limit には電流上限またはトルク上限を指定してください')
    if args.action == 'diagnose':
        if args.current_limit_a is None:
            parser.error('diagnoseには比較する --current-limit-a が必要です')
        try:
            validate_current_limit(args.diagnostic_baseline_a)
        except ValueError as exc:
            parser.error(str(exc))
        if args.angle / args.grip_speed > 10 or args.hold > 5 or args.timeout > 10:
            parser.error('diagnoseは閉じ目標の所要時間 <= 10秒、hold <= 5、timeout <= 10 が必要です')
        if args.diagnostic_baseline_a > args.current_limit_a:
            parser.error('diagnoseのbaseline電流は比較電流以下にしてください')
    return args


def load_driver(source):
    source = Path(source)
    if hashlib.sha256(source.read_bytes()).hexdigest() != DRIVER_SHA256:
        raise ValueError('PIKAドライバの固定SHA256が一致しません')
    import serial
    if serial.__version__ != '3.5':
        raise RuntimeError('pyserial==3.5 が必要です')
    spec = importlib.util.spec_from_file_location('_pinned_pika_control_driver', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def monitored_driver(module):
    class MonitoredGripper(module.PikaGripper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.latest = None
            self.fault = None
            self.fault_detail = None
            self.last_disable_sent = None
            self.last_position_sent = None
            self.last_position_target = None
            self._framer = TelemetryFramer()
            self._valid_frames = 0
            self._rejected_frames = 0
            self._corrupt_frames = 0
            self._corrupt_samples = deque(maxlen=8)
            self._last_corrupt_warning = float('-inf')
            self._last_rx_warning = float('-inf')
            self._trace_start = time.monotonic()
            self._trace_lock = threading.Lock()
            self._rx_history = deque(maxlen=256)
            self._tx_history = deque(maxlen=64)
            self._fault_trace = None
            self._after_fault_rx = []
            self._after_fault_tx = []
            # Reenter the upstream send lock so validation also runs after
            # waiting for an in-flight read. Keep upstream byte encoding.
            self._serial_lock = threading.RLock()
            self.recorder = None
            self.phase = 'connect'
            self.diagnostic_guard = None

        def record(self, kind, **fields):
            if self.recorder is not None:
                self.recorder.record(kind, phase=self.phase, **fields)

        def set_phase(self, phase, guard=None):
            self.phase = phase
            self.diagnostic_guard = guard
            self.record('phase', guard=guard)

        def _consume_buffer(self):
            self.record('rx_bytes', chunk=self._buf)
            before = self._framer.resync_count
            frames = self._framer.feed(self._buf)
            self._buf = b''
            for frame in frames:
                self._parse_frame(frame)
            now = time.monotonic()
            if self._framer.resync_count > before and now - self._last_rx_warning >= 5.:
                LOGGER.warning('[PikaGripper] %s: 受信JSONを再同期 (累計%d回、%d bytes破棄; 表示は最大5秒に1回)',
                               self.port, self._framer.resync_count, self._framer.discarded_bytes)
                self._last_rx_warning = now

        def rx_diagnostics(self):
            return dict(valid_frames=self._valid_frames, rejected_frames=self._rejected_frames,
                        corrupt_frames=self._corrupt_frames, corrupt_samples=list(self._corrupt_samples),
                        resync_count=self._framer.resync_count,
                        discarded_bytes=self._framer.discarded_bytes,
                        buffered_bytes=len(self._framer.buffer))

        def reject_value(self, reason, field, value, frame):
            self._rejected_frames += 1
            self.record('rx_rejected', field=field, value=repr(value)[:128],
                        raw_frame_hex=frame.hex(), reason=reason)
            if self.fault is None:
                self.fault_detail = dict(field=field, value=repr(value)[:128],
                                         phase=self.phase,
                                         raw_frame=frame.decode('utf-8', errors='replace')[:1024])
                if self.latest is not None:
                    self.fault_detail['previous_position_rad'] = self.latest[1].position
                    self.fault_detail['previous_age_ms'] = (time.monotonic() - self.latest[0]) * 1000
                with self._trace_lock:
                    self.fault_detail['last_position_target_rad'] = self.last_position_target
                    self._fault_trace = dict(fault_time_s=time.monotonic() - self._trace_start,
                                              fault_detail=self.fault_detail,
                                              before_rx=list(self._rx_history),
                                              before_tx=list(self._tx_history))
                self.fault = f'{reason}: {field}={repr(value)[:128]}'
            else:
                with self._trace_lock:
                    if len(self._after_fault_rx) < 128:
                        self._after_fault_rx.append(dict(t_s=time.monotonic() - self._trace_start,
                                                          accepted=False, field=field, value=repr(value)[:128]))

        def fault_trace(self):
            with self._trace_lock:
                if self._fault_trace is None:
                    return None
                return dict(**self._fault_trace, after_rx=list(self._after_fault_rx),
                            after_tx=list(self._after_fault_tx))

        def _parse_frame(self, frame):
            # Validate complete position/status before updating upstream state.
            # Ignore broken/partial JSON; absence of good frames expires below.
            try:
                data = json.loads(frame)
                position = data['motor']['Position']
                status_value = data['motorstatus']['Status']
                if not isinstance(status_value, str):
                    self._rejected_frames += 1
                    return
                status = int(status_value, 16)
                if not 0 <= status <= 255:
                    self._rejected_frames += 1
                    return
                # Official SDK status table: bits 0..5 are driver faults;
                # 0x40 is enable and 0x80 is homed, neither is a fault.
                if self.phase != 'cleanup' and status & 0x3f:
                    self.reject_value('ドライバの異常ビットを受信しました', 'motorstatus.Status', status_value, frame)
                    return
                current = data['motor'].get('Current')
                if type(current) in (int, float) and math.isfinite(current) and abs(current) >= CORRUPT_CURRENT_MA:
                    # Reject the whole frame before using its angle/status.
                    # Like malformed JSON, this must NOT refresh feedback.
                    # A real out-of-range angle with ordinary current still
                    # latches below; sustained damage expires in 250 ms.
                    self._rejected_frames += 1
                    self._corrupt_frames += 1
                    event = dict(t_s=time.monotonic() - self._trace_start, accepted=False,
                                 phase=self.phase, reason='grossly_corrupt_current',
                                 raw_frame=frame.decode('utf-8', errors='replace')[:1024])
                    self._corrupt_samples.append(event)
                    with self._trace_lock:
                        self._rx_history.append(event)
                        if self._fault_trace is not None and len(self._after_fault_rx) < 128:
                            self._after_fault_rx.append(event)
                    self.record('rx_corrupt', raw_frame_hex=frame.hex(), current_ma=current)
                    now = time.monotonic()
                    if now - self._last_corrupt_warning >= 5.:
                        LOGGER.warning('[PikaGripper] %s: 破損した数値フレームを破棄 (累計%d回、Current=%s mA; 正常受信期限250msは維持)',
                                       self.port, self._corrupt_frames, current)
                        self._last_corrupt_warning = now
                    return
                if type(position) not in (int, float) or not math.isfinite(position) or not -.05 <= position <= 1.72:
                    self.reject_value('受信角度が診断範囲外または非有限です', 'motor.Position', position, frame)
                    return
                guard = self.diagnostic_guard
                if guard is not None and not guard[0] <= position <= guard[1]:
                    self.reject_value(f'診断中の移動量が中止条件を超えました（{guard[0]:.3f}〜{guard[1]:.3f} rad）',
                                      'motor.Position', position, frame)
                    return
                for key in ('Speed', 'Current'):
                    value = data['motor'].get(key)
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                        self.reject_value('受信速度/電流が非有限または不正です', f'motor.{key}', value, frame)
                        return
                for key in ('Voltage', 'DriverTemp', 'MotorTemp', 'BusCurrent'):
                    value = data['motorstatus'].get(key)
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                        self.reject_value('受信電圧/温度/電流が非有限または不正です', f'motorstatus.{key}', value, frame)
                        return
                super()._parse_frame(frame)
                self.latest = (time.monotonic(), super().get_state())
                self._valid_frames += 1
                event = dict(t_s=self.latest[0] - self._trace_start, accepted=True, **asdict(self.latest[1]))
                self.record('rx_state', state=asdict(self.latest[1]))
                with self._trace_lock:
                    self._rx_history.append(event)
                    if self._fault_trace is not None and len(self._after_fault_rx) < 128:
                        self._after_fault_rx.append(event)
            except (ValueError, KeyError, TypeError, AttributeError):
                self._rejected_frames += 1
                self.record('rx_invalid', raw_frame_hex=frame.hex())
                return

        def fresh_state(self, *, for_cleanup=False):
            latest = self.latest
            if self.fault and not for_cleanup:
                raise RuntimeError(self.fault)
            if not for_cleanup and self.recorder is not None and self.recorder.error is not None:
                raise RuntimeError(f'診断記録に失敗しました: {self.recorder.error}')
            if latest is None or not 0 <= time.monotonic() - latest[0] <= STATE_MAX_AGE:
                raise RuntimeError('グリッパ状態が未受信または250ms以上古いです')
            return latest[1]

        def _send(self, cmd, *values, flush=True):
            if cmd not in (10, 11, 15, 22):
                raise ValueError('この操作で許可されていないPIKA指令です')
            started = time.monotonic()
            self.record('tx_request', cmd=cmd, values=list(values), flush=flush)
            try:
                with self._serial_lock:
                    if cmd != 10:  # Never block disable on stale telemetry/log failures.
                        state = self.fresh_state()
                        if cmd == 22 and not state.enabled:
                            raise RuntimeError('無効状態で位置目標は送れません')
                    result = super()._send(cmd, *values, flush=flush)
            except BaseException as exc:
                self.record('tx_error', cmd=cmd, values=list(values), error=str(exc))
                raise
            sent = time.monotonic()
            event = dict(t_s=sent - self._trace_start, cmd=cmd, values=list(values),
                         flush=flush, send_duration_ms=(sent - started) * 1000)
            self.record('tx_written', cmd=cmd, values=list(values), flush=flush,
                        send_duration_ms=event['send_duration_ms'])
            with self._trace_lock:
                if cmd == 10:
                    self.last_disable_sent = sent
                elif cmd == 22:
                    self.last_position_sent = sent
                    self.last_position_target = values[0]
                self._tx_history.append(event)
                if self._fault_trace is not None and len(self._after_fault_tx) < 32:
                    self._after_fault_tx.append(event)
            return result

    return MonitoredGripper


def validate_current_limit(current_a):
    if (type(current_a) not in (int, float) or not math.isfinite(current_a)
            or not 0 < current_a <= MAX_CURRENT_A):
        raise ValueError(f'電流上限は 0 < A <= {MAX_CURRENT_A:g} の有限値で指定してください')
    try:
        encoded = struct.unpack('<f', struct.pack('<f', current_a))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError('電流上限をfloat32で表現できません') from exc
    if not math.isfinite(encoded) or encoded <= 0:
        raise ValueError('電流上限をfloat32で表現できません')


def set_current_limit(gripper, current_a):
    """Send command 15 in A. Firmware limiting semantics/ACK are unverified."""
    validate_current_limit(current_a)
    gripper.set_effort_limit(current_a)


def hold(gripper, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not gripper.fresh_state().enabled:
            raise RuntimeError('待機中にグリッパが無効になりました')
        time.sleep(min(.05, max(0., deadline - time.monotonic())))


def disable_and_confirm(gripper):
    # A detected telemetry fault must not wait for the reported speed to settle.
    gripper.disable(retries=10, retry_period=.2, settle_timeout=0. if gripper.fault else .5)
    state = gripper.fresh_state(for_cleanup=True)
    if (state.enabled or gripper.last_disable_sent is None
            or gripper.latest[0] < gripper.last_disable_sent):
        raise RuntimeError('無効化を確認できません')


def move_and_confirm(gripper, target, timeout, report):
    gripper.set_angle_and_wait(target, tolerance=.025, timeout=timeout, resend_period=.1)
    state = gripper.fresh_state()
    if (gripper.latest[0] < gripper.last_position_sent or not state.enabled
            or abs(state.position - target) > .025):
        raise TimeoutError(f'目標 {target} rad への到達を確認できません')
    report['moves'].append(dict(target_rad=target, **asdict(state)))
    report['move_count'] += 1
    # Keep long console sessions bounded; detailed arrivals are printed live.
    if len(report['moves']) > 64:
        del report['moves'][:-64]
    print(f'到達: target={target:.3f} rad, position={state.position:.4f} rad', flush=True)


CONSOLE_HELP = '''
help                 コマンド一覧
status               実測状態を表示
params               現在の操作パラメータを表示
open [rad]           指定角度に開く（省略時は設定した開き角度）
close                0 radへ閉じる
grip [A]             段階的に閉じる。把持中の再入力は電流だけ変更
move rad             任意角度へ移動 (0〜1.67 rad)
cycle [rad]          開く→待機→閉じる
current A            電流上限を変更 (0 < A <= 2、例: current 0.2)
kt Nm/A              確認済み実効トルク定数を設定（送信なし）
torque Nm            設定済みktで電流上限へ換算し送信
set angle rad        open/cycleの既定開き角度を変更
set timeout seconds  到達期限を変更 (0 < 秒 <= 30)
set hold seconds     cycleの開いた後の待機時間 (0〜60秒)
set grip-speed rad/s gripの閉じ目標の変化率 (0 < 値 <= 2、実測速度の制限ではない)
enable               現在の状態で有効化（位置目標は送らない）
disable / stop       無効化（接続は維持）
quit / exit          無効化・切断して終了（Ctrl+C/Ctrl+Dも終了）
'''.strip()


class ConsoleInput:
    """Poll Linux stdin without blocking hardware checks during idle input.

    Read raw bytes so redirected/pasted multiple lines do not get stranded
    in TextIOWrapper buffers while select() waits for another OS event.
    """
    def __init__(self, stream=None):
        self.stream = sys.stdin if stream is None else stream
        self.buffer = b''
        self.eof = False

    def read(self, prompt, check):
        print(prompt, end='', flush=True)
        while True:
            check()
            if b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                return line.decode(self.stream.encoding or 'utf-8', errors='replace').rstrip('\r')
            if self.eof:
                if self.buffer:
                    line, self.buffer = self.buffer, b''
                    return line.decode(self.stream.encoding or 'utf-8', errors='replace')
                raise EOFError
            if not select.select([self.stream.fileno()], [], [], .05)[0]:
                continue
            chunk = os.read(self.stream.fileno(), 4096)
            if not chunk:
                self.eof = True
            self.buffer += chunk
            if len(self.buffer) > 16384:
                raise RuntimeError('入力が長すぎます（最大16384 byte）')


class GripperConsole:
    def __init__(self, gripper, args, report):
        self.gripper = gripper  # None means command preview, never fake feedback.
        self.angle = args.angle
        self.timeout = args.timeout
        self.hold = args.hold
        self.current_a = args.current_limit_a
        self.grip_speed = args.grip_speed
        self.kt = args.torque_constant_nm_per_a
        self.report = report
        self.expect_enabled = False
        self.grip_active = False
        self.last_grip_sent = 0.
        self.grip_target = None
        self.action = args.action

    def check(self):
        if self.gripper is not None:
            state = self.gripper.fresh_state()
            if self.expect_enabled and not state.enabled:
                raise RuntimeError('操作中/入力待ち中にグリッパが無効になりました')
            elapsed = time.monotonic() - self.last_grip_sent
            if self.grip_active and self.grip_target > 0. and elapsed >= GRIP_PERIOD:
                # Limit each increment too: after a delayed input/serial call,
                # never catch up by jumping directly to a distant target.
                target = max(0., self.grip_target - self.grip_speed * min(elapsed, GRIP_PERIOD))
                self.gripper._send(22, target, flush=False)
                self.grip_target = target
                self.last_grip_sent = time.monotonic()
                if target == 0. and self.action == 'interactive':
                    self.gripper.set_phase('grip_hold')

    def enable(self):
        if self.gripper is not None:
            self.check()
            if not self.gripper.fresh_state().enabled:
                self.gripper.enable(retries=10, retry_period=.2)
            if not self.gripper.fresh_state().enabled:
                raise RuntimeError('有効化を確認できません')
            self.expect_enabled = True

    def move(self, target):
        self.grip_active = False
        self.grip_target = None
        if self.gripper is not None and self.action == 'interactive':
            self.gripper.set_phase('interactive_move')
        self.enable()
        if self.gripper is None:
            print(f'[preview] enable → 目標 {target:.3f} rad（送信なし）')
        else:
            move_and_confirm(self.gripper, target, self.timeout, self.report)
            if self.action == 'interactive':
                self.gripper.set_phase('position_hold')

    @staticmethod
    def number(value, minimum=0., maximum=math.inf, *, positive=False):
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError('数値を指定してください') from exc
        if not math.isfinite(number) or not minimum <= number <= maximum or (positive and number <= 0):
            raise ValueError(f'有限値 {minimum}〜{maximum} を指定してください（正数必須: {positive}）')
        return number

    def change_current(self, value):
        validate_current_limit(value)
        if self.gripper is not None:
            set_current_limit(self.gripper, value)
            self.report['limit_command_sent'] = True
        self.current_a = value
        self.report['current_limit_a'] = value
        print(f'{"[preview] " if self.gripper is None else ""}電流上限 {value:.6g} A'
              '（設定の読み戻し/ACKなし）')

    def command(self, line):
        parts = shlex.split(line)
        if not parts:
            return True
        name, values = parts[0].lower(), parts[1:]
        counts = {'help': (0,), 'status': (0,), 'params': (0,), 'open': (0, 1), 'close': (0,), 'grip': (0, 1),
                  'move': (1,), 'cycle': (0, 1), 'current': (1,), 'kt': (1,), 'torque': (1,),
                  'set': (2,), 'enable': (0,), 'disable': (0,), 'stop': (0,), 'quit': (0,), 'exit': (0,)}
        if name not in counts or len(values) not in counts[name]:
            raise ValueError('不明なコマンドまたは引数の数が違います。helpを参照してください')
        if name in ('quit', 'exit'):
            return False
        if name == 'help':
            print(CONSOLE_HELP)
        elif name == 'status':
            if self.gripper is None:
                print('[preview] 未接続。実測状態は取得していません')
            else:
                print(json.dumps(asdict(self.gripper.fresh_state()), ensure_ascii=False, indent=2, allow_nan=False))
        elif name == 'params':
            print(json.dumps(dict(open_angle_rad=self.angle, timeout_s=self.timeout, cycle_hold_s=self.hold,
                                  requested_current_limit_a=self.current_a, torque_constant_nm_per_a=self.kt,
                                  grip_active=self.grip_active, grip_speed_rad_s=self.grip_speed,
                                  grip_target_rad=self.grip_target, limit_readback_available=False),
                             ensure_ascii=False, indent=2, allow_nan=False))
        elif name == 'grip':
            current_a = self.number(values[0], positive=True) if values else self.current_a
            if current_a is None:
                raise ValueError('grip 0.2 のように電流 A を指定してください')
            validate_current_limit(current_a)  # Check all arguments before enabling.
            self.change_current(current_a)
            # Repeated grip commands adjust current without replacing an
            # existing closed/ramping target with the obstructed jaw angle.
            if not self.grip_active:
                self.enable()
                if self.gripper is not None:
                    self.gripper.set_phase('grip_ramp')
                    self.grip_target = max(0., min(MAX_ANGLE, self.gripper.fresh_state().position))
                    self.gripper.set_angle(self.grip_target)
                    self.last_grip_sent = time.monotonic()
                    if self.grip_target == 0.:
                        self.gripper.set_phase('grip_hold')
            self.grip_active = True
            self.report['grip_count'] = self.report.get('grip_count', 0) + 1
            print(f'{"[preview] " if self.gripper is None else ""}grip: {current_a:g} A、目標変化率{self.grip_speed:g} rad/sで閉じる。'
                  'currentで調整、openで開く、stopで無効化。')
        elif name in ('open', 'move', 'close', 'cycle'):
            target = 0. if name == 'close' else (
                self.number(values[0], maximum=MAX_ANGLE, positive=name in ('open', 'cycle'))
                if values else self.angle)
            self.move(target)
            if name == 'cycle':
                if self.gripper is not None:
                    hold(self.gripper, self.hold)
                else:
                    print(f'[preview] {self.hold:.3f}秒待機（実際には待機しません）')
                self.move(0.)
        elif name == 'current':
            self.change_current(self.number(values[0], positive=True))
        elif name == 'kt':
            self.kt = self.number(values[0], positive=True)
            print(f'トルク定数 {self.kt:.6g} N·m/A を設定（利用者の確認値、送信なし）')
        elif name == 'torque':
            value = self.number(values[0], positive=True)
            if self.kt is None:
                raise ValueError('先に kt <確認済みN·m/A> を指定してください')
            self.change_current(value / self.kt)
        elif name == 'set':
            key = values[0].lower()
            if key == 'angle':
                self.angle = self.number(values[1], maximum=MAX_ANGLE, positive=True)
            elif key == 'timeout':
                self.timeout = self.number(values[1], maximum=30., positive=True)
            elif key == 'hold':
                self.hold = self.number(values[1], maximum=60.)
            elif key == 'grip-speed':
                self.grip_speed = self.number(values[1], maximum=2., positive=True)
                self.report['grip_speed_rad_s'] = self.grip_speed
            else:
                raise ValueError('setは angle / timeout / hold / grip-speed を指定してください')
            applies = 'grip中は次の更新から適用' if key == 'grip-speed' else '次の操作から適用'
            print(f'{key} = {values[1]}（{applies}、この入力では送信なし）')
        elif name == 'enable':
            self.enable()
            print('[preview] enable（送信なし）' if self.gripper is None else '有効化を確認しました')
        elif name in ('disable', 'stop'):
            self.grip_active = False
            self.grip_target = None
            if self.gripper is not None:
                self.gripper.set_phase('interactive_stop')
                disable_and_confirm(self.gripper)
                self.expect_enabled = False
            print('[preview] disable（送信なし）' if self.gripper is None else '無効化を確認しました')
        return True


def console_loop(gripper, args, report, read_command=None):
    console = GripperConsole(gripper, args, report)
    if gripper is not None:
        gripper.set_phase('interactive_idle')
    reader = ConsoleInput().read if read_command is None else read_command
    print(CONSOLE_HELP)
    print('位置操作後は有効状態を維持します。disableで無効化、quitで終了。')
    prompt = 'pika> ' if gripper is not None else 'pika[preview]> '
    while True:
        try:
            line = reader(prompt, console.check)
        except EOFError:
            print('\n入力終了。終了処理を行います。')
            break
        console.check()
        if gripper is not None:
            gripper.record('console_command', line=line)
        try:
            if not console.command(line):
                break
        except ValueError as exc:
            print(f'入力エラー: {exc}')
    report['console_parameters'] = dict(open_angle_rad=console.angle, timeout_s=console.timeout,
                                        cycle_hold_s=console.hold, torque_constant_nm_per_a=console.kt,
                                        grip_speed_rad_s=console.grip_speed)


def diagnose(gripper, args, report):
    """One finite comparison, with current change separated from closure.

    This does not certify current limits, gripping force or future usability.
    Do not resend position during the current-only interval: record the
    response to command 15 with the previous target left unchanged.
    """
    report['diagnostic_target_current_a'] = args.current_limit_a
    report['diagnostic_baseline_a'] = args.diagnostic_baseline_a
    report['diagnostic_excursion_rad'] = DIAGNOSTIC_EXCURSION
    report['diagnostic_scope'] = 'single_run_response_not_force_or_hardware_certification'
    gripper.set_phase('baseline_current')
    set_current_limit(gripper, args.diagnostic_baseline_a)
    report['current_limit_a'] = args.diagnostic_baseline_a
    report['limit_command_sent'] = True
    gripper.set_phase('baseline_open')
    gripper.enable(retries=10, retry_period=.2)
    move_and_confirm(gripper, args.angle, args.timeout, report)
    position = gripper.fresh_state().position
    guard = [max(-.05, position - DIAGNOSTIC_EXCURSION), min(1.72, position + DIAGNOSTIC_EXCURSION)]
    gripper.set_phase('baseline_hold', guard)
    print('診断1: 開いた角度のまま基準電流で待機', flush=True)
    hold(gripper, args.hold)
    gripper.set_phase('current_change_hold', guard)
    print(f'診断2: 位置目標を変更せず、電流指令だけ {args.current_limit_a:g} Aへ変更', flush=True)
    set_current_limit(gripper, args.current_limit_a)
    report['current_limit_a'] = args.current_limit_a
    hold(gripper, args.hold)
    console = GripperConsole(gripper, args, report)
    console.expect_enabled = True
    console.grip_target = max(0., min(MAX_ANGLE, gripper.fresh_state().position))
    console.grip_active = True
    # Opening by more than 0.1 rad during a closing trial aborts even if the
    # value is inside the general angle range. It is an experiment rule.
    gripper.set_phase('close_ramp', [-.05, min(1.72, console.grip_target + DIAGNOSTIC_EXCURSION)])
    print('診断3: 電流指令を再送せず、位置目標を段階的に0 radへ変更', flush=True)
    gripper.set_angle(console.grip_target)
    console.last_grip_sent = time.monotonic()
    deadline = time.monotonic() + 10.
    while console.grip_target > 0:
        console.check()
        if time.monotonic() > deadline:
            raise TimeoutError('診断の閉じ目標更新が10秒以内に完了しませんでした')
        time.sleep(.01)
    gripper.set_phase('closed_hold', gripper.diagnostic_guard)
    end = time.monotonic() + args.hold
    while time.monotonic() < end:
        console.check()
        time.sleep(min(.01, max(0., end - time.monotonic())))
    report['grip_count'] = 1
    report['diagnostic_result'] = 'no_abort_in_this_run'


def run(gripper, args, read_command=None):
    report = dict(completed=False, disable_confirmed=False, port_closed=False,
                  current_limit_a=args.current_limit_a, limit_command_sent=False,
                  limit_readback_available=False, moves=[], move_count=0,
                  grip_speed_rad_s=args.grip_speed,
                  hardware_execution=gripper is not None)
    try:
        if gripper is not None:
            if args.record_dir is not None or args.action == 'diagnose':
                gripper.recorder = SessionRecorder(args.record_dir or args.fault_log_dir, gripper._trace_start)
                report['session_log'] = str(gripper.recorder.output)
                gripper.record('session_start', action=args.action, current_limit_a=args.current_limit_a,
                               baseline_current_a=args.diagnostic_baseline_a, angle_rad=args.angle,
                               grip_speed_rad_s=args.grip_speed, hold_s=args.hold, driver_sha256=DRIVER_SHA256,
                               control_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               scope='host_reads_and_writes_not_firmware_ack')
            gripper.connect()
            gripper._serial.write_timeout = .5
            gripper._serial.exclusive = True
            gripper.wait_for_state(timeout=3.)
            initial = gripper.fresh_state()
            report['initial'] = asdict(initial)
            if initial.enabled:
                raise RuntimeError('初期状態で既に有効です。他の制御を終了してください')
            if args.current_limit_a is not None and args.action != 'diagnose':
                set_current_limit(gripper, args.current_limit_a)
                report['limit_command_sent'] = True
        if args.action == 'diagnose':
            diagnose(gripper, args, report)
        elif args.action == 'interactive':
            console_loop(gripper, args, report, read_command)
        elif args.action != 'limit':
            gripper.enable(retries=10, retry_period=.2)
            if not gripper.fresh_state().enabled:
                raise RuntimeError('有効化を確認できません')
            targets = {'open': [args.angle], 'close': [0.], 'cycle': [args.angle, 0.]}[args.action]
            for target in targets:
                move_and_confirm(gripper, target, args.timeout, report)
                hold(gripper, args.hold)
        report['completed'] = True
    except KeyboardInterrupt:
        report['error'] = '操作中断 (SIGINT/SIGTERM)'
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if gripper is not None:
            report['last_operation_phase'] = gripper.phase
            gripper.set_phase('cleanup')
        if gripper is not None and gripper.is_connected:
            try:
                disable_and_confirm(gripper)
                report['disable_confirmed'] = True
            except Exception as exc:
                report['disable_error'] = str(exc)
            finally:
                try:
                    gripper.disconnect()
                except Exception as exc:
                    report['disconnect_error'] = str(exc)
        report['port_closed'] = gripper is None or not gripper.is_connected
        if gripper is not None:
            report['rx'] = gripper.rx_diagnostics()
            report['telemetry_numeric_integrity_ok'] = gripper._corrupt_frames == 0 and gripper.fault_detail is None
            if gripper.fault_detail is not None:
                # Completion precedes cleanup. A fault first seen during
                # cleanup must still make the whole session fail.
                report.setdefault('error', gripper.fault)
                report['fault_detail'] = gripper.fault_detail
                try:
                    args.fault_log_dir.mkdir(parents=True, exist_ok=True)
                    output = Path(tempfile.mkdtemp(prefix='fault-', dir=args.fault_log_dir)) / 'trace.json'
                    trace = dict(port=gripper.port, action=args.action, driver_sha256=DRIVER_SHA256,
                                 current_limit_a=report['current_limit_a'], grip_speed_rad_s=report['grip_speed_rad_s'],
                                 scope='telemetry_and_commands_not_verified_motion', **gripper.fault_trace())
                    output.write_text(json.dumps(trace, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                    report['fault_log'] = str(output)
                except Exception as exc:
                    report['fault_log_error'] = str(exc)
            if gripper.recorder is not None:
                gripper.record('session_end', completed=report['completed'], error=report.get('error'),
                               disable_confirmed=report['disable_confirmed'], port_closed=report['port_closed'])
                gripper.recorder.close()
                if gripper.recorder.error is not None:
                    report['session_log_error'] = gripper.recorder.error
    report['passed'] = bool(report['completed'] and (gripper is None or report['disable_confirmed']) and report['port_closed']
                            and not any(key.endswith('error') for key in report))
    if gripper is not None and gripper.recorder is not None:
        try:
            (gripper.recorder.output / 'report.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        except Exception as exc:
            report['session_log_error'] = str(exc)
            report['passed'] = False
    return report


def main(argv=None):
    args = parse_args(argv)
    plan = dict(action=args.action, port=args.port, angle_rad=args.angle, hold_s=args.hold,
                current_limit_a=args.current_limit_a, grip_speed_rad_s=args.grip_speed, execute=args.execute)
    print(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False))
    gripper = None
    if not args.execute and args.action != 'interactive':
        print('プレビューのみ。実機操作には --execute を指定してください。')
        return 0
    if args.execute:
        try:
            try:
                resolved = Path(args.port).resolve(strict=True)
            except FileNotFoundError as exc:
                raise ValueError(f'ポート {args.port} が存在しません。'
                                 '既定パスはG1搭載PC用です。接続PCのUSBシリアルを '
                                 '--port /dev/ttyUSB0 などで指定してください') from exc
            if not stat.S_ISCHR(resolved.stat().st_mode):
                raise ValueError('指定ポートはキャラクターデバイスではありません')
            if args.port == RIGHT_PORT and resolved != Path(RIGHT_DEVICE).resolve(strict=True):
                raise ValueError('記録済みの右PIKAデバイスと一致しません')
            module = load_driver(args.driver)
            gripper = monitored_driver(module)(args.port)
        except Exception as exc:
            print(f'接続前エラー: {exc}', file=sys.stderr)
            return 1
    else:
        print('プレビュー対話モード。ポートは開かず、指令は送信しません。')
    stop_requested = False
    def interrupted(signum, frame):
        nonlocal stop_requested
        if not stop_requested:
            stop_requested = True
            raise KeyboardInterrupt
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        report = run(gripper, args)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
