"""
Generator remote control through a Scheiber SourceSelector node.

The SourceSelector node (``0x..0Bxx`` message family) that is wired to the
generator drives two relay outputs connected to the generator's remote
start and stop lines. The control panel sends a one-byte command frame and
the node pulses the matching relay itself:

- ``0x02460Bxx`` data ``01``: start. Output 1 closes for 30 s.
- ``0x02460Bxx`` data ``02``: stop. Output 2 closes for 60 s.

The node reports back on several frames (see plan/generator-control.md):

- ``0x02160Bxx``: relay output state, same 8-byte layout as the Bloc9 S1/S2
  status frame (bytes 0-3 output 1 = start relay, bytes 4-7 output 2 = stop
  relay).
- ``0x02140Bxx``: engine state byte. Bit 0 is set while the generator runs.
- ``0x02440Bxx``: control phase byte (``02``/``03`` starting, ``01`` running,
  ``05``/``04`` stopping, ``00`` stopped).
- ``0x02040Bxx``: AC measurement ``[genV u16][genHz u16][srcV u16][srcHz u16]``
  big-endian, generator values are 0 while stopped.
- ``0x02060Bxx``: generator starter battery voltage, u16 big-endian, 0.1 V.

Safety: commands only leave through ``ScheiberCanBus.send_message`` so
``read_only`` mode blocks them, and :meth:`GeneratorControl.start` /
:meth:`GeneratorControl.stop` refuse to send while the state is unknown,
while a relay pulse is still active, or when the generator is already in the
requested state.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

import can

from .bloc7 import SensorOutput, ValueConfig, create_sensor_output
from .matchers import Matcher
from .output import Output
from .protocol import (
    GENERATOR_COMMAND_START,
    GENERATOR_COMMAND_STOP,
    SOURCE_SELECTOR_AC_PREFIX,
    SOURCE_SELECTOR_COMMAND_PREFIX,
    SOURCE_SELECTOR_DC_PREFIX,
    SOURCE_SELECTOR_ENGINE_STATE_PREFIX,
    SOURCE_SELECTOR_OUTPUT_STATE_PREFIX,
    SOURCE_SELECTOR_PHASE_PREFIX,
    build_address_byte,
)

ENGINE_RUNNING_BIT = 0x01

PHASE_NAMES: Dict[int, str] = {
    0x00: "stopped",
    0x01: "running",
    0x02: "starting",
    0x03: "starting",
    0x04: "stopping",
    0x05: "stopping",
}

# Observed relay pulse lengths plus margin. Used only to expire a pulse whose
# release frame was missed; the node itself times the relays.
START_PULSE_EXPIRY_S = 45.0
STOP_PULSE_EXPIRY_S = 75.0

# Generator frequency outside this window is a measurement transient (values
# such as 1050 Hz appear for one frame right after a stop) and is ignored.
FREQUENCY_MIN_HZ = 40.0
FREQUENCY_MAX_HZ = 70.0
# Below this frequency the generator counts as not producing AC.
RUNNING_FREQUENCY_HZ = 40.0


class GeneratorInterlockError(RuntimeError):
    """Raised when a start/stop command is refused by the software interlock."""


class GeneratorControl:
    """
    Generator start/stop control and status for one SourceSelector node.

    State is derived from the bus only and never persisted: the node repeats
    its AC measurement at ~2 Hz, so ``running`` is known within a second of
    startup even though the engine-state and phase frames are only sent on
    change.
    """

    def __init__(
        self,
        device_id: int,
        name: str,
        entity_id: str,
        send_message_func: Callable[[int, bytes], None],
        segment_id: int = 0,
        logger: Optional[logging.Logger] = None,
        time_func: Callable[[], float] = time.time,
    ):
        self.device_id = device_id
        self.segment_id = segment_id
        self.name = name
        self.entity_id = entity_id
        self._send_message = send_message_func
        self._now = time_func
        self.logger = logger or logging.getLogger(f"{__name__}.{entity_id}")

        address = build_address_byte(device_id, segment_id)
        self.command_id = SOURCE_SELECTOR_COMMAND_PREFIX | address
        self.output_state_id = SOURCE_SELECTOR_OUTPUT_STATE_PREFIX | address
        self.engine_state_id = SOURCE_SELECTOR_ENGINE_STATE_PREFIX | address
        self.phase_id = SOURCE_SELECTOR_PHASE_PREFIX | address
        self.ac_measurement_id = SOURCE_SELECTOR_AC_PREFIX | address
        self.dc_measurement_id = SOURCE_SELECTOR_DC_PREFIX | address

        self._engine_state: Optional[int] = None
        self._phase: Optional[int] = None
        self._start_pulse_since: Optional[float] = None
        self._stop_pulse_since: Optional[float] = None
        self._last_running: Optional[bool] = None
        self._observers: List[Callable[[Dict[str, Any]], None]] = []

        big16 = {"bit_length": 16, "endian": "big"}
        self.voltage_sensor = create_sensor_output(
            "voltage",
            f"{name} voltage",
            f"{entity_id}_voltage",
            Matcher(pattern=self.ac_measurement_id, mask=0xFFFFFFFF),
            ValueConfig(start_byte=0, scale=1.0, **big16),
        )
        self.frequency_sensor = create_sensor_output(
            "frequency",
            f"{name} frequency",
            f"{entity_id}_frequency",
            Matcher(pattern=self.ac_measurement_id, mask=0xFFFFFFFF),
            ValueConfig(start_byte=2, scale=1.0, **big16),
        )
        self.battery_voltage_sensor = create_sensor_output(
            "voltage",
            f"{name} battery voltage",
            f"{entity_id}_battery_voltage",
            Matcher(pattern=self.dc_measurement_id, mask=0xFFFFFFFF),
            ValueConfig(start_byte=0, scale=0.1, **big16),
        )

    # ------------------------------------------------------------------
    # Matchers and message processing
    # ------------------------------------------------------------------

    def get_matchers(self) -> List[Matcher]:
        """Matchers for every frame this control decodes (plus the command echo)."""
        return [
            Matcher(pattern=arbitration_id, mask=0xFFFFFFFF)
            for arbitration_id in (
                self.output_state_id,
                self.engine_state_id,
                self.phase_id,
                self.ac_measurement_id,
                self.dc_measurement_id,
                self.command_id,
            )
        ]

    def get_sensors(self) -> List[SensorOutput]:
        """Built-in measurement sensors of the generator interface."""
        return [
            self.voltage_sensor,
            self.frequency_sensor,
            self.battery_voltage_sensor,
        ]

    def process_message(self, msg: can.Message) -> bool:
        """Decode one frame from the node. Returns True when the frame was known."""
        arbitration_id = msg.arbitration_id
        data = bytes(msg.data)

        if arbitration_id == self.output_state_id:
            self._process_output_state(msg)
        elif arbitration_id == self.engine_state_id:
            if data:
                self._engine_state = data[0]
                self.logger.debug(f"Engine state byte 0x{data[0]:02X}")
        elif arbitration_id == self.phase_id:
            if data:
                self._phase = data[0]
                self.logger.info(f"Generator phase 0x{data[0]:02X} ({self.phase_name})")
                # The phase byte is sent together with the relay release, so it
                # doubles as a fallback when the output-state frame is missed.
                if data[0] in (0x01, 0x00):
                    self._start_pulse_since = None
                    self._stop_pulse_since = None
        elif arbitration_id == self.ac_measurement_id:
            self._process_ac_measurement(data)
        elif arbitration_id == self.dc_measurement_id:
            self.battery_voltage_sensor.process_message(msg)
        elif arbitration_id == self.command_id:
            # Command echo (ours or the panel's). Known, nothing to decode.
            if data:
                self.logger.info(f"Generator command 0x{data[0]:02X} seen on bus")
        else:
            return False

        self._notify_if_changed()
        return True

    def _process_output_state(self, msg: can.Message) -> None:
        start_relay = Output.decode_output_frame(msg, 0)
        stop_relay = Output.decode_output_frame(msg, 1)
        if start_relay is None or stop_relay is None:
            self.logger.warning(
                f"Short output-state frame from generator node: {bytes(msg.data).hex()}"
            )
            return
        now = self._now()
        if start_relay["energised"]:
            if self._start_pulse_since is None:
                self.logger.info("Generator start relay closed")
                self._start_pulse_since = now
        else:
            if self._start_pulse_since is not None:
                self.logger.info("Generator start relay released")
            self._start_pulse_since = None
        if stop_relay["energised"]:
            if self._stop_pulse_since is None:
                self.logger.info("Generator stop relay closed")
                self._stop_pulse_since = now
        else:
            if self._stop_pulse_since is not None:
                self.logger.info("Generator stop relay released")
            self._stop_pulse_since = None

    def _process_ac_measurement(self, data: bytes) -> None:
        if len(data) < 4:
            self.logger.warning(
                f"Short AC measurement frame from generator node: {data.hex()}"
            )
            return
        voltage = float(int.from_bytes(data[0:2], "big"))
        frequency = float(int.from_bytes(data[2:4], "big"))
        if frequency != 0.0 and not (FREQUENCY_MIN_HZ <= frequency <= FREQUENCY_MAX_HZ):
            self.logger.debug(f"Ignoring generator frequency transient {frequency} Hz")
            return
        self.voltage_sensor.set_value(round(voltage, 2))
        self.frequency_sensor.set_value(round(frequency, 2))

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    @property
    def start_pulse_active(self) -> bool:
        """True while the start relay is (believed to be) closed."""
        return self._pulse_active(self._start_pulse_since, START_PULSE_EXPIRY_S)

    @property
    def stop_pulse_active(self) -> bool:
        """True while the stop relay is (believed to be) closed."""
        return self._pulse_active(self._stop_pulse_since, STOP_PULSE_EXPIRY_S)

    def _pulse_active(self, since: Optional[float], expiry: float) -> bool:
        if since is None:
            return False
        if self._now() - since > expiry:
            self.logger.warning(
                "Relay release frame not seen within %.0f s, assuming released",
                expiry,
            )
            return False
        return True

    @property
    def running(self) -> Optional[bool]:
        """
        Generator running state, or None while unknown.

        The engine-state frame is authoritative once seen. Before that (after a
        restart) the generator output frequency, which repeats at ~2 Hz, is used.
        """
        if self._engine_state is not None:
            return bool(self._engine_state & ENGINE_RUNNING_BIT)
        frequency = self.frequency_sensor.get_value()
        if frequency is None:
            return None
        return float(frequency) >= RUNNING_FREQUENCY_HZ

    @property
    def phase(self) -> Optional[int]:
        """Raw control phase byte from the node, or None if not seen yet."""
        return self._phase

    @property
    def phase_name(self) -> Optional[str]:
        """Human-readable phase, falling back to the running state."""
        if self._phase is not None:
            return PHASE_NAMES.get(self._phase, f"unknown_0x{self._phase:02X}")
        running = self.running
        if running is None:
            return None
        return "running" if running else "stopped"

    @property
    def engine_state(self) -> Optional[int]:
        """Raw engine state byte from the node, or None if not seen yet."""
        return self._engine_state

    def get_state(self) -> Dict[str, Any]:
        """Snapshot of the derived state for observers and entities."""
        return {
            "running": self.running,
            "phase": self.phase_name,
            "start_pulse_active": self.start_pulse_active,
            "stop_pulse_active": self.stop_pulse_active,
        }

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Send the start command (refused by the interlock when unsafe)."""
        self._check_interlock(want_running=True)
        self.logger.info(f"Sending generator START (0x{self.command_id:08X} 01)")
        self._send_message(self.command_id, bytes([GENERATOR_COMMAND_START]))

    def stop(self) -> None:
        """Send the stop command (refused by the interlock when unsafe)."""
        self._check_interlock(want_running=False)
        self.logger.info(f"Sending generator STOP (0x{self.command_id:08X} 02)")
        self._send_message(self.command_id, bytes([GENERATOR_COMMAND_STOP]))

    def set(self, running: bool) -> None:
        """Switch-style API: True starts, False stops."""
        if running:
            self.start()
        else:
            self.stop()

    def _check_interlock(self, want_running: bool) -> None:
        action = "start" if want_running else "stop"
        if self.start_pulse_active:
            raise GeneratorInterlockError(
                f"Refusing to {action} generator: start relay pulse still active"
            )
        if self.stop_pulse_active:
            raise GeneratorInterlockError(
                f"Refusing to {action} generator: stop relay pulse still active"
            )
        running = self.running
        if running is None:
            raise GeneratorInterlockError(
                f"Refusing to {action} generator: state unknown (no frames from node "
                f"0x{self.ac_measurement_id:08X} yet)"
            )
        if running == want_running:
            state = "running" if running else "stopped"
            raise GeneratorInterlockError(
                f"Refusing to {action} generator: it is already {state}"
            )

    # ------------------------------------------------------------------
    # Observer pattern
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._observers:
            self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback in self._observers:
            self._observers.remove(callback)

    def _notify_if_changed(self) -> None:
        state = self.get_state()
        if state == getattr(self, "_last_state", None):
            return
        self._last_state = state
        for callback in list(self._observers):
            try:
                callback(state)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.error(f"Generator observer failed: {exc}")
