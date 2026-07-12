"""Tests for scheiber.air_switch runtime device."""

import can
import pytest

from scheiber.air_switch import (
    AIR_SWITCH_MATCH_MASK,
    AIR_SWITCH_MATCH_PATTERN,
    AirSwitchDevice,
)


def _msg(arbitration_id: int, data: bytes) -> can.Message:
    return can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)


@pytest.fixture
def device_config():
    return {
        "buttons": [
            {
                "name": "Bottom Left",
                "entity_id": "bow_salon_bottom_left",
                "identity": "52AB81",
                "button_index": 1,
            },
            {
                "name": "Top Left",
                "entity_id": "bow_salon_top_left",
                "identity": "52AB81",
                "button_index": 2,
            },
        ]
    }


@pytest.fixture
def air_switch_device(device_config, mock_scheiber_can_bus, mock_logger):
    return AirSwitchDevice(
        device_id=1,
        can_bus=mock_scheiber_can_bus,
        config=device_config,
        logger=mock_logger,
    )


def test_get_matchers_covers_whole_family(air_switch_device):
    matchers = air_switch_device.get_matchers()

    assert len(matchers) == 1
    assert matchers[0].pattern == AIR_SWITCH_MATCH_PATTERN
    assert matchers[0].mask == AIR_SWITCH_MATCH_MASK
    assert matchers[0].matches(_msg(0x04001A80, bytes(5)))
    assert matchers[0].matches(_msg(0x04001A82, bytes(5)))
    assert matchers[0].matches(_msg(0x04001A83, bytes(5)))
    assert not matchers[0].matches(_msg(0x04001F98, bytes(5)))


def test_get_air_switch_buttons_returns_configured_buttons(air_switch_device):
    buttons = air_switch_device.get_air_switch_buttons()

    assert {button.entity_id for button in buttons} == {
        "bow_salon_bottom_left",
        "bow_salon_top_left",
    }


def test_process_message_fires_press_on_rising_edge_only(air_switch_device):
    button = next(
        b for b in air_switch_device.get_air_switch_buttons() if b.button_index == 2
    )
    events = []
    button.subscribe(lambda event: events.append(event))

    # Redundant press frames (same identity/status on all three low bytes).
    air_switch_device.process_message(_msg(0x04001A80, bytes.fromhex("0152AB8182")))
    air_switch_device.process_message(_msg(0x04001A82, bytes.fromhex("0152AB8182")))
    air_switch_device.process_message(_msg(0x04001A83, bytes.fromhex("0152AB8182")))

    assert events == [{"event_type": "press"}]

    # Release, then press again: should fire exactly one more press event.
    air_switch_device.process_message(_msg(0x04001A80, bytes.fromhex("0152AB8102")))
    air_switch_device.process_message(_msg(0x04001A80, bytes.fromhex("0152AB8182")))

    assert events == [{"event_type": "press"}, {"event_type": "press"}]


def test_process_message_ignores_other_configured_button(air_switch_device):
    button1 = next(
        b for b in air_switch_device.get_air_switch_buttons() if b.button_index == 1
    )
    events = []
    button1.subscribe(lambda event: events.append(event))

    # Button index 2 press should not notify button index 1's observers.
    air_switch_device.process_message(_msg(0x04001A80, bytes.fromhex("0152AB8182")))

    assert events == []


def test_process_message_logs_unknown_button_once(air_switch_device, mock_logger):
    unknown_msg = _msg(0x04001A80, bytes.fromhex("0152AB8184"))  # button_index 4

    air_switch_device.process_message(unknown_msg)
    air_switch_device.process_message(unknown_msg)

    assert mock_logger.warning.call_count == 1


def test_process_message_ignores_non_air_switch_frames(air_switch_device):
    # Deferred wired-family shape must not be routed to any button.
    wired_msg = _msg(0x04001A80, bytes.fromhex("0000000186"))

    # Should not raise and should not match any configured button.
    air_switch_device.process_message(wired_msg)


def test_state_persistence_is_a_no_op(air_switch_device):
    assert air_switch_device.store_to_state() == {}
    air_switch_device.restore_from_state({"anything": True})  # must not raise
