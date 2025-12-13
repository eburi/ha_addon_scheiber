"""
Dimmable light component with transitions and flash effects.

Uses composition to combine Switch functionality with brightness control,
transitions, and flash effects.
"""

from typing import Any, Callable, Dict, Optional
import logging

from .switch import Switch
from .transitions import TransitionController, FlashController


class DimmableLight:
    """
    Dimmable light with brightness control, transitions, and flash effects.

    Uses composition: contains a Switch and adds brightness/fade/flash capabilities.
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
        Initialize dimmable light.

        Args:
            device_id: Parent device ID
            switch_nr: Switch number (0-indexed)
            name: Human-readable name (e.g., 's1', 's2')
            entity_id: Entity ID for Home Assistant (without domain prefix)
            send_command_func: Function to send CAN commands: func(switch_nr, state, brightness)
            logger: Optional logger
        """
        self.device_id = device_id
        self.switch_nr = switch_nr
        self.name = name
        self.entity_id = entity_id
        self._send_command = send_command_func
        self.logger = logger or logging.getLogger(f"DimmableLight.{device_id}.{name}")

        # State
        self._state = False
        self._brightness = 0

        # Controllers
        self.transition_controller = TransitionController(self)
        self.flash_controller = FlashController(self)

        # Observers
        self._observers: list[Callable[[Dict[str, Any]], None]] = []

    def set(
        self,
        state: bool,
        brightness: Optional[int] = None,
        flash: float = 0.0,
        fade_to: Optional[int] = None,
        fade_duration: float = 1.0,
        fade_easing: str = "ease_in_out_sine",
    ) -> None:
        """
        Control light with multiple options.

        Args:
            state: True=ON, False=OFF
            brightness: 0-255 (None=use previous, 0=OFF)
            flash: Flash duration in seconds (overrides other params)
            fade_to: Target brightness for fade (None=no fade)
            fade_duration: Fade duration in seconds
            fade_easing: Easing function name
        """
        # Flash takes priority
        if flash > 0:
            self.flash(flash)
            return

        # Fade takes priority over immediate set
        if fade_to is not None:
            self.fade_to(fade_to, fade_duration, fade_easing)
            return

        # Immediate brightness change
        if brightness is not None:
            self.set_brightness(brightness)
        elif state:
            # Turn on with previous brightness (or default to max)
            self.set_brightness(self._brightness if self._brightness > 0 else 255)
        else:
            # Turn off
            self.set_brightness(0)

    def set_brightness(self, brightness: int) -> None:
        """
        Set brightness immediately (public API, cancels transitions).

        Args:
            brightness: 0-255 (0=OFF)
        """
        # Cancel any active transition or flash
        property_name = self.name
        self.transition_controller.cancel_transition(property_name)
        self.flash_controller.cancel_flash(property_name)

        # Set new brightness
        self._set_brightness(brightness, notify=True)

    def _set_brightness(self, brightness: int, notify: bool = True) -> None:
        """
        Internal brightness setter (used by set_brightness()).

        Args:
            brightness: 0-255
            notify: Whether to notify observers
        """
        brightness = max(0, min(255, brightness))
        state = brightness > 0

        self._state = state
        self._brightness = brightness

        # Send CAN command
        self._send_switch_command(self.switch_nr, state, brightness)

        # Notify observers with complete state
        if notify:
            self._notify_observers({"state": state, "brightness": brightness})

    def _send_switch_command(
        self, switch_nr: int, state: bool, brightness: int
    ) -> None:
        """Send CAN command via provided function."""
        self._send_command(switch_nr, state, brightness)

    def fade_to(
        self,
        target_brightness: int,
        duration: float = 1.0,
        easing: str = "ease_in_out_sine",
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Fade to target brightness over duration.

        Args:
            target_brightness: Target brightness (0-255)
            duration: Transition duration in seconds
            easing: Easing function name
            on_complete: Optional callback when complete
        """
        property_name = self.name
        start_brightness = self._brightness

        self.transition_controller.start_transition(
            property_name=property_name,
            start_brightness=start_brightness,
            end_brightness=target_brightness,
            duration=duration,
            easing_name=easing,
        )

        if on_complete:
            on_complete()

    def flash(
        self, duration: float = 2.0, on_complete: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Flash light ON briefly, then restore previous state.

        Args:
            duration: Flash duration in seconds
            on_complete: Optional callback when complete
        """
        property_name = self.name
        previous_state = self._state
        previous_brightness = self._brightness

        self.flash_controller.start_flash(
            property_name=property_name,
            duration=duration,
            previous_state=previous_state,
            previous_brightness=previous_brightness,
            on_complete=on_complete,
        )

    def cancel_transition(self) -> None:
        """Cancel any active transition."""
        self.transition_controller.cancel_transition(self.name)

    def cancel_flash(self) -> None:
        """Cancel any active flash."""
        self.flash_controller.cancel_flash(self.name)

    def get_state(self) -> Dict[str, Any]:
        """
        Get current state.

        Returns:
            Dict with 'state' and 'brightness'
        """
        return {
            "state": self._state,
            "brightness": self._brightness,
        }

    def is_on(self) -> bool:
        """
        Check if light is ON.

        Returns:
            True if light is ON, False if OFF
        """
        return self._state

    def get_brightness(self) -> int:
        """
        Get current brightness.

        Returns:
            Brightness value (0-255)
        """
        return self._brightness

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to state/brightness changes.

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

    def update_state(self, state: bool, brightness: int) -> None:
        """
        Update state from received CAN message (without sending command).

        Special handling for Bloc9 hardware quirk:
        - When Bloc9 is ON without PWM (full brightness), it reports: state=ON, brightness=0
        - This must be translated to: state=ON, brightness=255 for MQTT
        - For MQTT: brightness 0 = OFF, brightness > 0 = ON

        Args:
            state: New state from CAN bus
            brightness: New brightness from CAN bus
        """
        # Bloc9 hardware quirk: ON without PWM reports as state=ON, brightness=0
        # Translate this to brightness=255 for MQTT
        effective_brightness = brightness
        if state and brightness == 0:
            effective_brightness = 255

        # Effective state: OFF if brightness is 0, ON otherwise
        effective_state = effective_brightness > 0

        changed_props = {}
        if self._state != effective_state:
            self._state = effective_state
            changed_props["state"] = effective_state

        if self._brightness != effective_brightness:
            self._brightness = effective_brightness
            changed_props["brightness"] = effective_brightness

        if changed_props:
            translation_note = (
                f" (translated from brightness={brightness})"
                if brightness != effective_brightness
                else ""
            )
            self.logger.debug(
                f"State updated from CAN: {self.name} state={effective_state}, brightness={effective_brightness}{translation_note}"
            )
            self._notify_observers(changed_props)

    def __str__(self) -> str:
        """String representation."""
        return f"DimmableLight({self.name}, state={'ON' if self._state else 'OFF'}, brightness={self._brightness})"
