"""
Base class for Bloc9 outputs (lights and switches).

Provides common functionality for CAN message matching and state decoding.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import can


class Output:
    """
    Base class for Bloc9 outputs.

    Each output corresponds to one physical switch on the Bloc9 device (S1-S6).
    Outputs can be lights (with brightness) or switches (ON/OFF only).
    """

    #: Number of stale-setpoint observations within STALE_WINDOW_SECONDS before an
    #: output is reported as stale. A stuck Bloc9 repeats the pattern every ~8.5s,
    #: so three observations is roughly 25 seconds of sustained misbehaviour. This
    #: is deliberately above one so a single odd frame during a ramp cannot trip it.
    STALE_MIN_OBSERVATIONS = 3

    #: Sliding window in which STALE_MIN_OBSERVATIONS must occur.
    STALE_WINDOW_SECONDS = 120.0

    #: A stale output is considered recovered once this many seconds pass with no
    #: further stale observation. A healthy Bloc9 only emits output status frames
    #: on change, so recovery is detected as sustained silence rather than a
    #: positive signal. Recovery is polled from the device heartbeat (~1 Hz).
    STALE_RECOVERY_SECONDS = 60.0

    def __init__(
        self,
        device_id: int,
        switch_nr: int,
        name: str,
        entity_id: str,
        send_command_func: Callable,
        segment_id: int = 0,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize output.

        Args:
            device_id: Parent device ID (bus ID)
            switch_nr: Switch number (0-5 for S1-S6)
            name: Human-readable name
            entity_id: Entity ID for Home Assistant
            send_command_func: Function to send CAN commands
            segment_id: Parent device segment ID
            logger: Optional logger
        """
        self.device_id = device_id
        self.segment_id = segment_id
        self.switch_nr = switch_nr
        self.name = name
        self.entity_id = entity_id
        self._send_command_func = send_command_func
        output_device_slug = (
            f"{device_id}" if segment_id == 0 else f"{device_id}_{segment_id}"
        )
        self.logger = logger or logging.getLogger(f"Output.{output_device_slug}.{name}")

        # State
        self._state = False

        # Stale-setpoint detection (see STALE_* class constants)
        self._stale_observations: List[float] = []
        self._stale = False
        self._stale_last_seen: Optional[float] = None
        self._stale_brightness: Optional[int] = None

        # Observers
        self._observers: List[Callable[[Dict[str, Any]], None]] = []

    def get_matchers(self):
        """
        Return CAN message matchers for this output's state change messages.

        Returns:
            List of Matcher objects
        """
        from .matchers import Matcher

        # Determine which message type based on switch number
        # S1/S2: 0x02160600, S3/S4: 0x02180600, S5/S6: 0x021A0600
        if self.switch_nr in (0, 1):  # S1, S2
            base_pattern = 0x02160600
            property_name = "s1_s2_change"
        elif self.switch_nr in (2, 3):  # S3, S4
            base_pattern = 0x02180600
            property_name = "s3_s4_change"
        elif self.switch_nr in (4, 5):  # S5, S6
            base_pattern = 0x021A0600
            property_name = "s5_s6_change"
        else:
            return []

        from .discovery import build_bloc9_address_byte

        # Add device route to pattern (same addressing as commands)
        pattern = base_pattern | build_bloc9_address_byte(
            self.device_id, self.segment_id
        )

        return [Matcher(pattern=pattern, mask=0xFFFFFFFF)]

    @staticmethod
    def decode_output_frame(
        msg: can.Message, switch_nr: int
    ) -> Optional[Dict[str, Any]]:
        """
        Decode one output's four bytes from a Bloc9 status frame.

        Per-output layout is [brightness, reserved, mode_byte, state_byte]:
        bytes 0-3 for the lower output (S1/S3/S5), bytes 4-7 for the higher
        output (S2/S4/S6).

        Args:
            msg: CAN message with 8 bytes
            switch_nr: Switch number (0-5)

        Returns:
            Dict with brightness, mode_byte, state_byte and energised, or None
            if the frame is too short.
        """
        if len(msg.data) < 8:
            return None

        offset = 0 if switch_nr % 2 == 0 else 4
        mode_byte = msg.data[offset + 2]
        state_byte = msg.data[offset + 3]

        return {
            "brightness": msg.data[offset],
            "mode_byte": mode_byte,
            "state_byte": state_byte,
            # Bit 0 of either byte means the output is actually energised.
            "energised": bool(mode_byte & 0x01) or bool(state_byte & 0x01),
        }

    @staticmethod
    def get_state_from_can_message(
        msg: can.Message, switch_nr: int, dimming_threshold: int = 2
    ) -> Tuple[bool, int]:
        """
        Decode state and brightness from CAN message.

        CAN message format (8 bytes), four bytes per output:
            Bytes 0-3: Lower switch (even switch_nr: 0, 2, 4)
                - Byte 0: Brightness level
                - Byte 1: Reserved (always 0x00 observed)
                - Byte 2, bit 0: Mode/energised bit
                - Byte 3, bit 0: ON/OFF state bit
            Bytes 4-7: Higher switch (odd switch_nr: 1, 3, 5)
                - Byte 4: Brightness level
                - Byte 5: Reserved (always 0x00 observed)
                - Byte 6, bit 0: Mode/energised bit
                - Byte 7, bit 0: ON/OFF state bit

        The mode byte mirrors the command mode bytes: 0x00 off, 0x01 full on,
        0x11 PWM dimming on. Bit 0 means "output energised". A value of 0x10 is
        "PWM configured but NOT energised" and must be treated as OFF even when
        the brightness byte carries a stale or ramping setpoint.

        Brightness alone is NOT a reliable ON indicator: a faulty or
        de-energised output can report a non-zero brightness setpoint
        indefinitely. Conversely, during a dim ramp the state bit lags behind
        while the mode bit is already set, so both bits are OR-ed together.

        Args:
            msg: CAN message with 8 bytes
            switch_nr: Switch number (0-5)
            dimming_threshold: Deprecated, retained for signature compatibility

        Returns:
            Tuple of (state: bool, brightness: int)
        """
        frame = Output.decode_output_frame(msg, switch_nr)
        if frame is None:
            return (False, 0)

        state = frame["energised"]

        # Suppress stale/ramping brightness setpoints from de-energised outputs.
        brightness = frame["brightness"] if state else 0

        return (state, brightness)

    def decode_and_track(self, msg: can.Message) -> Tuple[bool, int]:
        """
        Decode this output's state and feed the stale-setpoint detector.

        Args:
            msg: CAN message that matched this output

        Returns:
            Tuple of (state: bool, brightness: int)
        """
        frame = self.decode_output_frame(msg, self.switch_nr)
        if frame is None:
            return (False, 0)

        self._note_stale_sample(frame)

        state = frame["energised"]
        return (state, frame["brightness"] if state else 0)

    def _note_stale_sample(
        self, frame: Dict[str, Any], now: Optional[float] = None
    ) -> None:
        """
        Record one status frame for stale-setpoint detection.

        A de-energised output reporting a non-zero brightness setpoint is
        abnormal. Seen once it is harmless, but a Bloc9 stuck in a hold-to-dim
        cycle repeats it indefinitely while the lamp stays dark. Sustained
        repetition is what we report.

        Args:
            frame: Result of decode_output_frame()
            now: Monotonic timestamp, injectable for tests
        """
        if now is None:
            now = time.monotonic()

        if frame["energised"] or frame["brightness"] == 0:
            # Healthy sample. Does not clear an active report on its own: the
            # stuck cycle alternates phantom and clean-off frames, so clearing
            # here would flap. Recovery is handled by check_stale_recovery().
            return

        cutoff = now - self.STALE_WINDOW_SECONDS
        self._stale_observations = [t for t in self._stale_observations if t >= cutoff]
        self._stale_observations.append(now)
        self._stale_last_seen = now
        self._stale_brightness = frame["brightness"]

        if self._stale or len(self._stale_observations) < self.STALE_MIN_OBSERVATIONS:
            return

        self._stale = True
        self.logger.warning(
            f"Output '{self.name}' (S{self.switch_nr + 1}) on bloc9 "
            f"{self._route_slug()} appears STALE: reported a non-zero brightness "
            f"setpoint ({frame['brightness']}) while de-energised "
            f"(mode=0x{frame['mode_byte']:02X}, state=0x{frame['state_byte']:02X}) "
            f"{len(self._stale_observations)} times in the last "
            f"{self.STALE_WINDOW_SECONDS:.0f}s. The physical output is OFF. This "
            f"matches a Bloc9 stuck in a hold-to-dim cycle; pressing the bound air "
            f"switch has been observed to clear it."
        )

    def check_stale_recovery(self, now: Optional[float] = None) -> None:
        """
        Clear a stale report once the output has been quiet long enough.

        A healthy Bloc9 only emits output status frames on change, so a
        recovered output goes silent rather than sending a positive all-clear.
        Call this periodically; the device heartbeat (~1 Hz) is a good clock.

        Args:
            now: Monotonic timestamp, injectable for tests
        """
        if not self._stale:
            return

        if now is None:
            now = time.monotonic()

        if self._stale_last_seen is None:
            return

        quiet_for = now - self._stale_last_seen
        if quiet_for < self.STALE_RECOVERY_SECONDS:
            return

        self._stale = False
        self._stale_observations.clear()
        self._stale_brightness = None
        self.logger.info(
            f"Output '{self.name}' (S{self.switch_nr + 1}) on bloc9 "
            f"{self._route_slug()} RECOVERED: no stale brightness setpoint for "
            f"{quiet_for:.0f}s."
        )

    def is_stale(self) -> bool:
        """Return True while this output is reporting a stale brightness setpoint."""
        return self._stale

    def _route_slug(self) -> str:
        """Format this output's parent device route for log messages."""
        return (
            f"{self.device_id}"
            if self.segment_id == 0
            else f"{self.device_id}_{self.segment_id}"
        )

    def process_matching_message(self, msg: can.Message) -> None:
        """
        Process a CAN message that matched this output's matcher.

        Args:
            msg: CAN message
        """
        raise NotImplementedError("Subclasses must implement process_matching_message")

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to state changes.

        Args:
            callback: Function called as callback(state_dict) with changed properties
        """
        if callback not in self._observers:
            self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Unsubscribe from changes."""
        if callback in self._observers:
            self._observers.remove(callback)

    def _notify_observers(self, state: Dict[str, Any]) -> None:
        """Notify all observers with state dict containing changed properties."""
        for observer in self._observers:
            try:
                observer(state)
            except Exception as e:
                self.logger.error(f"Error in observer callback: {e}")

    def get_state(self) -> Any:
        """Get current state (to be overridden by subclasses)."""
        return self._state

    def __str__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}({self.name}, state={'ON' if self._state else 'OFF'})"
