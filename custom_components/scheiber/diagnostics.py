"""Diagnostics support for Scheiber CAN."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    return {
        "entry": {
            "domain": DOMAIN,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "connected": runtime.connected,
        "last_error": runtime.last_error,
        "stats": runtime.stats,
        "discovered_devices": [
            {
                "key": device.key,
                "name": device.display_name,
                "type": device.device_type,
                "route_slug": device.route_slug,
                "bus_id": device.bus_id,
                "segment_id": device.segment_id,
                "identity_hex": device.identity_hex,
                "observations": device.observations,
                "outputs": {
                    output_name: {
                        "state": output.state,
                        "brightness": output.brightness,
                        "raw_brightness": output.raw_brightness,
                        "last_seen": output.last_seen,
                    }
                    for output_name, output in device.outputs.items()
                },
                "buttons": device.buttons,
                "families": sorted(device.families),
                "implemented": device.implemented,
            }
            for device in runtime.discovered_devices.values()
        ],
        "messages": [
            {
                "arbitration_id": summary.key,
                "count": summary.count,
                "dlc": summary.dlc,
                "last_data": summary.data_hex,
                "family": summary.family,
                "last_seen": summary.last_seen,
            }
            for summary in runtime.message_summaries.values()
        ],
    }
