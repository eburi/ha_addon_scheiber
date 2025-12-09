#!/usr/bin/env python3
"""
Device class hierarchy for Scheiber CAN devices.

Base class ScheiberCanDevice provides common functionality.
Subclasses (Bloc9, etc.) add device-specific behavior including command handling.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import can

# Import the shared snake_case converter from config_loader
from config_loader import name_to_snake_case

# Import easing functions
from easing import get_easing_function


import threading
import time


class TransitionController:
    """
    Manages smooth brightness transitions with easing functions.

    This controller executes transitions in a background thread, allowing concurrent
    transitions for multiple lights. Each transition can use a different easing function
    to create natural-looking fade effects.
    """

    def __init__(self, device, step_delay: float = 0.1):
        """
        Initialize the transition controller.

        Args:
            device: The device instance (must have _send_switch_command method)
            step_delay: Time in seconds between brightness updates (default 100ms = 10Hz)
        """
        self.device = device
        self.step_delay = step_delay
        self.logger = logging.getLogger(f"{__name__}.TransitionController")

        # Track active transitions: {property_name: thread}
        self.active_transitions = {}

        # Lock for thread-safe access to active_transitions
        self.lock = threading.Lock()

        # Stop events for cancelling transitions: {property_name: Event}
        self.stop_events = {}

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
        Start a smooth brightness transition.

        Args:
            property_name: Name of the property (e.g., 's1')
            switch_nr: Switch number (0-5)
            start_brightness: Starting brightness (0-255)
            end_brightness: Target brightness (0-255)
            duration: Transition duration in seconds
            easing_name: Name of easing function to use
            on_step: Optional callback to invoke at each step with current brightness
        """
        # Cancel any existing transition for this property
        self.cancel_transition(property_name)

        # Create a new stop event
        stop_event = threading.Event()
        with self.lock:
            self.stop_events[property_name] = stop_event

        # Start transition in a new thread
        thread = threading.Thread(
            target=self._execute_transition,
            args=(
                property_name,
                switch_nr,
                start_brightness,
                end_brightness,
                duration,
                easing_name,
                stop_event,
                on_step,
            ),
            daemon=True,
            name=f"Transition-{property_name}",
        )

        with self.lock:
            self.active_transitions[property_name] = thread

        thread.start()
        self.logger.info(
            f"Started transition for {property_name}: {start_brightness} -> {end_brightness} "
            f"over {duration}s using {easing_name}"
        )

    def cancel_transition(self, property_name: str):
        """
        Cancel an active transition.

        Args:
            property_name: Name of the property to cancel transition for
        """
        with self.lock:
            # Signal the thread to stop
            if property_name in self.stop_events:
                self.stop_events[property_name].set()

            # Wait for thread to finish
            if property_name in self.active_transitions:
                thread = self.active_transitions[property_name]
                # Don't wait if we're on the same thread (shouldn't happen)
                if threading.current_thread() != thread:
                    thread.join(timeout=1.0)
                    if thread.is_alive():
                        self.logger.warning(
                            f"Transition thread for {property_name} did not stop cleanly"
                        )

                del self.active_transitions[property_name]

            # Clean up stop event
            if property_name in self.stop_events:
                del self.stop_events[property_name]

    def cancel_all(self):
        """Cancel all active transitions."""
        with self.lock:
            property_names = list(self.active_transitions.keys())

        for property_name in property_names:
            self.cancel_transition(property_name)

    def _execute_transition(
        self,
        property_name: str,
        switch_nr: int,
        start_brightness: int,
        end_brightness: int,
        duration: float,
        easing_name: str,
        stop_event: threading.Event,
        on_step: Optional[Callable[[int], None]],
    ):
        """
        Execute a brightness transition in the current thread.

        This method runs in a background thread and should not be called directly.
        """
        try:
            # Get easing function
            try:
                easing_func = get_easing_function(easing_name)
            except ValueError as e:
                self.logger.error(f"Invalid easing function: {e}, using default")
                easing_func = get_easing_function()  # Use default

            # Calculate number of steps based on duration and step delay
            num_steps = max(1, int(duration / self.step_delay))

            # Execute transition
            start_time = time.time()

            for step in range(num_steps + 1):
                # Check if we should stop
                if stop_event.is_set():
                    self.logger.warning(
                        f"Transition interrupted for {property_name} at step {step}/{num_steps} "
                        f"({step/num_steps*100:.0f}% complete)"
                    )
                    return

                # Calculate progress (0.0 to 1.0)
                progress = step / num_steps if num_steps > 0 else 1.0

                # Apply easing function
                eased_progress = easing_func(progress)

                # Calculate current brightness
                brightness_range = end_brightness - start_brightness
                current_brightness = int(
                    start_brightness + (brightness_range * eased_progress)
                )

                # Clamp to valid range
                current_brightness = max(0, min(255, current_brightness))

                # Send command to device
                self.device._send_switch_command(
                    switch_nr, current_brightness > 0, brightness=current_brightness
                )

                # Invoke step callback if provided
                if on_step:
                    on_step(current_brightness)

                # Sleep until next step (unless this is the last step)
                if step < num_steps:
                    # Calculate how long we should sleep to maintain timing
                    elapsed = time.time() - start_time
                    target_time = (step + 1) * self.step_delay
                    sleep_time = target_time - elapsed

                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    elif sleep_time < -self.step_delay:
                        # We're falling behind - log a warning
                        self.logger.warning(
                            f"Transition for {property_name} falling behind by {-sleep_time:.2f}s"
                        )

            elapsed_total = time.time() - start_time
            self.logger.info(
                f"Completed transition for {property_name} in {elapsed_total:.2f}s "
                f"({num_steps} steps, target {duration:.2f}s)"
            )

        except Exception as e:
            self.logger.error(
                f"Error during transition for {property_name}: {e}", exc_info=True
            )

        finally:
            # Clean up
            with self.lock:
                if property_name in self.active_transitions:
                    del self.active_transitions[property_name]
                if property_name in self.stop_events:
                    del self.stop_events[property_name]


