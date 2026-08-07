"""
Base class for Bloc9 outputs (lights and switches).

Provides common functionality for CAN message matching and state decoding.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import can


class Output:
    """
    Base class for Bloc9 outputs.

    Each output corresponds to one physical switch on the Bloc9 device (S1-S6).
    Outputs can be lights (with brightness) or switches (ON/OFF only).
    """

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
        if len(msg.data) < 8:
            return (False, 0)

        # Use parity to determine which 4 bytes to read
        if switch_nr % 2 == 0:  # Even: S1, S3, S5 (lower switch, bytes 0-3)
            offset = 0
        else:  # Odd: S2, S4, S6 (higher switch, bytes 4-7)
            offset = 4

        brightness = msg.data[offset]
        mode_bit = (msg.data[offset + 2] & 0x01) == 0x01
        state_bit = (msg.data[offset + 3] & 0x01) == 0x01

        # The device is ON only when it reports itself as energised.
        state = mode_bit or state_bit

        # Suppress stale/ramping brightness setpoints from de-energised outputs.
        if not state:
            brightness = 0

        return (state, brightness)

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
