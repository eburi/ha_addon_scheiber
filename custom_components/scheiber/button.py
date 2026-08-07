"""Button entities for Scheiber CAN."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .entity import ScheiberNetworkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scheiber buttons."""
    async_add_entities([ScheiberRefreshDiscoveryButton(entry.runtime_data)])


class ScheiberRefreshDiscoveryButton(ScheiberNetworkEntity, ButtonEntity):
    """Button to refresh HA states from currently known observations."""

    _attr_name = "Refresh discovery"

    def __init__(self, runtime) -> None:
        """Initialize button."""
        super().__init__(runtime, "refresh_discovery")

    async def async_press(self) -> None:
        """Refresh all Scheiber entities."""
        self.runtime._notify("all", "network", "messages")
