"""Tests for scheiber.button_discovery classification helpers."""

import can

from scheiber.button_discovery import (
    classify_air_switch_message,
    classify_button_source_message,
    diff_status_bits,
)


def _msg(arbitration_id: int, data: bytes) -> can.Message:
    return can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)


def test_classify_air_switch_message_decodes_press():
    msg = _msg(0x04001A80, bytes.fromhex("0152AB8182"))

    result = classify_air_switch_message(msg)

    assert result["kind"] == "air_switch_button"
    assert result["identity_hex"] == "52AB81"
    assert result["button_index"] == 2
    assert result["pressed"] is True
    assert result["status_hex"] == "0x82"


def test_classify_air_switch_message_decodes_release():
    msg = _msg(0x04001A82, bytes.fromhex("0152AB8102"))

    result = classify_air_switch_message(msg)

    assert result["pressed"] is False
    assert result["button_index"] == 2
    assert result["identity_hex"] == "52AB81"


def test_classify_air_switch_message_matches_all_known_low_bytes():
    for low_byte in (0x80, 0x82, 0x83):
        arbitration_id = 0x04001A00 | low_byte
        msg = _msg(arbitration_id, bytes.fromhex("0152AB8181"))
        result = classify_air_switch_message(msg)
        assert result is not None
        assert result["button_index"] == 1


def test_classify_air_switch_message_rejects_wired_zero_identity_shape():
    # Deferred wired-family shape: constant zero identity bytes.
    msg = _msg(0x04001809, bytes.fromhex("0000000186"))

    assert classify_air_switch_message(msg) is None


def test_classify_air_switch_message_rejects_other_prefixes():
    msg = _msg(0x04001F98, bytes.fromhex("0152AB8182"))

    assert classify_air_switch_message(msg) is None


def test_classify_air_switch_message_rejects_wrong_length():
    msg = _msg(0x04001A80, bytes.fromhex("0152AB81820011"))

    assert classify_air_switch_message(msg) is None


def test_classify_air_switch_message_rejects_non_leader_byte():
    msg = _msg(0x04001A80, bytes.fromhex("0052AB8182"))

    assert classify_air_switch_message(msg) is None


def test_classify_button_source_message_still_matches_known_families():
    # The broad/provisional classifier remains available for investigation
    # of both the wireless and deferred wired families.
    wireless = _msg(0x04001A80, bytes.fromhex("0152AB8182"))
    wired = _msg(0x04001808, bytes.fromhex("0000000185"))

    wireless_result = classify_button_source_message(wireless)
    wired_result = classify_button_source_message(wired)

    assert wireless_result["source_family"] == "wireless_light_air_switch_interface"
    assert wired_result["source_family"] == "button_panel_or_key_interface"


def test_diff_status_bits_reports_rising_and_falling():
    transitions = diff_status_bits(0x82, 0x02)

    assert transitions["falling_bits"] == [7]
    assert transitions["rising_bits"] == []
