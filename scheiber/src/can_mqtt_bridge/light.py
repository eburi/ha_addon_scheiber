"""
Light entity for MQTT Bridge.

Handles MQTT discovery, state publishing, and command handling for lights.
"""

import json
import logging
import time
from typing import Dict, Any, Callable, Optional
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes


class MQTTLight:
    """
    MQTT Light entity with Home Assistant Discovery support.

    Each light instance handles its own:
    - Discovery config publishing
    - State publishing (observer pattern)
    - Command topic subscription
    - Command parsing and execution
    """

    def __init__(
        self,
        hardware_light,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        """
        Initialize MQTT Light.

        Args:
            hardware_light: DimmableLight instance from scheiber module
            device_type: Device type (e.g., 'bloc9')
            device_id: Device bus ID
            mqtt_client: MQTT client instance
            mqtt_topic_prefix: MQTT topic prefix
            read_only: Read-only mode (no commands)
        """
        self.logger = logging.getLogger(f"{__name__}.{hardware_light.entity_id}")
        self.hardware_light = hardware_light
        self.device_type = device_type
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only

        # Generate identifiers (using s1, s2, etc. naming from hardware)
        self.switch_name = f"s{hardware_light.switch_nr + 1}"  # e.g., 's1', 's2'
        self.unique_id = f"scheiber_{device_type}_{device_id}_{self.switch_name}"
        self.entity_id = hardware_light.entity_id  # e.g., 'main_light_crew_cabin'

        # Generate topics (v5 schema)
        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{self.switch_name}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/light/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"

        # Track MQTT state for comparison
        self._mqtt_state: Optional[Dict[str, Any]] = None
        self._mqtt_state_timestamp: Optional[float] = None
        self._initial_state_published = False
        self._checking_initial_state = False

        # Subscribe to hardware state changes
        hardware_light.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        """Publish Home Assistant MQTT Discovery config."""
        discovery_config = {
            "name": self.hardware_light.name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "availability_topic": self.availability_topic,
            "optimistic": False,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
            "schema": "json",
            "brightness": True,
            "supported_color_modes": ["brightness"],
            "brightness_scale": 255,
            "flash": True,
            "flash_time_short": 2,
            "flash_time_long": 10,
            "effect": True,
            "effect_list": [
                "linear",
                "ease_in_sine",
                "ease_out_sine",
                "ease_in_out_sine",
                "ease_in_quad",
                "ease_out_quad",
                "ease_in_out_quad",
                "ease_in_cubic",
                "ease_out_cubic",
                "ease_in_out_cubic",
                "ease_in_quart",
                "ease_out_quart",
                "ease_in_out_quart",
            ],
        }

        self.mqtt_client.publish(
            self.config_topic, json.dumps(discovery_config), retain=True, qos=1
        )
        self.logger.debug(f"Published discovery config")

    def publish_availability(self, available: bool = True):
        """Publish availability status."""
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def subscribe_to_commands(self):
        """Subscribe to command topic."""
        self.mqtt_client.subscribe(self.command_topic)
        self.logger.debug(f"Subscribed to commands at {self.command_topic}")

    def publish_initial_state(self):
        """Publish initial state from hardware if needed."""
        # Get current hardware state
        hw_state = self.hardware_light.get_state()
        hw_on = hw_state.get("state", False)
        hw_brightness = hw_state.get("brightness", 0)

        # Subscribe to state topic to fetch retained message
        self._setup_state_subscription(hw_on, hw_brightness)

    def _setup_state_subscription(self, hw_on: bool, hw_brightness: int):
        """Subscribe to state topic to check existing retained state."""
        # Store hardware state for comparison
        self._pending_hw_state = {"state": hw_on, "brightness": hw_brightness}
        self._checking_initial_state = True

        # Subscribe to state topic to get retained message
        self.mqtt_client.message_callback_add(
            self.state_topic, self._on_initial_state_message
        )
        self.mqtt_client.subscribe(self.state_topic)
        self.logger.debug(f"Subscribed to {self.state_topic} to check retained state")

        # Set timeout to publish anyway if no retained message
        def timeout_handler():
            if not self._initial_state_published and self._checking_initial_state:
                self._checking_initial_state = False
                self.logger.info(
                    f"No retained state found after timeout, publishing initial state: "
                    f"state={'ON' if hw_on else 'OFF'}, brightness={hw_brightness}"
                )
                self._publish_state(self._pending_hw_state)
                self._initial_state_published = True
                # Clean up
                self.mqtt_client.message_callback_remove(self.state_topic)
                self.mqtt_client.unsubscribe(self.state_topic)

        # Timeout after 2 seconds
        threading = __import__("threading")
        timer = threading.Timer(2.0, timeout_handler)
        timer.daemon = True
        timer.start()

    def _on_initial_state_message(self, client, userdata, message):
        """Handle initial state topic message during subscription check."""
        if not self._checking_initial_state or self._initial_state_published:
            return

        self._checking_initial_state = False
        self._check_and_publish_state(message)

        # Clean up
        self.mqtt_client.message_callback_remove(self.state_topic)
        self.mqtt_client.unsubscribe(self.state_topic)

    def _check_and_publish_state(self, message):
        """Check retained state and publish if needed."""
        if self._initial_state_published:
            return

        hw_state = self._pending_hw_state
        hw_on = hw_state["state"]
        hw_brightness = hw_state["brightness"]

        try:
            # Parse retained message
            if message.payload:
                mqtt_state = json.loads(message.payload.decode())
                mqtt_on = mqtt_state.get("state") == "ON"
                mqtt_brightness = mqtt_state.get("brightness", 0)

                # Check message age
                message_age = None
                if hasattr(message, "timestamp") and message.timestamp:
                    message_age = time.time() - message.timestamp

                # Compare states
                state_matches = hw_on == mqtt_on and hw_brightness == mqtt_brightness
                is_old = message_age is not None and message_age > 60

                if state_matches and not is_old:
                    self.logger.info(
                        f"Retained state matches hardware (state={'ON' if hw_on else 'OFF'}, "
                        f"brightness={hw_brightness}), skipping initial publish"
                    )
                else:
                    if not state_matches:
                        self.logger.info(
                            f"Retained state differs from hardware. "
                            f"MQTT: state={'ON' if mqtt_on else 'OFF'}, brightness={mqtt_brightness}; "
                            f"Hardware: state={'ON' if hw_on else 'OFF'}, brightness={hw_brightness}. "
                            f"Publishing hardware state."
                        )
                    elif is_old:
                        self.logger.info(
                            f"Retained state is old ({message_age:.1f}s), "
                            f"publishing fresh hardware state: state={'ON' if hw_on else 'OFF'}, brightness={hw_brightness}"
                        )
                    self._publish_state(hw_state)
            else:
                # No retained message
                self.logger.info(
                    f"No retained state found, publishing initial state: "
                    f"state={'ON' if hw_on else 'OFF'}, brightness={hw_brightness}"
                )
                self._publish_state(hw_state)

        except Exception as e:
            self.logger.warning(
                f"Error checking retained state: {e}, publishing anyway"
            )
            self._publish_state(hw_state)

        finally:
            self._initial_state_published = True

    def _publish_state(self, state_dict: Dict[str, Any]):
        """Publish state to MQTT."""
        json_state = {}
        if "state" in state_dict:
            json_state["state"] = "ON" if state_dict["state"] else "OFF"
        if "brightness" in state_dict:
            json_state["brightness"] = state_dict["brightness"]

        if json_state:
            payload = json.dumps(json_state)
            self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)
            self.logger.info(f"Published state to {self.state_topic}: {payload}")

    def _on_hardware_state_change(self, state_dict: Dict[str, Any]):
        """
        Handle hardware state changes and publish to MQTT.

        Args:
            state_dict: State dictionary from hardware light
        """
        self._publish_state(state_dict)

    def handle_command(
        self, payload: str, is_retained: bool = False, timestamp: Optional[float] = None
    ):
        """
        Handle incoming MQTT command.

        Args:
            payload: JSON command payload
            is_retained: Whether this is a retained message
            timestamp: Message timestamp (for age checking)
        """
        if self.read_only:
            self.logger.debug("Ignoring command (read-only mode)")
            return

        # Check for old retained messages (>5 minutes)
        if is_retained and timestamp is not None:
            message_age = time.time() - timestamp
            if message_age > 300:  # 5 minutes
                self.logger.info(
                    f"Ignoring old retained command (age: {message_age:.1f}s)"
                )
                # Clear the old retained message
                self.mqtt_client.publish(self.command_topic, None, retain=True)
                return

        try:
            # Parse JSON command
            try:
                command = json.loads(payload)
            except json.JSONDecodeError:
                # Simple ON/OFF command
                command = {"state": payload}

            state = command.get("state", "ON")
            brightness = command.get("brightness")
            transition = command.get("transition")
            flash = command.get("flash")
            effect = command.get("effect")

            # Execute command
            if flash:
                # Flash effect
                count = 3 if flash == "short" else 5
                self.logger.info(f"Flashing {count} times")
                self.hardware_light.flash(count=count)
            elif transition:
                # Fade transition with optional easing effect
                target = (
                    brightness
                    if brightness is not None
                    else (255 if state == "ON" else 0)
                )
                duration = transition
                easing = effect if effect else self.hardware_light._default_easing
                self.logger.info(f"Fading to {target} over {duration}s with {easing}")
                self.hardware_light.fade_to(target, duration=duration, easing=easing)
            elif brightness is not None or effect:
                # Set brightness with optional effect (used as transition easing)
                if effect and brightness is not None:
                    self.logger.info(
                        f"Setting brightness to {brightness} with effect {effect}"
                    )
                elif effect:
                    self.logger.info(f"Setting default effect to {effect}")
                elif brightness is not None:
                    self.logger.info(f"Setting brightness to {brightness}")

                self.hardware_light.set(
                    state=state == "ON",
                    brightness=brightness,
                    effect=effect,
                )
            else:
                # Simple ON/OFF
                target = 255 if state == "ON" else 0
                self.logger.info(f"Setting to {state}")
                self.hardware_light.set_brightness(target)

            # Clear retained command after successful execution
            if is_retained:
                self.logger.debug("Clearing retained command")
                self.mqtt_client.publish(self.command_topic, None, retain=True)

        except Exception as e:
            self.logger.error(f"Error handling command: {e}")

    def matches_topic(self, topic: str) -> bool:
        """
        Check if this light handles the given topic.

        Args:
            topic: MQTT topic

        Returns:
            True if this light handles the topic
        """
        return topic == self.command_topic
