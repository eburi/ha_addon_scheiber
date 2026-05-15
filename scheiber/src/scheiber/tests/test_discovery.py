import can

from scheiber.discovery import classify_bloc9_message, decode_bloc9_bus_id


def test_decode_bloc9_bus_id_from_status_message():
    assert decode_bloc9_bus_id(0x021A06B8) == 7
    assert decode_bloc9_bus_id(0x021606D0) == 10
    assert decode_bloc9_bus_id(0x02160601) is None


def test_classify_bloc9_state_update_message():
    msg = can.Message(
        arbitration_id=0x021A06B8,
        data=bytes([0x6B, 0x00, 0x11, 0x01, 0x00, 0x00, 0x01, 0x01]),
        is_extended_id=True,
    )

    result = classify_bloc9_message(msg)

    assert result["kind"] == "state_update"
    assert result["bus_id"] == 7
    assert result["group"] == "s5_s6"
    assert result["outputs"]["s5"]["state"] is True
    assert result["outputs"]["s5"]["raw_brightness"] == 0x6B
    assert result["outputs"]["s6"]["effective_brightness"] == 255


def test_classify_bloc9_heartbeat_message():
    msg = can.Message(
        arbitration_id=0x000006B8,
        data=bytes([0x00] * 8),
        is_extended_id=True,
    )

    result = classify_bloc9_message(msg)

    assert result == {
        "kind": "heartbeat",
        "bus_id": 7,
        "arbitration_id": "0x000006B8",
    }
