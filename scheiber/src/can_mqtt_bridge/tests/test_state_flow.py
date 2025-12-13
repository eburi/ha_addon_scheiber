"""
Test to verify CAN message -> hardware state -> MQTT state flow.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import Mock, MagicMock
import can
from scheiber.bloc9 import Bloc9Device
from scheiber.can_bus import ScheiberCanBus
from can_mqtt_bridge.light import MQTTLight


def test_can_to_mqtt_state_flow():
    """Test that CAN messages trigger MQTT state updates."""

    # Create mock CAN bus
    mock_bus = Mock(spec=ScheiberCanBus)

    # Create Bloc9 device with one light on S5
    device = Bloc9Device(
        device_id=7,
        can_bus=mock_bus,
        lights_config={"s5": {"name": "Test Light", "entity_id": "test_light"}},
    )

    # Get the light
    lights = device.get_lights()
    assert len(lights) == 1
    hardware_light = lights[0]

    # Create MQTT light wrapper
    mock_mqtt_client = Mock()
    mqtt_light = MQTTLight(
        hardware_light=hardware_light,
        device_type="bloc9",
        device_id=7,
        mqtt_client=mock_mqtt_client,
        mqtt_topic_prefix="homeassistant",
        read_only=False,
    )

    # Verify observer was subscribed
    assert len(hardware_light._observers) == 1

    # Simulate CAN message for S5/S6 change (switches 4 and 5)
    # S5 ON with brightness 200, S6 OFF
    # Message format: 8 bytes [s5_brightness, 0, 0, s5_state_bit, s6_brightness, 0, 0, s6_state_bit]
    can_message = can.Message(
        arbitration_id=0x021A06B8,  # S5/S6 change for device 7
        data=bytes(
            [200, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]
        ),  # S5: brightness=200 ON, S6: OFF
        is_extended_id=True,
    )

    # Process the message through the device
    device.process_message(can_message)

    # Verify MQTT publish was called with correct state
    assert mock_mqtt_client.publish.called
    calls = mock_mqtt_client.publish.call_args_list

    # Should have published state update
    state_published = False
    for call in calls:
        topic = call[0][0]
        payload = call[0][1]
        if "state" in topic and "test_light" not in topic:  # Not the entity_id topic
            print(f"State update: {topic} = {payload}")
            state_published = True
            # Verify payload contains expected state
            import json

            state = json.loads(payload)
            assert state["state"] == "ON"
            assert state["brightness"] == 200

    assert state_published, "State was not published to MQTT"
    print("✓ CAN -> Hardware -> MQTT state flow working correctly")


if __name__ == "__main__":
    test_can_to_mqtt_state_flow()
