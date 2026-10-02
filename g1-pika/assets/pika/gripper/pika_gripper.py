#!/usr/bin/env python

# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Serial driver for the AgileX Pika Gripper.

Protocol reverse-engineered from pika_ros's serial_gripper_imu.cpp: each
command is a single command-code byte followed by zero or more little-endian
float32 values and a trailing b"\\r\\n". The gripper streams back a
continuous sequence of JSON objects shaped like:

    {"motor": {"Speed": .., "Current": .., "Position": ..},
     "motorstatus": {"Voltage": .., "DriverTemp": .., "MotorTemp": ..,
                      "Status": "0x..", "BusCurrent": ..}}

Angle range is [0.0, 1.67] rad (closed -> open). The gripper firmware in
this deployment runs in MIT mode, so position targets must be sent with
POSITION_CTRL_MIT (not POSITION_CTRL_POS_VEL, which this firmware ignores).
"""

import json
import logging
import struct
import threading
import time
from dataclasses import dataclass

import serial

logger = logging.getLogger(__name__)

BAUD_RATE = 460800
MIN_ANGLE = 0.0
MAX_ANGLE = 1.67

# ZMQ ports used by run_g1_server.py's --gripper bridge and by
# RemotePikaGripper (remote_pika_gripper.py) to talk to it. Defined here
# (rather than in run_g1_server.py, which imports unitree_sdk2py at module
# scope) so remote clients don't need the Unitree SDK installed just to get
# these two integers.
GRIPPER_CMD_PORT = 6100
GRIPPER_STATE_PORT = 6101
GRIPPER_SIDES = ("left", "right")

# Command codes (Send_Flag in serial_gripper_imu.cpp)
_DISABLE = 10
_ENABLE = 11
_SET_ZERO = 12
_VELOCITY_CTRL = 13
_EFFORT_CTRL = 15
_POSITION_CTRL_MIT = 22
_POSITION_CTRL_POS_VEL = 23

_ENABLED_STATUS_BIT = 0b01000000


@dataclass
class PikaGripperState:
    position: float | None = None  # rad, raw motor angle
    speed: float | None = None
    current: float | None = None
    voltage: float | None = None
    driver_temp: float | None = None
    motor_temp: float | None = None
    status: int | None = None  # raw status byte
    bus_current: float | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.status is not None and self.status & _ENABLED_STATUS_BIT)


class PikaGripper:
    """Thin serial driver for a single Pika Gripper unit."""

    def __init__(self, port: str, baud_rate: int = BAUD_RATE):
        self.port = port
        self.baud_rate = baud_rate
        self._serial: serial.Serial | None = None
        self._serial_lock = threading.Lock()  # serializes read()/write() on this port; see _read_loop
        self._state = PikaGripperState()
        self._state_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._buf = b""

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        if self.is_connected:
            return
        self._serial = serial.Serial(self.port, self.baud_rate, timeout=0.1)
        # The CH340 adapter toggles DTR/RTS on open, which briefly resets the
        # gripper's MCU. Commands sent before it finishes reinitializing are
        # silently ignored (confirmed experimentally: ENABLE sent <0.5s after
        # open never took effect, but did after ~1s). wait_for_state() alone
        # isn't a reliable substitute since JSON status frames start flowing
        # again before the MCU is done initializing.
        time.sleep(1.0)
        self._shutdown_event.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        logger.info(f"[PikaGripper] Connected on {self.port}")

    def disconnect(self) -> None:
        if not self.is_connected:
            return
        try:
            self.disable()
        except Exception as e:
            logger.warning(f"[PikaGripper] Failed to disable on disconnect: {e}")
        self._shutdown_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        self._serial.close()
        self._serial = None
        logger.info(f"[PikaGripper] Disconnected from {self.port}")

    def _read_loop(self) -> None:
        # Holds _serial_lock only for the read() call itself (bounded by the
        # port's 0.1s timeout), not across the whole loop iteration, so a
        # pending write() never waits long. This adapter's CH340 driver
        # doesn't reliably tolerate a write() landing while a read() is
        # in-flight (confirmed experimentally: commands sent from a thread
        # that reads continuously and unsynchronized were silently dropped
        # far more often than in a single-threaded read-then-write script).
        #
        # Transient SerialException (e.g. "device reports readiness to read
        # but returned no data") happens on this adapter occasionally and is
        # NOT fatal -- confirmed experimentally: bailing out on the first one
        # used to silently kill this thread forever, freezing get_state() at
        # whatever it last saw while callers kept retrying commands against a
        # gripper that looked alive but wasn't being listened to anymore.
        # Only give up after several consecutive failures (real disconnect).
        consecutive_errors = 0
        max_consecutive_errors = 20
        while not self._shutdown_event.is_set():
            try:
                with self._serial_lock:
                    chunk = self._serial.read(256)
                consecutive_errors = 0
            except serial.SerialException as e:
                consecutive_errors += 1
                logger.warning(
                    f"[PikaGripper] Serial read error on {self.port} "
                    f"({consecutive_errors}/{max_consecutive_errors}): {e}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[PikaGripper] Giving up reading {self.port} after repeated errors")
                    return
                time.sleep(0.05)
                continue
            if not chunk:
                continue
            self._buf += chunk
            self._consume_buffer()

    # A dropped/truncated read (see the SerialException handling above) can
    # leave an unmatched '{' whose closing '}' never arrives, which would
    # otherwise make the brace-matching scan below wait forever on an
    # ever-growing buffer. serial_gripper_imu.cpp (the reference C++
    # implementation this protocol was reverse-engineered from) has the same
    # guard: `if(msg.size() > 1000) msg.clear();` in its receiving() loop.
    _MAX_BUF_BYTES = 4096

    def _consume_buffer(self) -> None:
        # Frames are back-to-back JSON objects; split on balanced braces so a
        # frame that arrives split across two reads still parses cleanly.
        if len(self._buf) > self._MAX_BUF_BYTES:
            logger.warning(
                f"[PikaGripper] {self.port}: read buffer hit {len(self._buf)} bytes "
                "(unmatched braces from a dropped read?), resyncing"
            )
            self._buf = b""
            return
        while True:
            start = self._buf.find(b"{")
            if start < 0:
                self._buf = b""
                return
            depth = 0
            end = None
            for i in range(start, len(self._buf)):
                if self._buf[i : i + 1] == b"{":
                    depth += 1
                elif self._buf[i : i + 1] == b"}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                self._buf = self._buf[start:]
                return
            frame = self._buf[start : end + 1]
            self._buf = self._buf[end + 1 :]
            self._parse_frame(frame)

    def _parse_frame(self, frame: bytes) -> None:
        try:
            data = json.loads(frame)
        except json.JSONDecodeError:
            return
        motor = data.get("motor", {})
        motorstatus = data.get("motorstatus", {})
        status_hex = motorstatus.get("Status")
        status = int(status_hex, 16) if status_hex else None
        with self._state_lock:
            if "Position" in motor:
                self._state.position = motor["Position"]
            if "Speed" in motor:
                self._state.speed = motor["Speed"]
            if "Current" in motor:
                self._state.current = motor["Current"]
            if "Voltage" in motorstatus:
                self._state.voltage = motorstatus["Voltage"]
            if "DriverTemp" in motorstatus:
                self._state.driver_temp = motorstatus["DriverTemp"]
            if "MotorTemp" in motorstatus:
                self._state.motor_temp = motorstatus["MotorTemp"]
            if status is not None:
                self._state.status = status
            if "BusCurrent" in motorstatus:
                self._state.bus_current = motorstatus["BusCurrent"]

    def get_state(self) -> PikaGripperState:
        with self._state_lock:
            return PikaGripperState(**self._state.__dict__)

    def _send(self, cmd: int, *values: float, flush: bool = True) -> None:
        if not self.is_connected:
            raise RuntimeError(f"[PikaGripper] {self.port} is not connected")
        payload = struct.pack("<B", cmd)
        for v in values:
            payload += struct.pack("<f", v)
        payload += b"\r\n"
        with self._serial_lock:
            if flush:
                # Flushing the input buffer right before write() measurably
                # improved command reliability in testing (CH340 driver
                # quirk, possibly a side effect of tcflush re-syncing the
                # adapter). BUT: callers that poll get_state() shortly after
                # sending (enable()/disable()) must NOT flush on every retry
                # -- doing so can discard the very confirmation frame that
                # was about to arrive, making a command that already
                # succeeded look like it's still failing forever.
                self._serial.reset_input_buffer()
            self._serial.write(payload)

    def enable(self, retries: int = 20, retry_period: float = 0.2) -> None:
        """Send ENABLE, resending until the enabled status bit is confirmed.

        Only the first send flushes the input buffer (see _send()'s `flush`
        docstring) -- subsequent retries must NOT flush, or they can wipe
        out the very confirmation frame the polling loop below is waiting
        for, making an ENABLE that already succeeded look like it never did.
        """
        for attempt in range(retries):
            self._send(_ENABLE, 0.0, flush=(attempt == 0))
            time.sleep(retry_period)
            if self.get_state().enabled:
                return
        raise TimeoutError(f"[PikaGripper] {self.port}: ENABLE not confirmed after {retries} attempts")

    def disable(
        self,
        retries: int = 20,
        retry_period: float = 0.2,
        settle_speed: float = 0.01,
        settle_timeout: float = 3.0,
    ) -> None:
        """Wait for motion to settle, then send DISABLE, resending until confirmed.

        See enable() re: only flushing on the first attempt. The settle wait
        is a genuine precaution (don't cut torque mid-servo) but turned out
        NOT to be the main cause of DISABLE's apparent unreliability -- that
        was the flush-every-retry bug above; disable was very likely taking
        effect immediately and we were just repeatedly erasing the evidence.
        """
        settle_deadline = time.time() + settle_timeout
        while time.time() < settle_deadline:
            state = self.get_state()
            if state.speed is not None and abs(state.speed) <= settle_speed:
                break
            time.sleep(0.05)

        for attempt in range(retries):
            self._send(_DISABLE, 0.0, flush=(attempt == 0))
            time.sleep(retry_period)
            if not self.get_state().enabled:
                return
        raise TimeoutError(f"[PikaGripper] {self.port}: DISABLE not confirmed after {retries} attempts")

    def set_zero(self) -> None:
        self._send(_SET_ZERO, 0.0)

    def set_effort_limit(self, current_amps: float) -> None:
        self._send(_EFFORT_CTRL, current_amps)

    def set_velocity(self, velocity: float) -> None:
        self._send(_VELOCITY_CTRL, velocity, velocity)

    def set_angle(self, angle: float) -> None:
        """Send a target angle in [MIN_ANGLE, MAX_ANGLE] rad (MIT position control).

        Fire-and-forget: a dropped packet just means the next control-loop
        tick's set_angle() call (same or updated target) supersedes it. Do
        NOT add blocking retries here -- this is called every control cycle
        and a wait would distort the loop's timing. For a one-shot confirmed
        move (e.g. scripts/tests, not a running control loop), use
        set_angle_and_wait() instead.
        """
        angle = max(MIN_ANGLE, min(MAX_ANGLE, angle))
        self._send(_POSITION_CTRL_MIT, angle)

    def set_angle_and_wait(
        self,
        angle: float,
        tolerance: float = 0.02,
        timeout: float = 5.0,
        resend_period: float = 0.2,
    ) -> PikaGripperState:
        """Move to `angle` and block until position is within `tolerance` rad of it.

        Resends the target periodically (see set_angle()'s docstring on why
        single sends aren't reliable) until either the tolerance is met or
        `timeout` elapses, in which case the last-seen state is returned
        without raising (the gripper may just be mechanically obstructed).
        """
        angle = max(MIN_ANGLE, min(MAX_ANGLE, angle))
        deadline = time.time() + timeout
        state = self.get_state()
        attempt = 0
        while time.time() < deadline:
            self._send(_POSITION_CTRL_MIT, angle, flush=(attempt == 0))
            attempt += 1
            time.sleep(resend_period)
            state = self.get_state()
            if state.position is not None and abs(state.position - angle) <= tolerance:
                break
        return state

    def wait_for_state(self, timeout: float = 5.0) -> PikaGripperState:
        """Block until at least one status frame has been received."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.get_state()
            if state.position is not None:
                return state
            time.sleep(0.01)
        raise TimeoutError(f"[PikaGripper] Timed out waiting for state on {self.port}")
