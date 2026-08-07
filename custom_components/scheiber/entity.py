"""Base entities for the Scheiber CAN integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN
from .coordinator import DiscoveredDevice, ScheiberRuntime


class ScheiberEntity(Entity):
    """Base Scheiber entity."""

    _attr_has_entity_name = True


    def __init__(self, runtime: ScheiberRuntime, unique_suffix: str) -> None:
        """Initialize entity."""
        self.runtime = runtime
        self._attr_unique_id = f"scheiber_{runtime.can_interface}_{unique_suffix}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.runtime.connected


class ScheiberNetworkEntity(ScheiberEntity):
    """Entity attached to the CAN network device."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return network device info."""
        return self.runtime.build_network_device_info()


class ScheiberDiscoveredEntity(ScheiberEntity):
    """Entity attached to a discovered device."""

    def __init__(
        self, runtime: ScheiberRuntime, device: DiscoveredDevice, unique_suffix: str
    ) -> None:
        """Initialize discovered entity."""
        super().__init__(runtime, unique_suffix)
        self.device = device
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return discovered device info."""
        return self.runtime.build_device_info(self.device)


def slugify(value: str) -> str:
    """Return a HA-safe slug fragment."""
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def device_identifier(device: DiscoveredDevice) -> tuple[str, str]:
    """Return device registry identifier."""
    return (DOMAIN, device.key)
