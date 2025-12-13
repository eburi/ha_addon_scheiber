"""
Basic ON/OFF switch component.

Provides simple boolean state control with observer pattern for notifications.
"""

from typing import Any, Callable, Dict, Optional
import logging
import can

from .output import Output


class Switch(Output):
    """
    Basic ON/OFF switch.

    Provides:
    - Simple set(state) method for ON/OFF control
    - Observer pattern for state change notifications
    - State query
    - CAN message processing
    """

    def __init__(
        self,
        device_id: int,
        switch_nr: int,
        name: str,
        entity_id: str,
        send_command_func: Callable[[int, bool, Optional[int]], None],
        logger: Optional[logging.Logger] = None,
        dimming_threshold: int = 2,
    ):
        """
        Initialize switch.

        Args:
            device_id: Parent device ID
            switch_nr: Switch number (0-indexed)
            name: Human-readable name (e.g., 's1', 's2')
            entity_id: Entity ID for Home Assistant (without domain prefix)
            send_command_func: Callback to send CAN command (switch_nr, state, optional brightness)
            logger: Optional logger
            dimming_threshold: Threshold for considering brightness as ON
        """
        super().__init__(
            device_id, switch_nr, name, entity_id, send_command_func, logger
        )
        self.send_command_func = send_command_func
        self.dimming_threshold = dimming_threshold

    def set(self, state: bool) -> None:
        """
        Turn switch ON or OFF.

        Args:
            state: True for ON, False for OFF
        """
        self._state = state
        self._send_command(state)
        self._notify_observers({"state": state})

    def process_matching_message(self, msg: can.Message) -> None:
        """
        Process a CAN message that matched this switch's matcher.

        Extracts state from the message and updates internal state.

        Args:
            msg: CAN message
        """
        state, brightness = self.get_state_from_can_message(
            msg, self.switch_nr, self.dimming_threshold
        )
        # Switch ignores brightness, only cares about state
        self.update_state(state)

    def get_state(self) -> bool:
        """
        Get current switch state.

        Returns:
            Current state (True=ON, False=OFF)
        """
        return self._state

    def _send_command(self, state: bool) -> None:
        """
        Send CAN command to switch device via callback.

        Args:
            state: Desired state
        """
        self.send_command_func(self.switch_nr, state)

    def update_state(self, state: bool) -> None:
        """
        Update state from received CAN message (without sending command).

        Args:
            state: New state from CAN bus
        """
        if self._state != state:
            self._state = state
            self._notify_observers({"state": state})
