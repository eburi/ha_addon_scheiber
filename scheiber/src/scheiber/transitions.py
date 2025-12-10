"""
Transition and flash controllers for smooth brightness changes.

These controllers were originally in scheiber_device.py and are kept
as-is for compatibility.
"""

import threading
import time
import math
from typing import Callable, Optional
import logging


class TransitionController:
    """Manages smooth transitions for dimmable outputs using easing functions."""

    def __init__(self, device, step_delay: float = 0.02):
        self.device = device
        self.step_delay = step_delay
        self.active_transitions = {}
        self.lock = threading.Lock()

    def start_transition(
        self,
        property_name: str,
        switch_nr: int,
        start_brightness: int,
        end_brightness: int,
        duration: float,
        easing_name: str = "ease_in_out_sine",
        on_step: Optional[Callable[[int], None]] = None,
    ):
        """
        Start a smooth transition for a dimmable output.

        Args:
            property_name: Name of the property (e.g., 's1')
            switch_nr: Switch number (0-5)
            start_brightness: Starting brightness (0-255)
            end_brightness: Target brightness (0-255)
            duration: Transition duration in seconds
            easing_name: Name of the easing function to use
            on_step: Optional callback for each step (receives brightness)
        """
        self.cancel_transition(property_name)

        stop_event = threading.Event()
        self.active_transitions[property_name] = stop_event

        def run_transition():
            try:
                steps = max(1, int(duration / self.step_delay))
                easing_func = self._get_easing_function(easing_name)
                for step in range(steps + 1):
                    if stop_event.is_set():
                        logging.info(
                            f"Transition for {property_name} cancelled at step {step}"
                        )
                        return
                    t = step / steps
                    value = int(
                        round(
                            start_brightness
                            + (end_brightness - start_brightness) * easing_func(t)
                        )
                    )
                    # Use internal _set_brightness to avoid canceling ourselves
                    self.device._set_brightness(switch_nr, value, notify=False)
                    if on_step:
                        on_step(value)
                    time.sleep(self.step_delay)
                logging.info(
                    f"Transition for {property_name} completed: {start_brightness} -> {end_brightness}"
                )
            except Exception as e:
                logging.error(
                    f"Error in transition for {property_name}: {e}", exc_info=True
                )
            finally:
                with self.lock:
                    if property_name in self.active_transitions:
                        del self.active_transitions[property_name]

        threading.Thread(target=run_transition, daemon=True).start()

    def cancel_transition(self, property_name: str):
        """Cancel any active transition for the given property."""
        with self.lock:
            stop_event = self.active_transitions.pop(property_name, None)
        if stop_event:
            stop_event.set()

    def _get_easing_function(self, name: str) -> Callable[[float], float]:
        """Return an easing function by name."""
        if name == "ease_in_out_sine":
            return lambda t: -(math.cos(math.pi * t) - 1) / 2
        elif name == "ease_in_cubic":
            return lambda t: t**3
        elif name == "ease_out_cubic":
            return lambda t: 1 - (1 - t) ** 3
        else:
            return lambda t: t  # Linear fallback


class FlashController:
    """Manages flash effects for outputs with state restore."""

    def __init__(self, device, flash_transition_length: float = 0.25):
        self.device = device
        self.flash_transition_length = flash_transition_length
        self.active_flashes = {}
        self.stop_events = {}
        self.lock = threading.Lock()

    def start_flash(
        self,
        property_name: str,
        switch_nr: int,
        duration: float,
        previous_state: bool,
        previous_brightness: int,
        on_complete: Optional[Callable[[], None]] = None,
    ):
        """
        Start a flash effect for a given output, then restore previous state.

        Args:
            property_name: Name of the property (e.g., 's1')
            switch_nr: Switch number (0-5)
            duration: Flash duration in seconds
            previous_state: State to restore after flash
            previous_brightness: Brightness to restore after flash
            on_complete: Optional callback after restore
        """
        self.cancel_flash(property_name)

        stop_event = threading.Event()
        with self.lock:
            self.stop_events[property_name] = stop_event
            self.active_flashes[property_name] = stop_event

        def run_flash():
            try:
                # Phase 1: Flash ON at full brightness
                self.device._send_switch_command(switch_nr, True, brightness=255)
                logging.debug(f"Flash {property_name}: ON @ 255")

                elapsed = 0.0
                check_interval = 0.05
                while elapsed < duration:
                    if stop_event.is_set():
                        logging.warning(
                            f"Flash interrupted for {property_name} after {elapsed:.1f}s"
                        )
                        return

                    sleep_time = min(check_interval, duration - elapsed)
                    time.sleep(sleep_time)
                    elapsed += sleep_time

                # Phase 2: Restore to previous state
                if stop_event.is_set():
                    logging.warning(
                        f"Flash interrupted for {property_name} before restore"
                    )
                    return

                self.device._send_switch_command(
                    switch_nr, previous_state, brightness=previous_brightness
                )
                logging.debug(
                    f"Flash {property_name}: restored to state={previous_state}, brightness={previous_brightness}"
                )

                # Invoke completion callback
                if on_complete:
                    on_complete()

                logging.info(f"Completed flash for {property_name}")

            except Exception as e:
                logging.error(
                    f"Error during flash for {property_name}: {e}", exc_info=True
                )

            finally:
                # Clean up
                with self.lock:
                    if property_name in self.active_flashes:
                        del self.active_flashes[property_name]
                    if property_name in self.stop_events:
                        del self.stop_events[property_name]

        threading.Thread(target=run_flash, daemon=True).start()

    def cancel_flash(self, property_name: str):
        """Cancel any active flash for the given property."""
        with self.lock:
            stop_event = self.stop_events.pop(property_name, None)
        if stop_event:
            stop_event.set()
