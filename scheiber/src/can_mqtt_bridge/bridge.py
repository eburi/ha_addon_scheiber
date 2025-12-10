"""
MQTT Bridge implementation for Home Assistant integration.

Bridges Scheiber CAN devices to Home Assistant via MQTT Discovery.
"""

import json
import logging
import threading
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt

# Add parent directory to path for scheiber module
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheiber import create_scheiber_system, ScheiberSystem


class MQTTBridge:
    """
    MQTT Bridge for Home Assistant integration.

    Features:
    - Home Assistant MQTT Discovery
    - State publishing with observer pattern
    - Command handling for lights (brightness, fade, flash)
    - Automatic reconnection
    - Clean shutdown
    """

    def __init__(
        self,
        can_interface: str,
        mqtt_host: str,
        mqtt_port: int = 1883,
        mqtt_user: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        mqtt_topic_prefix: str = "homeassistant",
        config_path: Optional[str] = None,
        state_file: Optional[str] = None,
        log_level: str = "info",
        read_only: bool = False,
    ):
        """
        Initialize MQTT Bridge.

        Args:
            can_interface: CAN interface name (e.g., 'can0')
            mqtt_host: MQTT broker hostname
            mqtt_port: MQTT broker port
            mqtt_user: MQTT username (optional)
            mqtt_password: MQTT password (optional)
            mqtt_topic_prefix: Topic prefix (default: 'homeassistant')
            config_path: Path to scheiber.yaml config file
            state_file: Path to state persistence file
            log_level: Logging level
            read_only: Read-only mode (no CAN commands)
        """
        self.logger = logging.getLogger(__name__)
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only
        self._running = False

        # Create Scheiber system
        self.logger.info("Creating Scheiber system...")
        self.system: ScheiberSystem = create_scheiber_system(
            can_interface=can_interface,
            config_path=config_path,
            state_file=state_file,
            log_level=log_level,
            read_only=read_only,
        )

        # Create MQTT client
        self.logger.info(f"Connecting to MQTT broker {mqtt_host}:{mqtt_port}...")
        self.mqtt_client = mqtt.Client()

        if mqtt_user and mqtt_password:
            self.mqtt_client.username_pw_set(mqtt_user, mqtt_password)

        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        try:
            self.mqtt_client.connect(mqtt_host, mqtt_port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

        # Track subscriptions
        self._light_subscriptions: Dict[str, Any] = {}

    def start(self):
        """Start the bridge."""
        if self._running:
            return

        self._running = True
        self.logger.info("Starting MQTT bridge...")

        # Subscribe to device changes
        for device in self.system.get_all_devices():
            self._setup_device(device)

        # Subscribe to CAN statistics
        self.system.subscribe_to_stats(self._on_can_stats)

        # Start CAN system
        self.system.start()

        self.logger.info("MQTT bridge started")

    def stop(self):
        """Stop the bridge."""
        if not self._running:
            return

        self._running = False
        self.logger.info("Stopping MQTT bridge...")

        # Stop system
        self.system.stop()

        # Stop MQTT
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

        self.logger.info("MQTT bridge stopped")

    def _setup_device(self, device):
        """
        Setup MQTT for a device.

        Args:
            device: ScheiberCanDevice instance
        """
        device_type = device.__class__.__name__.lower().replace("device", "")
        device_id = device.device_id

        self.logger.info(f"Setting up MQTT for {device_type} device {device_id}")

        # Setup lights
        for light in device.get_lights():
            self._setup_light(device_type, device_id, light)

        # Setup switches
        for switch in device.get_switches():
            self._setup_switch(device_type, device_id, switch)

    def _setup_light(self, device_type: str, device_id: int, light):
        """
        Setup MQTT for a light with Home Assistant Discovery.

        Args:
            device_type: Device type (e.g., 'bloc9')
            device_id: Device bus ID
            light: DimmableLight instance
        """
        light_name = light.name.lower()
        unique_id = f"scheiber_{device_type}_{device_id}_{light_name}"

        # Base topics
        base_topic = (
            f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{light_name}"
        )
        config_topic = f"{self.mqtt_topic_prefix}/light/{unique_id}/config"
        state_topic = f"{base_topic}/state"
        brightness_state_topic = f"{base_topic}/brightness"
        command_topic = f"{base_topic}/set"
        brightness_command_topic = f"{base_topic}/set_brightness"

        # Home Assistant Discovery config
        discovery_config = {
            "name": f"Scheiber {light_name.upper()}",
            "unique_id": unique_id,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "manufacturer": "Scheiber",
                "model": "Marine Lighting Control System",
            },
            "state_topic": state_topic,
            "command_topic": command_topic,
            "brightness_state_topic": brightness_state_topic,
            "brightness_command_topic": brightness_command_topic,
            "brightness_scale": 255,
            "payload_on": "ON",
            "payload_off": "OFF",
            "optimistic": False,
            "schema": "json",
        }

        # Publish discovery config
        self.mqtt_client.publish(
            config_topic, json.dumps(discovery_config), retain=True
        )

        self.logger.debug(f"Published discovery config for {unique_id}")

        # Subscribe to commands
        self.mqtt_client.subscribe(command_topic)
        self.mqtt_client.subscribe(brightness_command_topic)

        self.logger.debug(f"Subscribed to commands for {unique_id}")

        # Subscribe to light state changes
        def on_light_change(prop: str, value: Any):
            if prop == "state":
                # Publish state
                payload = "ON" if value else "OFF"
                self.mqtt_client.publish(state_topic, payload, retain=True)
                self.logger.debug(f"{unique_id} state: {payload}")
            elif prop == "brightness":
                # Publish brightness
                self.mqtt_client.publish(
                    brightness_state_topic, str(value), retain=True
                )
                self.logger.debug(f"{unique_id} brightness: {value}")

        light.subscribe(on_light_change)
        self._light_subscriptions[unique_id] = (
            light,
            on_light_change,
            command_topic,
            brightness_command_topic,
        )

        # Publish initial state
        on_light_change("state", light.is_on())
        on_light_change("brightness", light.get_brightness())

    def _setup_switch(self, device_type: str, device_id: int, switch):
        """
        Setup MQTT for a switch with Home Assistant Discovery.

        Args:
            device_type: Device type (e.g., 'bloc9')
            device_id: Device bus ID
            switch: Switch instance
        """
        switch_name = switch.name.lower().replace(" ", "_")
        unique_id = f"scheiber_{device_type}_{device_id}_{switch.entity_id}"

        # Base topics
        base_topic = f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{switch.entity_id}"
        config_topic = f"{self.mqtt_topic_prefix}/switch/{unique_id}/config"
        state_topic = f"{base_topic}/state"
        command_topic = f"{base_topic}/set"

        # Home Assistant Discovery config
        discovery_config = {
            "name": f"Scheiber {switch.name}",
            "unique_id": unique_id,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "manufacturer": "Scheiber",
                "model": "Marine Lighting Control System",
            },
            "state_topic": state_topic,
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "optimistic": False,
        }

        # Publish discovery config
        self.mqtt_client.publish(
            config_topic, json.dumps(discovery_config), retain=True
        )

        self.logger.debug(f"Published switch discovery config for {unique_id}")

        # Subscribe to commands
        self.mqtt_client.subscribe(command_topic)

        self.logger.debug(f"Subscribed to switch commands for {unique_id}")

        # Subscribe to switch state changes
        def on_switch_change(prop: str, value: Any):
            if prop == "state":
                # Publish state
                payload = "ON" if value else "OFF"
                self.mqtt_client.publish(state_topic, payload, retain=True)
                self.logger.debug(f"{unique_id} state: {payload}")

        switch.subscribe(on_switch_change)
        self._light_subscriptions[unique_id] = (
            switch,
            on_switch_change,
            command_topic,
            None,  # No brightness topic for switches
        )

        # Publish initial state
        on_switch_change("state", switch.get_state())

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            self.logger.info("Connected to MQTT broker")

            # Resubscribe to all command topics if reconnecting
            for unique_id, (
                device,
                callback,
                cmd_topic,
                brightness_topic,
            ) in self._light_subscriptions.items():
                client.subscribe(cmd_topic)
                if brightness_topic:  # Skip None for switches
                    client.subscribe(brightness_topic)
                self.logger.debug(f"Resubscribed to {unique_id}")
        else:
            self.logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        """
        Handle incoming MQTT messages (commands from Home Assistant).

        Args:
            client: MQTT client
            userdata: User data
            msg: MQTT message
        """
        if self.read_only:
            self.logger.debug(f"Ignoring command (read-only mode): {msg.topic}")
            return

        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        self.logger.debug(f"MQTT message: {topic} = {payload}")

        # Find the device (light or switch) for this topic
        device = None
        is_brightness_command = False
        is_switch = False

        for unique_id, (
            d,
            callback,
            cmd_topic,
            brightness_topic,
        ) in self._light_subscriptions.items():
            if topic == cmd_topic:
                device = d
                is_brightness_command = False
                # Check if it's a switch (no brightness topic)
                is_switch = brightness_topic is None
                break
            elif brightness_topic and topic == brightness_topic:
                device = d
                is_brightness_command = True
                is_switch = False
                break

        if not device:
            self.logger.warning(f"No device found for topic: {topic}")
            return

        # Handle command based on device type
        try:
            if is_switch:
                # Switch command - simple ON/OFF
                state = payload == "ON"
                self.logger.info(f"Setting {device.name} to {payload}")
                device.set(state)
            elif is_brightness_command:
                # Brightness command for light
                brightness = int(payload)
                self.logger.info(f"Setting {device.name} brightness to {brightness}")
                device.set_brightness(brightness)
            else:
                # Light state command (JSON with optional transition)
                try:
                    command = json.loads(payload)
                except json.JSONDecodeError:
                    # Simple ON/OFF command
                    command = {"state": payload}

                state = command.get("state", "ON")
                brightness = command.get("brightness")
                transition = command.get("transition")
                flash = command.get("flash")

                if flash:
                    # Flash effect
                    count = 3 if flash == "short" else 5
                    self.logger.info(f"Flashing {device.name} {count} times")
                    device.flash(count=count)
                elif transition:
                    # Fade transition
                    target = (
                        brightness
                        if brightness is not None
                        else (255 if state == "ON" else 0)
                    )
                    duration_ms = int(transition * 1000)
                    self.logger.info(
                        f"Fading {device.name} to {target} over {duration_ms}ms"
                    )
                    device.fade_to(target, duration_ms=duration_ms)
                elif brightness is not None:
                    # Set brightness
                    self.logger.info(
                        f"Setting {device.name} brightness to {brightness}"
                    )
                    device.set_brightness(brightness)
                else:
                    # Simple ON/OFF
                    target = 255 if state == "ON" else 0
                    self.logger.info(f"Setting {device.name} to {state}")
                    device.set_brightness(target)

        except Exception as e:
            self.logger.error(f"Error handling command for {device.name}: {e}")

    def _on_can_stats(self, stats: Dict[str, Any]):
        """
        Handle CAN statistics updates.

        Args:
            stats: Statistics dictionary
        """
        self.logger.debug(
            f"CAN Stats: {stats['messages_received']} rx, "
            f"{stats['messages_sent']} tx, "
            f"{stats['unique_ids']} unique IDs"
        )
