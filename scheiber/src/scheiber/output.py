"""
Base class for Bloc9 outputs (lights and switches).

Provides common functionality for CAN message matching and state decoding.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import logging
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
            logger: Optional logger
        """
        self.device_id = device_id
        self.switch_nr = switch_nr
        self.name = name
        self.entity_id = entity_id
        self._send_command_func = send_command_func
        self.logger = logger or logging.getLogger(f"Output.{device_id}.{name}")

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

        # Add device ID to pattern (with 0x80 bit set - same as command encoding)
        pattern = base_pattern | ((self.device_id << 3) | 0x80)

        return [Matcher(pattern=pattern, mask=0xFFFFFFFF)]

    @staticmethod
    def get_state_from_can_message(
        msg: can.Message, switch_nr: int, dimming_threshold: int = 2
    ) -> Tuple[bool, int]:
        """
        Decode state and brightness from CAN message.

        CAN message format (8 bytes):
            Bytes 0-3: Lower switch (even switch_nr: 0, 2, 4)
                - Byte 0: Brightness level
                - Byte 3, bit 0: ON/OFF state bit
            Bytes 4-7: Higher switch (odd switch_nr: 1, 3, 5)
                - Byte 4: Brightness level
                - Byte 7, bit 0: ON/OFF state bit

        Args:
            msg: CAN message with 8 bytes
            switch_nr: Switch number (0-5)
            dimming_threshold: Threshold for considering brightness as ON

        Returns:
            Tuple of (state: bool, brightness: int)
        """
        if len(msg.data) < 8:
            return (False, 0)

        # Use parity to determine which 4 bytes to read
        if switch_nr % 2 == 0:  # Even: S1, S3, S5 (lower switch, bytes 0-3)
            brightness = msg.data[0]
            state_bit = (msg.data[3] & 0x01) == 0x01
        else:  # Odd: S2, S4, S6 (higher switch, bytes 4-7)
            brightness = msg.data[4]
            state_bit = (msg.data[7] & 0x01) == 0x01

        # State determination: state bit OR brightness above threshold
        state = state_bit or brightness > dimming_threshold

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
