"""
Switch entity for MQTT Bridge.

Handles MQTT discovery, state publishing, and command handling for switches.
"""

import json
import logging
import time
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt


class MQTTSwitch:
    """
    MQTT Switch entity with Home Assistant Discovery support.

    Each switch instance handles its own:
    - Discovery config publishing
    - State publishing (observer pattern)
    - Command topic subscription
    - Command parsing and execution
    """

    def __init__(
        self,
        hardware_switch,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        """
        Initialize MQTT Switch.

        Args:
            hardware_switch: Switch instance from scheiber module
            device_type: Device type (e.g., 'bloc9')
            device_id: Device bus ID
            mqtt_client: MQTT client instance
            mqtt_topic_prefix: MQTT topic prefix
            read_only: Read-only mode (no commands)
        """
        self.logger = logging.getLogger(f"{__name__}.{hardware_switch.entity_id}")
        self.hardware_switch = hardware_switch
        self.device_type = device_type
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only

        # Generate identifiers
        # switch_name is the output identifier (s1-s6 for bloc9)
        self.switch_name = f"s{hardware_switch.switch_nr + 1}"  # e.g., 's1', 's2'
        self.display_name = hardware_switch.name  # Human-readable name from config
        self.unique_id = f"scheiber_{device_type}_{device_id}_{self.switch_name}"
        self.entity_id = hardware_switch.entity_id  # e.g., 'navigation_light'

        # Generate topics (v5 schema)
        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{self.switch_name}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/switch/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"

        # Track MQTT state for comparison
        self._mqtt_state: Optional[str] = None
        self._mqtt_state_timestamp: Optional[float] = None
        self._initial_state_published = False
        self._checking_initial_state = False

        # Subscribe to hardware state changes
        hardware_switch.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        """Publish Home Assistant MQTT Discovery config."""
        discovery_config = {
            "name": self.display_name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "availability_topic": self.availability_topic,
            "optimistic": False,
            "device_class": "switch",
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
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
        hw_state = self.hardware_switch.get_state()
        hw_payload = "ON" if hw_state else "OFF"

        # Subscribe to state topic to fetch retained message
        self._setup_state_subscription(hw_payload)

    def _setup_state_subscription(self, hw_payload: str):
        """Subscribe to state topic to check existing retained state."""
        # Store hardware state for comparison
        self._pending_hw_payload = hw_payload
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
                    f"No retained state found after timeout, publishing initial state: {hw_payload}"
                )
                self._publish_state(hw_payload)
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

        hw_payload = self._pending_hw_payload

        try:
            # Parse retained message
            if message.payload:
                mqtt_payload = message.payload.decode().strip()

                # Check message age
                message_age = None
                if hasattr(message, "timestamp") and message.timestamp:
                    message_age = time.time() - message.timestamp

                # Compare states
                state_matches = hw_payload == mqtt_payload
                is_old = message_age is not None and message_age > 60

                if state_matches and not is_old:
                    self.logger.info(
                        f"Retained state matches hardware ({hw_payload}), skipping initial publish"
                    )
                else:
                    if not state_matches:
                        self.logger.info(
                            f"Retained state differs from hardware. "
                            f"MQTT: {mqtt_payload}; Hardware: {hw_payload}. "
                            f"Publishing hardware state."
                        )
                    elif is_old:
                        self.logger.info(
                            f"Retained state is old ({message_age:.1f}s), "
                            f"publishing fresh hardware state: {hw_payload}"
                        )
                    self._publish_state(hw_payload)
            else:
                # No retained message
                self.logger.info(
                    f"No retained state found, publishing initial state: {hw_payload}"
                )
                self._publish_state(hw_payload)

        except Exception as e:
            self.logger.warning(
                f"Error checking retained state: {e}, publishing anyway"
            )
            self._publish_state(hw_payload)

        finally:
            self._initial_state_published = True

    def _publish_state(self, payload: str):
        """Publish state to MQTT."""
        self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)
        self.logger.info(f"Published state to {self.state_topic}: {payload}")

    def _on_hardware_state_change(self, state_dict: Dict[str, Any]):
        """
        Handle hardware state changes and publish to MQTT.

        Args:
            state_dict: State dictionary from hardware switch
        """
        if "state" in state_dict:
            payload = "ON" if state_dict["state"] else "OFF"
            self._publish_state(payload)

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
            # Parse command (expect plain ON/OFF)
            state_bool = payload.strip().upper() == "ON"

            self.logger.info(f"Setting to {'ON' if state_bool else 'OFF'}")
            self.hardware_switch.set(state_bool)

            # Clear retained command after successful execution
            if is_retained:
                self.logger.debug("Clearing retained command")
                self.mqtt_client.publish(self.command_topic, None, retain=True)

        except Exception as e:
            self.logger.error(f"Error handling command: {e}")

    def matches_topic(self, topic: str) -> bool:
        """
        Check if this switch handles the given topic.

        Args:
            topic: MQTT topic

        Returns:
            True if this switch handles the topic
        """
        return topic == self.command_topic
