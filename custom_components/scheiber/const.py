"""Constants for the Scheiber CAN integration."""

from __future__ import annotations

DOMAIN = "scheiber"

CONF_CAN_INTERFACE = "can_interface"
CONF_READ_ONLY = "read_only"
CONF_DISCOVERY_ONLY = "discovery_only"
CONF_CONFIG_PATH = "config_path"
CONF_STATE_FILE = "state_file"
CONF_MAX_MESSAGE_IDS = "max_message_ids"

DEFAULT_CAN_INTERFACE = "can0"
DEFAULT_READ_ONLY = True
DEFAULT_DISCOVERY_ONLY = True
DEFAULT_MAX_MESSAGE_IDS = 200

EVENT_AIR_SWITCH_PRESS = f"{DOMAIN}_air_switch_press"

ATTR_DISCOVERY_KIND = "discovery_kind"
ATTR_ROUTE_SLUG = "route_slug"
ATTR_BUS_ID = "bus_id"
ATTR_SEGMENT_ID = "segment_id"
ATTR_OUTPUT = "output"

LIGHT_EFFECTS = [
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
]
