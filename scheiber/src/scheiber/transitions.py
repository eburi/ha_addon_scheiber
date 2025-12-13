"""
Transition and flash controllers for smooth brightness changes.

Designed for DimmableLight objects using proper object-oriented approach.
"""

import threading
import time
from typing import Callable, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from scheiber.light import DimmableLight

# Import easing functions from easing module
import sys
from pathlib import Path

# Add parent directory to path for easing import
sys.path.insert(0, str(Path(__file__).parent.parent))
from easing import get_easing_function


class TransitionController:
    """
    Manages smooth transitions for dimmable outputs using easing functions.

    Works with DimmableLight objects by calling their internal brightness setter
    without triggering state notifications during the transition.
    """

    def __init__(self, light: "DimmableLight", step_delay: float = 0.02):
        """
        Initialize transition controller.

        Args:
            light: DimmableLight instance
            step_delay: Delay between transition steps in seconds (50Hz = 0.02s)
        """
        self.light: "DimmableLight" = light
        self.step_delay = step_delay
        self.stop_event = None
        self.lock = threading.Lock()
        self.logger = (
            light.logger if hasattr(light, "logger") else logging.getLogger(__name__)
        )

    def start_transition(
        self,
        start_brightness: int,
        end_brightness: int,
        duration: float,
        easing_name: str = "ease_in_out_sine",
    ):
        """
        Start a smooth transition for a dimmable output.

        Args:
            start_brightness: Starting brightness (0-255)
            end_brightness: Target brightness (0-255)
            duration: Transition duration in seconds
            easing_name: Name of the easing function to use
        """
        self.cancel_transition()

        self.stop_event = threading.Event()

        def run_transition():
            try:
                steps = max(1, int(duration / self.step_delay))
                easing_func = get_easing_function(easing_name)

                for step in range(steps + 1):
                    if self.stop_event.is_set():
                        self.logger.info(
                            f"Transition for {self.light.name} cancelled at step {step}/{steps}"
                        )
                        return

                    # Calculate progress (0.0 to 1.0)
                    t = step / steps

                    # Apply easing function
                    eased_t = easing_func(t)

                    # Calculate brightness value
                    value = int(
                        round(
                            start_brightness
                            + (end_brightness - start_brightness) * eased_t
                        )
                    )

                    # Update brightness without triggering observers
                    # (observers are notified at the end)
                    brightness_val = max(0, min(255, value))

                    self.light._set_brightness(brightness_val, notify=False)

                    time.sleep(self.step_delay)

                # Notify observers once at the end with final state
                self.light._notify_observers(
                    {"state": self.light._state, "brightness": self.light._brightness}
                )

                self.logger.info(
                    f"Transition for {self.light.name} completed: {start_brightness} -> {end_brightness}"
                )
            except Exception as e:
                self.logger.error(
                    f"Error in transition for {self.light.name}: {e}", exc_info=True
                )
            finally:
                with self.lock:
                    self.stop_event = None

        threading.Thread(target=run_transition, daemon=True).start()

    def cancel_transition(self):
        """Cancel any active transition for this light."""
        with self.lock:
            stop_event = self.stop_event
            self.stop_event = None
        if stop_event:
            stop_event.set()


class FlashController:
    """
    Manages flash effects for outputs with state restore.

    Works with DimmableLight objects to flash at full brightness
    then restore previous state.
    """

    def __init__(self, light: "DimmableLight", flash_transition_length: float = 0.25):
        """
        Initialize flash controller.

        Args:
            light: DimmableLight instance
            flash_transition_length: Duration of flash (not currently used)
        """
        self.light: "DimmableLight" = light
        self.flash_transition_length = flash_transition_length
        self.stop_event = None
        self.lock = threading.Lock()
        self.logger = (
            light.logger if hasattr(light, "logger") else logging.getLogger(__name__)
        )

    def start_flash(
        self,
        duration: float,
        previous_state: bool,
        previous_brightness: int,
        on_complete: Optional[Callable[[], None]] = None,
    ):
        """
        Start a flash effect for a given output, then restore previous state.

        Args:
            duration: Flash duration in seconds
            previous_state: State to restore after flash
            previous_brightness: Brightness to restore after flash
            on_complete: Optional callback after restore
        """
        self.cancel_flash()

        with self.lock:
            self.stop_event = threading.Event()

        def run_flash():
            try:
                # Phase 1: Flash ON at full brightness
                self.light._set_brightness(255, notify=True)
                self.logger.debug(f"Flash {self.light.name}: ON @ 255")

                # Wait for flash duration with cancellation checks
                elapsed = 0.0
                check_interval = 0.05
                while elapsed < duration:
                    if self.stop_event.is_set():
                        self.logger.warning(
                            f"Flash interrupted for {self.light.name} after {elapsed:.1f}s"
                        )
                        return

                    sleep_time = min(check_interval, duration - elapsed)
                    time.sleep(sleep_time)
                    elapsed += sleep_time

                # Phase 2: Restore to previous state
                if self.stop_event.is_set():
                    self.logger.warning(
                        f"Flash interrupted for {self.light.name} before restore"
                    )
                    return

                self.light._set_brightness(previous_brightness, notify=True)
                self.logger.debug(
                    f"Flash {self.light.name}: restored to state={previous_state}, brightness={previous_brightness}"
                )

                # Invoke completion callback
                if on_complete:
                    on_complete()

                self.logger.info(f"Completed flash for {self.light.name}")

            except Exception as e:
                self.logger.error(
                    f"Error during flash for {self.light.name}: {e}", exc_info=True
                )

            finally:
                # Clean up
                with self.lock:
                    self.stop_event = None

        threading.Thread(target=run_flash, daemon=True).start()

    def cancel_flash(self):
        """Cancel any active flash for this light."""
        with self.lock:
            stop_event = self.stop_event
            self.stop_event = None
        if stop_event:
            stop_event.set()
