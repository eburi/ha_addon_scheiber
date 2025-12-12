"""
Basic ON/OFF switch component.

Provides simple boolean state control with observer pattern for notifications.
"""

from typing import Any, Callable, Dict, List, Optional
import logging


class Switch:
    """
    Basic ON/OFF switch.

    Provides:
    - Simple set(state) method for ON/OFF control
    - Observer pattern for state change notifications
    - State query
    """

    def __init__(
        self,
        device_id: int,
        switch_nr: int,
        name: str,
        entity_id: str,
        send_command_func: Callable[[int, bool, Optional[int]], None],
        logger: Optional[logging.Logger] = None,
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
        """
        self.device_id = device_id
        self.switch_nr = switch_nr
        self.name = name
        self.entity_id = entity_id
        self.send_command_func = send_command_func
        self.logger = logger or logging.getLogger(f"Switch.{device_id}.{name}")

        self._state = False
        self._observers: List[Callable[[Dict[str, Any]], None]] = []

    def set(self, state: bool) -> None:
        """
        Turn switch ON or OFF.

        Args:
            state: True for ON, False for OFF
        """
        self._state = state
        self._send_command(state)
        self._notify_observers({"state": state})

    def get_state(self) -> bool:
        """
        Get current switch state.

        Returns:
            Current state (True=ON, False=OFF)
        """
        return self._state

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to state changes.

        Args:
            callback: Function called as callback(state_dict) with changed properties
        """
        if callback not in self._observers:
            self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Unsubscribe from state changes.

        Args:
            callback: Previously subscribed callback
        """
        if callback in self._observers:
            self._observers.remove(callback)

    def _notify_observers(self, state: Dict[str, Any]) -> None:
        """Notify all observers with state dict containing changed properties."""
        for observer in self._observers:
            try:
                observer(state)
            except Exception as e:
                self.logger.error(f"Error in observer callback: {e}")

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

    def __str__(self) -> str:
        """String representation."""
        return f"Switch({self.name}, state={'ON' if self._state else 'OFF'})"
