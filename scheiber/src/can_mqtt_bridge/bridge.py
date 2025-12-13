"""
MQTT Bridge implementation for Home Assistant integration.

Bridges Scheiber CAN devices to Home Assistant via MQTT Discovery.
"""

import json
import logging
import threading
from typing import Optional, Dict, Any, List
import paho.mqtt.client as mqtt

# Add parent directory to path for scheiber module
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheiber import create_scheiber_system, ScheiberSystem
from .light import MQTTLight
from .switch import MQTTSwitch
from .sensor import MQTTSensor


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

        # Track MQTT entities (lights and switches)
        self._mqtt_entities: List[Any] = []

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

        # Create MQTT light entities
        for hardware_light in device.get_lights():
            mqtt_light = MQTTLight(
                hardware_light=hardware_light,
                device_type=device_type,
                device_id=device_id,
                mqtt_client=self.mqtt_client,
                mqtt_topic_prefix=self.mqtt_topic_prefix,
                read_only=self.read_only,
            )
            mqtt_light.publish_discovery()
            mqtt_light.publish_availability(True)
            mqtt_light.subscribe_to_commands()
            # Check MQTT retained state and publish if needed (missing/old/different)
            mqtt_light.publish_initial_state()
            self._mqtt_entities.append(mqtt_light)

        # Create MQTT switch entities
        for hardware_switch in device.get_switches():
            mqtt_switch = MQTTSwitch(
                hardware_switch=hardware_switch,
                device_type=device_type,
                device_id=device_id,
                mqtt_client=self.mqtt_client,
                mqtt_topic_prefix=self.mqtt_topic_prefix,
                read_only=self.read_only,
            )
            mqtt_switch.publish_discovery()
            mqtt_switch.publish_availability(True)
            mqtt_switch.subscribe_to_commands()
            # Check MQTT retained state and publish if needed (missing/old/different)
            mqtt_switch.publish_initial_state()
            self._mqtt_entities.append(mqtt_switch)

        # Create MQTT sensor entities
        for hardware_sensor in device.get_sensors():
            mqtt_sensor = MQTTSensor(
                hardware_sensor=hardware_sensor,
                device_type=device_type,
                device_id=device_id,
                mqtt_client=self.mqtt_client,
                mqtt_topic_prefix=self.mqtt_topic_prefix,
            )
            mqtt_sensor.publish_discovery()
            mqtt_sensor.publish_availability(True)
            mqtt_sensor.subscribe_to_updates()
            mqtt_sensor.publish_state()
            self._mqtt_entities.append(mqtt_sensor)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            self.logger.info("Connected to MQTT broker")

            # Resubscribe to all command topics if reconnecting
            for entity in self._mqtt_entities:
                entity.subscribe_to_commands()
                self.logger.debug(f"Resubscribed to {entity.unique_id}")
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
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        is_retained = msg.retain
        timestamp = msg.timestamp

        self.logger.debug(f"MQTT message: {topic} = {payload} (retained={is_retained})")

        # Find the entity that handles this topic
        for entity in self._mqtt_entities:
            if entity.matches_topic(topic):
                entity.handle_command(
                    payload, is_retained=is_retained, timestamp=timestamp
                )
                return

        self.logger.warning(f"No entity found for topic: {topic}")

    def _on_can_stats(self, stats: Dict[str, Any]):
        """
        Handle CAN statistics updates and publish to MQTT.

        Args:
            stats: Statistics dictionary
        """
        self.logger.debug(
            f"CAN Stats: {stats['messages_received']} rx, "
            f"{stats['messages_sent']} tx, "
            f"{stats['unique_ids']} unique IDs"
        )

        # Publish stats to MQTT
        try:
            topic = f"{self.mqtt_topic_prefix}/scheiber/can/stats/state"
            payload = json.dumps(stats)
            self.mqtt_client.publish(topic, payload, retain=False)
        except Exception as e:
            self.logger.error(f"Failed to publish CAN stats to MQTT: {e}")