class FlashController:
    """
    Manages flash effects for lights.

    Flash briefly turns the light ON (or to a specific brightness) then returns to
    the previous state. This is useful for attention-getting notifications.
    """

    def __init__(self, device, flash_transition_length: float = 0.25):
        """
        Initialize the flash controller.

        Args:
            device: The device instance (must have _send_switch_command method)
            flash_transition_length: Transition time for flash ON/OFF in seconds (default 250ms)
        """
        self.device = device
        self.flash_transition_length = flash_transition_length
        self.logger = logging.getLogger(f"{__name__}.FlashController")

        # Track active flashes: {property_name: thread}
        self.active_flashes = {}

        # Lock for thread-safe access
        self.lock = threading.Lock()

        # Stop events for cancelling flashes: {property_name: Event}
        self.stop_events = {}

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
        Start a flash effect.

        Args:
            property_name: Name of the property (e.g., 's1')
            switch_nr: Switch number (0-5)
            duration: Flash duration in seconds
            previous_state: State to restore after flash
            previous_brightness: Brightness to restore after flash
            on_complete: Optional callback to invoke when flash completes
        """
        # Cancel any existing flash for this property
        self.cancel_flash(property_name)

        # Create a new stop event
        stop_event = threading.Event()
        with self.lock:
            self.stop_events[property_name] = stop_event

        # Start flash in a new thread
        thread = threading.Thread(
            target=self._execute_flash,
            args=(
                property_name,
                switch_nr,
                duration,
                previous_state,
                previous_brightness,
                stop_event,
                on_complete,
            ),
            daemon=True,
            name=f"Flash-{property_name}",
        )

        with self.lock:
            self.active_flashes[property_name] = thread

        thread.start()
        self.logger.info(
            f"Started flash for {property_name}: duration={duration}s, "
            f"restore to state={previous_state}, brightness={previous_brightness}"
        )

    def cancel_flash(self, property_name: str):
        """
        Cancel an active flash.

        Args:
            property_name: Name of the property to cancel flash for
        """
        with self.lock:
            # Signal the thread to stop
            if property_name in self.stop_events:
                self.stop_events[property_name].set()

            # Wait for thread to finish
            if property_name in self.active_flashes:
                thread = self.active_flashes[property_name]
                # Don't wait if we're on the same thread
                if threading.current_thread() != thread:
                    thread.join(timeout=1.0)
                    if thread.is_alive():
                        self.logger.warning(
                            f"Flash thread for {property_name} did not stop cleanly"
                        )

                del self.active_flashes[property_name]

            # Clean up stop event
            if property_name in self.stop_events:
                del self.stop_events[property_name]

    def cancel_all(self):
        """Cancel all active flashes."""
        with self.lock:
            property_names = list(self.active_flashes.keys())

        for property_name in property_names:
            self.cancel_flash(property_name)

    def _execute_flash(
        self,
        property_name: str,
        switch_nr: int,
        duration: float,
        previous_state: bool,
        previous_brightness: int,
        stop_event: threading.Event,
        on_complete: Optional[Callable[[], None]],
    ):
        """
        Execute a flash effect in the current thread.

        This method runs in a background thread and should not be called directly.
        """
        try:
            # Phase 1: Transition to ON (full brightness)
            if stop_event.is_set():
                self.logger.warning(
                    f"Flash interrupted for {property_name} before starting"
                )
                return

            self.device._send_switch_command(switch_nr, True, brightness=255)
            self.logger.debug(f"Flash {property_name}: ON at full brightness")

            # Wait for the flash duration
            # Split into small intervals to check stop_event frequently
            check_interval = 0.1  # Check every 100ms
            elapsed = 0.0

            while elapsed < duration:
                if stop_event.is_set():
                    self.logger.warning(
                        f"Flash interrupted for {property_name} after {elapsed:.1f}s "
                        f"({elapsed/duration*100:.0f}% complete)"
                    )
                    return

                sleep_time = min(check_interval, duration - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time

            # Phase 2: Restore to previous state
            if stop_event.is_set():
                self.logger.warning(
                    f"Flash interrupted for {property_name} before restore phase"
                )
                return

            self.device._send_switch_command(
                switch_nr, previous_state, brightness=previous_brightness
            )
            self.logger.debug(
                f"Flash {property_name}: restored to state={previous_state}, brightness={previous_brightness}"
            )

            # Invoke completion callback
            if on_complete:
                on_complete()

            self.logger.info(f"Completed flash for {property_name}")

        except Exception as e:
            self.logger.error(
                f"Error during flash for {property_name}: {e}", exc_info=True
            )

        finally:
            # Clean up
            with self.lock:
                if property_name in self.active_flashes:
                    del self.active_flashes[property_name]
                if property_name in self.stop_events:
                    del self.stop_events[property_name]


class ScheiberCanDevice(ABC):
    """Base class for all Scheiber CAN devices."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
        can_bus: Optional[can.BusABC],
        data_dir: Optional[str] = None,
        discovery_configs: Optional[List] = None,
    ):
        self.device_type = device_type
        self.device_id = device_id
        self.device_config = device_config
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.can_bus = can_bus
        self.data_dir = data_dir
        self.discovery_configs = discovery_configs or []
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}.{device_type}_{device_id}"
        )

        # Track device state: {property_name: value}
        self.state = {}

        # Track which properties have been published
        self.published_properties = set()

        # Track which properties are available (received data from CAN bus)
        self.available_properties = set()

    def get_base_topic(self) -> str:
        """Get the base MQTT topic for this device."""
        return f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}"

    def get_property_topic(self, property_name: str, suffix: str = "") -> str:
        """Get the MQTT topic for a specific property."""
        topic = f"{self.get_base_topic()}/{property_name}"
        if suffix:
            topic = f"{topic}/{suffix}"
        return topic

    def get_all_properties(self) -> Set[str]:
        """Get all unique properties across all matchers for this device."""
        all_properties = set()
        for matcher in self.device_config.get("matchers", []):
            all_properties.update(matcher.get("properties", {}).keys())
        return all_properties

    def update_state(self, decoded_properties: Dict[str, Any]):
        """Update device state with decoded properties."""
        self.state.update(decoded_properties)

    def mark_property_available(self, property_name: str):
        """Mark a property as available and publish availability status."""
        if property_name not in self.available_properties:
            self.available_properties.add(property_name)
            availability_topic = self.get_property_topic(property_name, "availability")
            self.logger.debug(
                f"Publishing availability to {availability_topic}: online"
            )
            self.mqtt_client.publish(availability_topic, "online", qos=1, retain=True)

    def register_command_topics(self) -> List[Tuple[str, Callable[[str, str], None]]]:
        """
        Register MQTT command topics this device wants to handle.

        Returns:
            List of (topic_pattern, handler_function) tuples.
            Topic patterns can include '+' wildcards for MQTT subscription.
        """
        return []

    def handle_command(self, topic: str, payload: str, is_retained: bool = False):
        """
        Handle a command received on an MQTT topic.

        Args:
            topic: Full MQTT topic where command was received
            payload: Command payload string
            is_retained: Whether this message was retained by the broker
        """
        self.logger.warning(f"Unhandled command on {topic}: {payload}")

    @abstractmethod
    def publish_discovery_config(self):
        """Publish Home Assistant MQTT Discovery configuration."""
        pass

    @abstractmethod
    def publish_state(self, property_name: str, value: Any):
        """Publish property state to MQTT."""
        pass

    def update_heartbeat(self):
        """Update device heartbeat. Override in subclasses to implement availability tracking."""
        pass

    def check_heartbeat(self):
        """Check device heartbeat. Override in subclasses to implement availability tracking."""
        pass

    def publish_device_info(self):
        """Publish device information to MQTT."""
        topic = self.get_base_topic()
        payload = {
            "name": self.device_config.get("name", self.device_type),
            "device_type": self.device_type,
            "bus_id": self.device_id,
        }
        import json

        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing device info to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)


