"""Home Assistant integration for Scheiber CAN bus devices."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ScheiberRuntime

PLATFORMS: tuple[Platform, ...] = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
)

ScheiberConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: ScheiberConfigEntry) -> bool:
    """Set up Scheiber CAN from a config entry."""
    runtime = ScheiberRuntime(hass, entry)
    await runtime.async_start()
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ScheiberConfigEntry) -> bool:
    """Unload Scheiber CAN config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ScheiberConfigEntry
) -> None:
    """Reload config entry after options updates."""
    await hass.config_entries.async_reload(entry.entry_id)
