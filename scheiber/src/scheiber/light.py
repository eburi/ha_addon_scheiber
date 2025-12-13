"""
Dimmable light component with transitions and flash effects.

Inherits from Output base class for CAN message processing.
"""

from typing import Any, Callable, Dict, Optional
import logging
import can

from .output import Output
from .transitions import TransitionController, FlashController


class DimmableLight(Output):
    """
    Dimmable light with brightness control, transitions, and flash effects.

    Inherits from Output and adds brightness control, transitions, and flash capabilities.
    """

    def __init__(
        self,
        device_id: int,
        switch_nr: int,
        name: str,
        entity_id: str,
        send_command_func: Callable,
        logger: Optional[logging.Logger] = None,
        dimming_threshold: int = 2,
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
            dimming_threshold: Threshold for considering brightness as ON
        """
        super().__init__(
            device_id, switch_nr, name, entity_id, send_command_func, logger
        )
        self._send_command = send_command_func
        self.dimming_threshold = dimming_threshold

        # Brightness state
        self._brightness = 0

        # Default easing for transitions (can be set via effect parameter)
        self._default_easing = "ease_in_out_sine"

        # Controllers
        self.transition_controller = TransitionController(self)
        self.flash_controller = FlashController(self)

    def set(
        self,
        state: bool,
        brightness: Optional[int] = None,
        flash: float = 0.0,
        fade_to: Optional[int] = None,
        fade_duration: float = 1.0,
        fade_easing: Optional[str] = None,
        effect: Optional[str] = None,
    ) -> None:
        """
        Control light with multiple options.

        Args:
            state: True=ON, False=OFF
            brightness: 0-255 (None=use previous, 0=OFF)
            flash: Flash duration in seconds (overrides other params)
            fade_to: Target brightness for fade (None=no fade)
            fade_duration: Fade duration in seconds
            fade_easing: Easing function name (overrides effect)
            effect: Effect name (stores as default easing for future transitions)
        """
        # Store effect as default easing if provided
        if effect:
            self._default_easing = effect
            self.logger.debug(f"Default easing set to: {effect}")

        # Determine easing: explicit fade_easing > effect > stored default
        easing = (
            fade_easing if fade_easing else (effect if effect else self._default_easing)
        )

        # Flash takes priority
        if flash > 0:
            self.flash(flash)
            return

        # Fade takes priority over immediate set
        if fade_to is not None:
            self.fade_to(fade_to, fade_duration, easing)
            return

        # If effect is sent with brightness, use it for transition
        if effect and brightness is not None:
            # Use effect as easing for transition to new brightness
            self.fade_to(brightness, fade_duration, easing)
            return

        # If only effect with state=ON (no brightness), just store it - don't change light
        if effect and brightness is None and state:
            # Effect stored above, don't change light state
            self.logger.debug(f"Stored effect '{effect}' without changing light state")
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
        self.transition_controller.cancel_transition()
        self.flash_controller.cancel_flash()

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

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """
        Restore light state from persisted data.

        Args:
            state: Dictionary with 'brightness' and 'state' keys
        """
        brightness = state.get("brightness", 0)
        # Restore without sending command (will sync on first CAN message)
        self._brightness = brightness
        self._state = brightness > 0
        self.logger.debug(f"Restored state: brightness={brightness}")

    def store_to_state(self) -> Dict[str, Any]:
        """
        Return current state for persistence.

        Returns:
            Dictionary with 'brightness' and 'state' keys
        """
        return {
            "brightness": self._brightness,
            "state": self._state,
        }

        # Send CAN command
        self._send_command(self.switch_nr, state, brightness)

        # Notify observers with complete state
        if notify:
            self._notify_observers({"state": state, "brightness": brightness})

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
        start_brightness = self._brightness

        self.transition_controller.start_transition(
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
        previous_state = self._state
        previous_brightness = self._brightness

        self.flash_controller.start_flash(
            duration=duration,
            previous_state=previous_state,
            previous_brightness=previous_brightness,
            on_complete=on_complete,
        )

    def cancel_transition(self) -> None:
        """Cancel any active transition."""
        self.transition_controller.cancel_transition()

    def cancel_flash(self) -> None:
        """Cancel any active flash."""
        self.flash_controller.cancel_flash()

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

    def process_matching_message(self, msg: can.Message) -> None:
        """
        Process a CAN message that matched this light's matcher.

        Extracts state and brightness from the message and updates internal state.

        Args:
            msg: CAN message
        """
        state, brightness = self.get_state_from_can_message(
            msg, self.switch_nr, self.dimming_threshold
        )

        self.logger.debug(
            f"Light '{self.name}' (S{self.switch_nr+1}) received matched message: "
            f"arbitration_id=0x{msg.arbitration_id:08X}, state={state}, brightness={brightness}"
        )

        self.update_state(state, brightness)

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