class Bloc9(ScheiberCanDevice):
    """Bloc9 device with switch and brightness support."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
        can_bus: Optional[can.BusABC],
        data_dir: Optional[str] = None,
        discovery_configs: Optional[List] = None,
    ):
        super().__init__(
            device_type,
            device_id,
            device_config,
            mqtt_client,
            mqtt_topic_prefix,
            can_bus,
            data_dir,
            discovery_configs=discovery_configs,
        )

        # Set state cache directory from data_dir or use default
        if data_dir:
            self.state_cache_dir = Path(data_dir) / "state_cache"
        else:
            self.state_cache_dir = Path(__file__).parent / ".state_cache"

        self.logger.info(
            f"Initialized Bloc9 device: {device_type} {device_id}, "
            f"state_cache={self.state_cache_dir}, "
            f"discovered_entities={len(self.discovery_configs)}"
        )

        # Heartbeat tracking for availability
        self.last_heartbeat = None  # Timestamp of last status message
        self.heartbeat_timeout = 60  # Seconds before marking offline
        self.is_online = False  # Current online status

        # Transition controller for smooth brightness changes
        self.transition_controller = TransitionController(self, step_delay=0.1)

        # Flash controller for attention-getting effects
        self.flash_controller = FlashController(self, flash_transition_length=0.25)

        # Load persisted state and publish if available
        self._load_and_publish_persisted_state()

    def publish_device_info(self):
        """Publish device information including switch states to MQTT."""
        topic = self.get_base_topic()
        payload = {
            "name": self.device_config.get("name", self.device_type),
            "device_type": self.device_type,
            "bus_id": self.device_id,
            "switches": {},
        }

        # Add current state of each switch
        all_properties = self.get_all_properties()
        for prop_name in all_properties:
            # Only include switch properties (not brightness/stat properties)
            if not prop_name.endswith("_brightness") and not prop_name.startswith(
                "stat"
            ):
                # Get state from persisted or current state
                state_value = self.state.get(prop_name, "unknown")
                # Normalize state values to ON/OFF
                if str(state_value) in ("1", "True", "true"):
                    state_value = "ON"
                elif str(state_value) in ("0", "False", "false"):
                    state_value = "OFF"
                payload["switches"][prop_name] = state_value

        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing device info to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)

    def update_heartbeat(self):
        """Update heartbeat timestamp and mark device online if needed."""
        import time

        self.last_heartbeat = time.time()

        # If device was offline, mark it online now
        if not self.is_online:
            self.is_online = True
            self._mark_all_properties_online()
            self.logger.info(f"Bloc9 device {self.device_id} is now ONLINE")

    def check_heartbeat(self):
        """Check if device should be marked offline due to missing heartbeats."""
        import time

        if self.last_heartbeat is None:
            return  # No heartbeat received yet

        time_since_heartbeat = time.time() - self.last_heartbeat

        if self.is_online and time_since_heartbeat > self.heartbeat_timeout:
            self.is_online = False
            self._mark_all_properties_offline()
            self.logger.warning(
                f"Bloc9 device {self.device_id} is now OFFLINE (no status for {time_since_heartbeat:.1f}s)"
            )

    def _mark_all_properties_online(self):
        """Mark all configured outputs as online (available)."""
        # Mark all configured outputs as online
        for disc_config in self.discovery_configs:
            availability_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{disc_config.output}/availability"
            self.mqtt_client.publish(availability_topic, "online", qos=1, retain=True)
            self.logger.debug(f"Marked {disc_config.output} as online")

    def _mark_all_properties_offline(self):
        """Mark all configured outputs as offline (unavailable)."""
        # Mark all configured outputs as offline
        for disc_config in self.discovery_configs:
            availability_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{disc_config.output}/availability"
            self.mqtt_client.publish(availability_topic, "offline", qos=1, retain=True)
            self.logger.debug(f"Marked {disc_config.output} as offline")

    def register_command_topics(self) -> List[Tuple[str, Callable[[str, str], None]]]:
        """Register command topics for explicitly configured outputs only."""
        topics = []

        for disc_config in self.discovery_configs:
            # Register ON/OFF command topic
            command_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{disc_config.output}/set"
            topics.append((command_topic, self.handle_command))

            # Register brightness command topic for lights
            if disc_config.component == "light":
                brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{disc_config.output}/set_brightness"
                topics.append((brightness_topic, self.handle_command))

        return topics

    def handle_command(self, topic: str, payload: str, is_retained: bool = False):
        """Handle JSON and legacy commands for Bloc9 switches."""
        # Ignore empty payloads (used for clearing retained messages)
        if not payload or payload.strip() == "":
            self.logger.debug(f"Ignoring empty payload on {topic}")
            return

        # Parse the topic to extract property name and command type
        # Topic format: <prefix>/scheiber/<device_type>/<device_id>/<property>/set
        topic_parts = topic.split("/")

        if len(topic_parts) < 2:
            self.logger.error(f"Invalid topic format: {topic}")
            return

        command_type = topic_parts[-1]  # 'set'
        property_name = topic_parts[-2]  # e.g., 's1', 's2'

        # Validate property starts with 's' and has a digit
        if not (
            property_name.startswith("s")
            and len(property_name) >= 2
            and property_name[1:].isdigit()
        ):
            self.logger.warning(f"Invalid property name: {property_name}")
            return

        # Extract switch number (s1=0, s2=1, etc.)
        switch_nr = int(property_name[1:]) - 1

        # CRITICAL: Only accept commands for explicitly configured entities
        # Verify this property is in discovery_configs
        is_configured = any(dc.output == property_name for dc in self.discovery_configs)

        if not is_configured:
            self.logger.warning(
                f"Received command for unconfigured property {property_name} on {topic}. "
                f"Ignoring - property not in scheiber.yaml discovery configs."
            )
            return

        try:
            # Check if this is a light entity (uses JSON schema)
            is_light = any(
                dc.output == property_name and dc.component == "light"
                for dc in self.discovery_configs
            )

            if is_light:
                # Parse JSON command for lights
                try:
                    cmd_data = json.loads(payload)
                    state = cmd_data.get("state", "ON").upper() == "ON"
                    brightness = cmd_data.get("brightness", 255 if state else 0)
                    transition = cmd_data.get(
                        "transition", 0
                    )  # seconds, not yet implemented
                    flash_duration = cmd_data.get(
                        "flash", None
                    )  # Flash duration in seconds

                    if brightness < 0 or brightness > 255:
                        self.logger.error(
                            f"Brightness value out of range (0-255): {brightness}"
                        )
                        return

                    # Handle flash command
                    if flash_duration is not None:
                        try:
                            flash_duration = float(flash_duration)
                            if flash_duration <= 0:
                                self.logger.error(
                                    f"Flash duration must be positive: {flash_duration}"
                                )
                                return
                        except (ValueError, TypeError):
                            self.logger.error(
                                f"Invalid flash duration value: {flash_duration}"
                            )
                            return

                        self.logger.info(
                            f"Executing flash command: switch={switch_nr}, duration={flash_duration}s{' (retained)' if is_retained else ''}"
                        )

                        # Cancel any existing transitions/flashes
                        self.transition_controller.cancel_transition(property_name)
                        self.flash_controller.cancel_flash(property_name)

                        # Get current state to restore after flash
                        current_state = self.state.get(property_name, "OFF") == "ON"
                        current_brightness_key = f"{property_name}_brightness"
                        current_brightness = self.state.get(current_brightness_key, 0)

                        # Define callback to restore state in MQTT when flash completes
                        def on_flash_complete():
                            state_topic = self.get_property_topic(
                                property_name, "state"
                            )
                            restore_state = "ON" if current_state else "OFF"
                            restore_payload = json.dumps(
                                {
                                    "state": restore_state,
                                    "brightness": current_brightness,
                                }
                            )
                            self.mqtt_client.publish(
                                state_topic, restore_payload, qos=1, retain=True
                            )
                            # Update internal state
                            self.state[property_name] = restore_state
                            self.state[current_brightness_key] = current_brightness
                            self.logger.debug(
                                f"Flash complete, restored to {restore_state} @ {current_brightness}"
                            )

                        # Start the flash
                        self.flash_controller.start_flash(
                            property_name=property_name,
                            switch_nr=switch_nr,
                            duration=flash_duration,
                            previous_state=current_state,
                            previous_brightness=current_brightness,
                            on_complete=on_flash_complete,
                        )

                        # Publish flashing state immediately for HA feedback
                        state_topic = self.get_property_topic(property_name, "state")
                        flash_payload = json.dumps({"state": "ON", "brightness": 255})
                        self.mqtt_client.publish(
                            state_topic, flash_payload, qos=1, retain=True
                        )

                        # Don't persist flashing state - we'll restore after flash
                        # Return early as flash handling is complete
                        if is_retained:
                            self.logger.info(f"Clearing retained command on {topic}")
                            self.mqtt_client.publish(topic, None, qos=1, retain=True)
                        return

                    self.logger.info(
                        f"Executing JSON light command: switch={switch_nr}, state={state}, "
                        f"brightness={brightness}, transition={transition}s{' (retained)' if is_retained else ''}"
                    )

                    # CRITICAL: Always cancel any existing transition first
                    # This ensures that turning off a light stops any running transition
                    self.transition_controller.cancel_transition(property_name)
                    # Also cancel any active flash
                    self.flash_controller.cancel_flash(property_name)

                    # Get current brightness for transition start point
                    current_brightness_key = f"{property_name}_brightness"
                    current_brightness = self.state.get(
                        current_brightness_key, 0 if not state else 255
                    )

                    # Handle transition if requested
                    if transition > 0 and current_brightness != brightness:
                        # Use transition controller for smooth dimming

                        # Determine easing function based on transition context
                        if current_brightness == 0 and brightness > 0:
                            # Fading up from off - use ease_out_cubic for snappy start
                            easing = "ease_out_cubic"
                        elif brightness == 0 and current_brightness > 0:
                            # Fading down to off - use ease_in_cubic for gentle end
                            easing = "ease_in_cubic"
                        else:
                            # General transition - use default ease_in_out_sine
                            easing = "ease_in_out_sine"

                        self.logger.info(
                            f"Starting transition: {current_brightness} -> {brightness} "
                            f"over {transition}s using {easing}"
                        )

                        # Define callback to publish intermediate state updates
                        def on_step(step_brightness: int):
                            state_topic = self.get_property_topic(
                                property_name, "state"
                            )
                            step_state = "ON" if step_brightness > 0 else "OFF"
                            step_payload = json.dumps(
                                {"state": step_state, "brightness": step_brightness}
                            )
                            self.mqtt_client.publish(
                                state_topic, step_payload, qos=1, retain=True
                            )
                            # Update internal state
                            self.state[property_name] = step_state
                            self.state[current_brightness_key] = step_brightness

                        # Start the transition
                        self.transition_controller.start_transition(
                            property_name=property_name,
                            switch_nr=switch_nr,
                            start_brightness=current_brightness,
                            end_brightness=brightness,
                            duration=transition,
                            easing_name=easing,
                            on_step=on_step,
                        )

                        # Persist final state (will be reached after transition completes)
                        final_state = "ON" if brightness > 0 else "OFF"
                        self._persist_state(property_name, final_state)
                        self._persist_state(current_brightness_key, brightness)

                    else:
                        # No transition - send command immediately
                        self._send_switch_command(
                            switch_nr, state, brightness=brightness
                        )

                        # Optimistically publish new state as JSON
                        state_topic = self.get_property_topic(property_name, "state")
                        state_value = "ON" if state and brightness > 0 else "OFF"
                        json_payload = json.dumps(
                            {"state": state_value, "brightness": brightness}
                        )
                        self.mqtt_client.publish(
                            state_topic, json_payload, qos=1, retain=True
                        )
                        self.logger.debug(
                            f"Optimistically published JSON state: {json_payload}"
                        )

                        # Update internal state
                        self.state[property_name] = state_value
                        self.state[f"{property_name}_brightness"] = brightness
                        self._persist_state(property_name, state_value)
                        self._persist_state(f"{property_name}_brightness", brightness)

                except json.JSONDecodeError:
                    # Fall back to legacy ON/OFF command
                    self.logger.warning(
                        f"Invalid JSON payload, treating as legacy command: {payload}"
                    )
                    # Cancel any running transition or flash
                    self.transition_controller.cancel_transition(property_name)
                    self.flash_controller.cancel_flash(property_name)
                    state = payload.upper() in ("ON", "1", "TRUE")
                    self._send_switch_command(switch_nr, state)

                    state_value = "ON" if state else "OFF"
                    brightness = 255 if state else 0
                    state_topic = self.get_property_topic(property_name, "state")
                    json_payload = json.dumps(
                        {"state": state_value, "brightness": brightness}
                    )
                    self.mqtt_client.publish(
                        state_topic, json_payload, qos=1, retain=True
                    )

                    self.state[property_name] = state_value
                    self.state[f"{property_name}_brightness"] = brightness
                    self._persist_state(property_name, state_value)
                    self._persist_state(f"{property_name}_brightness", brightness)
            else:
                # Non-light entities: simple ON/OFF command
                # Cancel any running transition or flash (safety measure)
                self.transition_controller.cancel_transition(property_name)
                self.flash_controller.cancel_flash(property_name)
                state = payload.upper() in ("ON", "1", "TRUE")
                self.logger.info(
                    f"Executing switch command: switch={switch_nr}, state={state}{' (retained)' if is_retained else ''}"
                )
                self._send_switch_command(switch_nr, state)

                # Optimistically publish new state for immediate HA feedback
                state_topic = self.get_property_topic(property_name, "state")
                state_value = "ON" if state else "OFF"
                self.mqtt_client.publish(state_topic, state_value, qos=1, retain=True)
                self.logger.debug(f"Optimistically published state={state_value}")

                # Update internal state
                self.state[property_name] = state_value
                self._persist_state(property_name, state_value)

            # Clear retained command after successful execution
            if is_retained:
                self.logger.info(f"Clearing retained command on {topic}")
                self.mqtt_client.publish(topic, None, qos=1, retain=True)

        except ValueError as e:
            self.logger.error(f"Invalid command payload: {payload} - {e}")
        except Exception as e:
            self.logger.error(f"Failed to execute command: {e}")

    def _send_switch_command(
        self, switch_nr: int, state: bool, brightness: Optional[int] = None
    ):
        """
        Send a switch command to the Bloc9 device via CAN bus.

        Args:
            switch_nr: Switch number (0-5 for S1-S6)
            state: Boolean state (True for ON, False for OFF)
            brightness: Optional brightness level (0-255)
        """
        if not self.can_bus:
            self.logger.error("No CAN bus available for sending commands")
            return

        try:
            # Construct CAN ID: lowest byte = (bloc9_id << 3) | 0x80
            low_byte = ((self.device_id << 3) | 0x80) & 0xFF
            can_id = 0x02360600 | low_byte

            # Construct 4-byte body based on brightness parameter
            if brightness is not None:
                if brightness == 0:
                    # Brightness 0 = turn off
                    data = bytes([switch_nr, 0x00, 0x00, 0x00])
                    self.logger.debug(f"Switch {switch_nr} -> OFF (brightness=0)")
                elif brightness == 255:
                    # Brightness 255 = turn on (without brightness control)
                    data = bytes([switch_nr, 0x01, 0x00, 0x00])
                    self.logger.debug(f"Switch {switch_nr} -> ON (brightness=255)")
                else:
                    # Set brightness level (byte 1 = 0x11, byte 3 = brightness)
                    brightness_byte = max(1, min(254, brightness))
                    data = bytes([switch_nr, 0x11, 0x00, brightness_byte])
                    self.logger.debug(
                        f"Switch {switch_nr} -> brightness={brightness_byte}"
                    )
            else:
                # Simple ON/OFF mode
                state_byte = 0x01 if state else 0x00
                data = bytes([switch_nr, state_byte, 0x00, 0x00])
                self.logger.debug(f"Switch {switch_nr} -> {'ON' if state else 'OFF'}")

            # Send the message
            msg = can.Message(arbitration_id=can_id, data=data)
            self.can_bus.send(msg)
            self.logger.info(
                f"CAN TX: ID=0x{can_id:08X} Data={' '.join(f'{b:02X}' for b in data)}"
            )
        except Exception as e:
            self.logger.error(f"Failed to send CAN message: {e}")
            raise

    def _get_scheiber_device_info(self) -> dict:
        """
        Get the unified Scheiber device info that all entities belong to.
        This creates a single "Scheiber" device in Home Assistant.
        """
        return {
            "identifiers": ["scheiber_system"],
            "name": "Scheiber",
            "model": "Marine Lighting Control System",
            "manufacturer": "Scheiber",
        }

    def publish_discovery_config(self):
        """
        Publish Home Assistant MQTT Discovery config for explicitly configured entities.

        Uses standard HA discovery pattern: <discovery_prefix>/{component}/{object_id}/config
        Only publishes discovery for outputs that are explicitly configured in scheiber.yaml.

        Device structure (v4.0.0):
        - All entities belong to a single unified "Scheiber" device
        - This simplifies entity naming in Home Assistant
        """
        import json

        self.logger.debug(
            f"publish_discovery_config called for Bloc9 {self.device_id}, "
            f"discovery_configs count: {len(self.discovery_configs)}"
        )

        if not self.discovery_configs:
            self.logger.info(
                f"No discovery configs for Bloc9 {self.device_id}, skipping discovery"
            )
            return

        self.logger.info(
            f"Publishing discovery for {len(self.discovery_configs)} entities on Bloc9 {self.device_id}"
        )

        # Get unified Scheiber device info
        scheiber_device = self._get_scheiber_device_info()

        for disc_config in self.discovery_configs:
            # Build discovery topic: <discovery_prefix>/{component}/{object_id}/config
            discovery_topic = f"{self.mqtt_topic_prefix}/{disc_config.component}/{disc_config.entity_id}/config"

            # Build scheiber topic paths for state and commands
            scheiber_base = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{disc_config.output}"
            state_topic = f"{scheiber_base}/state"
            command_topic = f"{scheiber_base}/set"
            availability_topic = f"{scheiber_base}/availability"

            self.logger.debug(
                f"Publishing {disc_config.component}.{disc_config.entity_id}: "
                f"name='{disc_config.name}', device='Scheiber'"
            )

            # All entities belong to the unified Scheiber device
            config_payload = {
                "name": disc_config.name,
                "unique_id": f"scheiber_{self.device_type}_{self.device_id}_{disc_config.output}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "optimistic": False,
                "qos": 1,
                "retain": True,
                "device": scheiber_device,
            }

            # Add brightness support for lights with JSON schema
            if disc_config.component == "light":
                config_payload["schema"] = "json"
                config_payload["brightness"] = True
                config_payload["supported_color_modes"] = ["brightness"]
                config_payload["brightness_scale"] = 255
                # Add flash support
                config_payload["flash"] = True
                config_payload["flash_time_short"] = 2
                config_payload["flash_time_long"] = 10

            config_json = json.dumps(config_payload)
            self.logger.debug(
                f"Publishing discovery to {discovery_topic}: {config_json}"
            )
            self.mqtt_client.publish(discovery_topic, config_json, qos=1, retain=True)

            # Publish initial offline availability
            self.logger.debug(
                f"Publishing initial availability to {availability_topic}: offline"
            )
            self.mqtt_client.publish(availability_topic, "offline", qos=1, retain=True)

            self.published_properties.add(disc_config.output)

    def publish_state(self, property_name: str, value: Any):
        """Publish property state to MQTT using JSON schema for lights."""
        # Skip publishing stat properties (used only for heartbeat)
        if property_name.startswith("stat"):
            return

        # Skip publishing if value is None
        if value is None:
            return

        # Handle brightness properties - update internal state but don't publish separately
        if property_name.endswith("_brightness"):
            # Persist brightness state
            self._persist_state(property_name, value)
            return

        # CRITICAL: Only publish state for explicitly configured entities
        # Check if this property is in discovery_configs
        is_configured = any(dc.output == property_name for dc in self.discovery_configs)

        if not is_configured:
            # Property not configured in scheiber.yaml - don't publish
            self.logger.debug(
                f"Skipping state publish for unconfigured property {property_name}"
            )
            return

        # Handle switch state with JSON schema
        topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"

        # Convert numeric values to ON/OFF
        if str(value) in ("1", "True", "true"):
            state_value = "ON"
        elif str(value) in ("0", "False", "false"):
            state_value = "OFF"
        else:
            state_value = str(value)

        # Get brightness value if available
        brightness_key = f"{property_name}_brightness"
        brightness = self.state.get(brightness_key, 255 if state_value == "ON" else 0)

        # CRITICAL: Detect unexpected state changes from CAN bus (e.g., hardware button press)
        # Strategy: Check if there's an active transition or flash for this property
        # - If NO active operation: This could be external (hardware button) - but we can't
        #   cancel what doesn't exist, so no action needed
        # - If active operation exists: Check if the new state differs significantly from
        #   what we expect. If it does, it's an external override - cancel the operation

        has_active_transition = (
            property_name in self.transition_controller.active_transitions
        )
        has_active_flash = property_name in self.flash_controller.active_flashes

        if has_active_transition or has_active_flash:
            # There's an active operation - check if this state change is unexpected
            # Compare the incoming state with our internal state expectation
            current_internal_state = self.state.get(property_name, "OFF")

            # Normalize internal state for comparison (handle numeric/string variations)
            if str(current_internal_state) in ("1", "True", "true", "ON"):
                normalized_internal = "ON"
            elif str(current_internal_state) in ("0", "False", "false", "OFF"):
                normalized_internal = "OFF"
            else:
                normalized_internal = str(current_internal_state)

            # If the CAN bus reports a different state than what we're tracking internally,
            # this indicates an external command (hardware button override)
            if state_value != normalized_internal:
                self.logger.warning(
                    f"Unexpected CAN bus state change for {property_name}: "
                    f"received {state_value} but expected {normalized_internal} "
                    f"(raw internal: {current_internal_state}, "
                    f"active: transition={has_active_transition}, flash={has_active_flash}). "
                    f"External override detected - cancelling operation."
                )
                self.transition_controller.cancel_transition(property_name)
                self.flash_controller.cancel_flash(property_name)
            else:
                # State matches - this is echo from our own command
                self.logger.debug(
                    f"State change for {property_name} matches internal state, "
                    f"assuming echo from our command during "
                    f"{'transition' if has_active_transition else 'flash'}"
                )

        # Publish as JSON for lights (entities configured via discovery_configs)
        is_light = any(
            dc.output == property_name and dc.component == "light"
            for dc in self.discovery_configs
        )

        if is_light:
            payload = json.dumps({"state": state_value, "brightness": brightness})
            self.logger.debug(f"Publishing light state (JSON) to {topic}: {payload}")
        else:
            # Non-light entities use simple ON/OFF
            payload = state_value
            self.logger.debug(f"Publishing property state to {topic}: {payload}")

        self.mqtt_client.publish(topic, payload, qos=1, retain=True)

        # Persist switch state
        self._persist_state(property_name, state_value)

    def _get_state_file_path(self) -> Path:
        """Get the path to the state file for this device."""
        return self.state_cache_dir / f"bloc9_{self.device_id}.json"

    def _persist_state(self, property_name: str, value: Any):
        """Persist a property state to disk."""
        try:
            # Ensure state cache directory exists
            self.state_cache_dir.mkdir(parents=True, exist_ok=True)

            state_file = self._get_state_file_path()

            # Load existing state or create new
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        state_data = json.load(f)
                except json.JSONDecodeError as e:
                    # Corrupted state file - log warning and start fresh
                    self.logger.warning(
                        f"Corrupted state file detected for Bloc9 {self.device_id}: {e}. "
                        f"Creating new state file."
                    )
                    state_data = {}
            else:
                state_data = {}

            # Update state
            state_data[property_name] = value

            # Write back to file atomically (write to temp, then rename)
            temp_file = state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(state_data, f, indent=2)

            # Atomic rename (overwrites existing file)
            temp_file.replace(state_file)

            self.logger.debug(f"Persisted state: {property_name}={value}")
        except Exception as e:
            self.logger.error(f"Failed to persist state for {property_name}: {e}")

    def _load_persisted_state(self) -> Dict[str, Any]:
        """Load persisted state from disk."""
        state_file = self._get_state_file_path()

        if not state_file.exists():
            self.logger.debug("No persisted state found")
            return {}

        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
            self.logger.info(
                f"Loaded persisted state with {len(state_data)} properties"
            )
            return state_data
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to load persisted state (corrupted JSON): {e}. "
                f"Starting with empty state - file will be recreated."
            )
            return {}
        except Exception as e:
            self.logger.error(f"Failed to load persisted state: {e}")
            return {}

    def _load_and_publish_persisted_state(self):
        """Load persisted state and publish to MQTT as initial state."""
        persisted_state = self._load_persisted_state()

        if not persisted_state:
            return

        self.logger.info(
            f"Publishing {len(persisted_state)} persisted properties to MQTT"
        )

        for property_name, value in persisted_state.items():
            try:
                # Handle brightness properties
                if property_name.endswith("_brightness"):
                    # Skip if value is None
                    if value is None:
                        continue

                    # Skip unconfigured properties
                    base_prop = property_name.replace("_brightness", "")
                    if not any(dc.output == base_prop for dc in self.discovery_configs):
                        self.logger.debug(
                            f"Skipping restore for unconfigured brightness property {property_name}"
                        )
                        continue

                    brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{base_prop}/brightness"
                    payload = str(value)
                    self.logger.debug(
                        f"Restoring brightness to {brightness_topic}: {payload}"
                    )
                    self.mqtt_client.publish(
                        brightness_topic, payload, qos=1, retain=True
                    )
                # Skip stat properties
                elif property_name.startswith("stat"):
                    continue
                # Handle regular switch state
                else:
                    # Skip if value is None
                    if value is None:
                        continue

                    # Skip unconfigured properties
                    if not any(
                        dc.output == property_name for dc in self.discovery_configs
                    ):
                        self.logger.debug(
                            f"Skipping restore for unconfigured property {property_name}"
                        )
                        continue

                    topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"

                    # Convert numeric values to ON/OFF for restored states
                    if str(value) in ("1", "True", "true", "ON"):
                        state_value = "ON"
                    elif str(value) in ("0", "False", "false", "OFF"):
                        state_value = "OFF"
                    else:
                        state_value = str(value)

                    # Get brightness for this property
                    brightness_key = f"{property_name}_brightness"
                    brightness = persisted_state.get(
                        brightness_key, 255 if state_value == "ON" else 0
                    )

                    # Check if this is a light entity
                    is_light = any(
                        dc.output == property_name and dc.component == "light"
                        for dc in self.discovery_configs
                    )

                    if is_light:
                        # Publish as JSON for lights
                        payload = json.dumps(
                            {"state": state_value, "brightness": brightness}
                        )
                        self.logger.debug(
                            f"Restoring light state (JSON) to {topic}: {payload}"
                        )
                    else:
                        # Publish as plain text for switches
                        payload = state_value
                        self.logger.debug(
                            f"Restoring switch state to {topic}: {payload}"
                        )

                    self.mqtt_client.publish(topic, payload, qos=1, retain=True)
            except Exception as e:
                self.logger.error(f"Failed to restore state for {property_name}: {e}")


# Device type registry - maps device type names to classes
DEVICE_TYPE_CLASSES = {
    "bloc9": Bloc9,
    # Add more device types here:
    # "tank_sensor": TankSensor,
    # "battery_monitor": BatteryMonitor,
}


def create_device(
    device_type: str,
    device_id: int,
    device_config: Dict[str, Any],
    mqtt_client,
    mqtt_topic_prefix: str,
    can_bus,
    data_dir: Optional[str] = None,
    discovery_configs: Optional[List] = None,
) -> ScheiberCanDevice:
    """Factory function to create appropriate device instance."""
    device_class = DEVICE_TYPE_CLASSES.get(device_type, ScheiberCanDevice)

    # ScheiberCanDevice is abstract, so if no specific class found, use Bloc9 as default
    if device_class == ScheiberCanDevice:
        logging.warning(
            f"No device class found for type '{device_type}', using Bloc9 as default"
        )
        device_class = Bloc9

    return device_class(
        device_type,
        device_id,
        device_config,
        mqtt_client,
        mqtt_topic_prefix,
        can_bus,
        data_dir,
        discovery_configs=discovery_configs,
    )
