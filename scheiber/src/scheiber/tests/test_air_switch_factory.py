"""Tests for wiring the air_switch device type through the system factory."""

from scheiber import create_scheiber_system
from scheiber.air_switch import AirSwitchDevice


def test_create_scheiber_system_builds_air_switch_device(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config_path.write_text("""
devices:
  - type: air_switch
    bus_id: 1
    name: Bow Salon Air Switch
    buttons:
      - name: Bottom Left
        entity_id: bow_salon_bottom_left
        identity: "52AB81"
        button_index: 1
      - name: Top Left
        entity_id: bow_salon_top_left
        identity: "52AB81"
        button_index: 2
""")

    system = create_scheiber_system(
        can_interface="vcan0", config_path=str(config_path), read_only=True
    )

    devices = system.get_all_devices()
    assert len(devices) == 1
    device = devices[0]
    assert isinstance(device, AirSwitchDevice)
    assert device.device_type == "air_switch"

    buttons = device.get_air_switch_buttons()
    assert {button.entity_id for button in buttons} == {
        "bow_salon_bottom_left",
        "bow_salon_top_left",
    }


def test_air_switch_device_routes_through_scheiber_system(tmp_path):
    import can

    config_path = tmp_path / "scheiber-config.yaml"
    config_path.write_text("""
devices:
  - type: air_switch
    bus_id: 1
    buttons:
      - name: Bottom Left
        entity_id: bow_salon_bottom_left
        identity: "52AB81"
        button_index: 1
""")

    system = create_scheiber_system(
        can_interface="vcan0", config_path=str(config_path), read_only=True
    )
    device = system.get_all_devices()[0]
    button = device.get_air_switch_buttons()[0]
    events = []
    button.subscribe(lambda event: events.append(event))

    msg = can.Message(
        arbitration_id=0x04001A80,
        data=bytes.fromhex("0152AB8181"),
        is_extended_id=True,
    )
    system._on_can_message(msg)

    assert events == [{"event_type": "press"}]
