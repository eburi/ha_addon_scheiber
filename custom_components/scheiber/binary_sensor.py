"""Binary sensors for Scheiber CAN."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .entity import ScheiberNetworkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scheiber binary sensors."""
    async_add_entities(
        [
            ScheiberCanConnectedBinarySensor(entry.runtime_data),
            ScheiberStaleOutputsBinarySensor(entry.runtime_data),
        ]
    )


class ScheiberCanConnectedBinarySensor(ScheiberNetworkEntity, BinarySensorEntity):
    """CAN interface connection state."""

    _attr_name = "CAN connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, runtime) -> None:
        """Initialize sensor."""
        super().__init__(runtime, "can_connected")

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener("network", self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """Return whether CAN is connected."""
        return self.runtime.connected

    @property
    def available(self) -> bool:
        """Connection sensor is available even when CAN is down."""
        return True


class ScheiberStaleOutputsBinarySensor(ScheiberNetworkEntity, BinarySensorEntity):
    """System-wide indicator for Bloc9 outputs stuck in a hold-to-dim cycle.

    A stuck Bloc9 keeps broadcasting a brightness setpoint while the output is
    de-energised, so the lamp stays dark while the system misbehaves. This
    aggregates that condition across every device on the bus.
    """

    _attr_name = "Stale outputs"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime) -> None:
        """Initialize sensor."""
        super().__init__(runtime, "stale_outputs")

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener("stale", self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """Return whether any output is currently stale."""
        return self.runtime.stale_outputs
