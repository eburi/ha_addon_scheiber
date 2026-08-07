"""Sensor entities for Scheiber CAN."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .coordinator import DiscoveredDevice, ScheiberRuntime
from .entity import ScheiberDiscoveredEntity, ScheiberNetworkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scheiber CAN sensors."""
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        ScheiberStatSensor(
            runtime,
            "messages_received",
            "Messages received",
            lambda stats: stats.get("messages_received"),
            icon="mdi:counter",
        ),
        ScheiberStatSensor(
            runtime,
            "messages_sent",
            "Messages sent",
            lambda stats: stats.get("messages_sent"),
            icon="mdi:counter",
        ),
        ScheiberStatSensor(
            runtime,
            "unique_ids",
            "Unique arbitration IDs",
            lambda stats: stats.get("unique_ids"),
            icon="mdi:identifier",
        ),
        ScheiberStatSensor(
            runtime,
            "uptime_seconds",
            "CAN uptime",
            lambda stats: stats.get("uptime_seconds"),
            device_class=SensorDeviceClass.DURATION,
            native_unit=UnitOfTime.SECONDS,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        ScheiberStatSensor(
            runtime,
            "message_rate",
            "Message rate",
            _messages_per_second,
            native_unit="msg/s",
            icon="mdi:speedometer",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        ScheiberDiscoverySummarySensor(runtime),
        ScheiberMessageTableSensor(runtime),
    ]

    known: set[str] = set()
    for device in runtime.discovered_devices.values():
        entities.extend(_discovered_device_sensors(runtime, device, known))

    def _async_add_discovered_device(device: DiscoveredDevice) -> None:
        new_entities = _discovered_device_sensors(runtime, device, known)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        runtime.async_add_discovery_listener(_async_add_discovered_device)
    )
    async_add_entities(entities)


def _discovered_device_sensors(
    runtime: ScheiberRuntime, device: DiscoveredDevice, known: set[str]
) -> list[SensorEntity]:
    unique_key = f"{device.key}_status"
    if unique_key in known:
        return []
    known.add(unique_key)
    return [ScheiberDiscoveredDeviceSensor(runtime, device)]


class ScheiberStatSensor(ScheiberNetworkEntity, SensorEntity):
    """CAN network statistic sensor."""

    def __init__(
        self,
        runtime,
        key: str,
        name: str,
        value_fn: Callable[[dict[str, Any]], Any],
        *,
        device_class: SensorDeviceClass | None = None,
        native_unit: str | None = None,
        icon: str | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        """Initialize sensor."""
        super().__init__(runtime, key)
        self._attr_translation_key = key
        self._attr_name = name
        self._value_fn = value_fn
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit
        self._attr_icon = icon
        self._attr_state_class = state_class

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener("network", self.async_write_ha_state)
        )

    @property
    def native_value(self) -> Any:
        """Return native value."""
        return self._value_fn(self.runtime.stats)


class ScheiberDiscoverySummarySensor(ScheiberNetworkEntity, SensorEntity):
    """Summary of discovered devices."""

    _attr_name = "Discovered devices"
    _attr_icon = "mdi:devices"

    def __init__(self, runtime) -> None:
        """Initialize sensor."""
        super().__init__(runtime, "discovered_devices")

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener("all", self.async_write_ha_state)
        )

    @property
    def native_value(self) -> int:
        """Return discovered device count."""
        return len(self.runtime.discovered_devices)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return discovered device summary."""
        return {
            "devices": [
                {
                    "key": device.key,
                    "name": device.display_name,
                    "type": device.device_type,
                    "route_slug": device.route_slug,
                    "bus_id": device.bus_id,
                    "segment_id": device.segment_id,
                    "identity_hex": device.identity_hex,
                    "observations": device.observations,
                    "outputs": sorted(device.outputs),
                    "buttons": sorted(device.buttons),
                    "families": sorted(device.families),
                    "implemented": device.implemented,
                }
                for device in self.runtime.discovered_devices.values()
            ]
        }


class ScheiberMessageTableSensor(ScheiberNetworkEntity, SensorEntity):
    """Raw arbitration ID table as sensor attributes."""

    _attr_name = "CAN messages"
    _attr_icon = "mdi:table"

    def __init__(self, runtime) -> None:
        """Initialize sensor."""
        super().__init__(runtime, "can_messages")

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener("messages", self.async_write_ha_state)
        )

    @property
    def native_value(self) -> int:
        """Return observed arbitration ID count."""
        return len(self.runtime.message_summaries)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return raw message summary table."""
        return {
            "messages": [
                {
                    "arbitration_id": summary.key,
                    "count": summary.count,
                    "dlc": summary.dlc,
                    "last_data": summary.data_hex,
                    "family": summary.family,
                    "last_seen": summary.last_seen,
                }
                for summary in self.runtime.message_summaries.values()
            ]
        }


class ScheiberDiscoveredDeviceSensor(ScheiberDiscoveredEntity, SensorEntity):
    """Per-device discovery status sensor."""

    _attr_icon = "mdi:chip"

    def __init__(self, runtime: ScheiberRuntime, device: DiscoveredDevice) -> None:
        """Initialize discovered device status sensor."""
        super().__init__(runtime, device, f"{device.key}_status")
        self._attr_name = "Discovery status"

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener(self.device.key, self.async_write_ha_state)
        )

    @property
    def native_value(self) -> str:
        """Return implementation status."""
        return "implemented" if self.device.implemented else "provisional"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return discovery details."""
        return {
            "type": self.device.device_type,
            "route_slug": self.device.route_slug,
            "bus_id": self.device.bus_id,
            "segment_id": self.device.segment_id,
            "identity_hex": self.device.identity_hex,
            "observations": self.device.observations,
            "outputs": sorted(self.device.outputs),
            "buttons": sorted(self.device.buttons),
            "families": sorted(self.device.families),
            "first_seen": self.device.first_seen,
            "last_seen": self.device.last_seen,
        }


def _messages_per_second(stats: dict[str, Any]) -> float | None:
    uptime = stats.get("uptime_seconds")
    received = stats.get("messages_received")
    if not uptime or received is None:
        return None
    return round(float(received) / float(uptime), 3)
