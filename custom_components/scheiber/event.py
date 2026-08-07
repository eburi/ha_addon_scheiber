"""Event entities for Scheiber AirSwitch observations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .coordinator import DiscoveredDevice, ScheiberRuntime
from .entity import ScheiberDiscoveredEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AirSwitch event entities known at setup time."""
    runtime = entry.runtime_data
    entities: list[EventEntity] = []
    known: set[str] = set()
    for device in runtime.discovered_devices.values():
        entities.extend(_air_switch_events(runtime, device, known))

    def _async_add_discovered_device(device: DiscoveredDevice) -> None:
        new_entities = _air_switch_events(runtime, device, known)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        runtime.async_add_discovery_listener(_async_add_discovered_device)
    )
    async_add_entities(entities)


def _air_switch_events(
    runtime: ScheiberRuntime, device: DiscoveredDevice, known: set[str]
) -> list[EventEntity]:
    if device.device_type != "air_switch":
        return []

    entities: list[EventEntity] = []
    for button_index in range(1, 9):
        unique_key = f"{device.key}_button_{button_index}"
        if unique_key in known:
            continue
        known.add(unique_key)
        entities.append(ScheiberAirSwitchEvent(runtime, device, button_index))
    return entities


class ScheiberAirSwitchEvent(ScheiberDiscoveredEntity, EventEntity):
    """AirSwitch button press event."""

    _attr_event_types = ["press"]

    def __init__(
        self, runtime: ScheiberRuntime, device: DiscoveredDevice, button_index: int
    ) -> None:
        """Initialize event entity."""
        super().__init__(runtime, device, f"{device.key}_button_{button_index}")
        self.button_index = button_index
        self._attr_name = f"Button {button_index}"
        self._last_pressed_seen: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener(self.device.key, self._handle_update)
        )

    def _handle_update(self) -> None:
        button = self.device.buttons.get(self.button_index)
        if not button or not button.get("pressed"):
            return
        last_seen = button.get("last_seen")
        if last_seen == self._last_pressed_seen:
            return
        self._last_pressed_seen = last_seen
        self._trigger_event("press", {"button_index": self.button_index})
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return button diagnostics."""
        return {"button_index": self.button_index}
