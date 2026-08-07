"""Switch entities for Scheiber CAN."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .coordinator import DiscoveredDevice, ScheiberRuntime
from .const import DOMAIN
from .core.switch import Switch as HardwareSwitch
from .entity import ScheiberDiscoveredEntity, ScheiberEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scheiber switches."""
    runtime = entry.runtime_data
    entities: list[SwitchEntity] = []
    known: set[str] = set()
    if runtime.discovery_only:
        entities.extend(_discovery_switches(runtime, known))

        def _async_add_discovered_device(device: DiscoveredDevice) -> None:
            new_entities = _device_discovery_switches(runtime, device, known)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            runtime.async_add_discovery_listener(_async_add_discovered_device)
        )
    else:
        for device in runtime.get_configured_bloc9_devices():
            for hardware_switch in device.get_switches():
                entities.append(ScheiberConfiguredSwitch(runtime, device, hardware_switch))
    async_add_entities(entities)


def _discovery_switches(
    runtime: ScheiberRuntime, known: set[str]
) -> list[SwitchEntity]:
    entities: list[SwitchEntity] = []
    for device in runtime.discovered_devices.values():
        entities.extend(_device_discovery_switches(runtime, device, known))
    return entities


def _device_discovery_switches(
    runtime: ScheiberRuntime, device: DiscoveredDevice, known: set[str]
) -> list[SwitchEntity]:
    if device.device_type != "bloc9":
        return []

    entities: list[SwitchEntity] = []
    for output_name in [f"s{i}" for i in range(1, 7)]:
        unique_key = f"{device.key}_{output_name}"
        if unique_key in known:
            continue
        known.add(unique_key)
        entities.append(ScheiberBloc9DiscoverySwitch(runtime, device, output_name))
    return entities


class ScheiberBloc9DiscoverySwitch(ScheiberDiscoveredEntity, SwitchEntity):
    """Discovered Bloc9 output exposed safely as a switch by default."""

    _attr_device_class = SwitchDeviceClass.SWITCH


    def __init__(
        self, runtime: ScheiberRuntime, device: DiscoveredDevice, output_name: str
    ) -> None:
        """Initialize discovered output switch."""
        super().__init__(runtime, device, f"{device.key}_{output_name}")
        self.output_name = output_name
        self._attr_name = output_name.upper()

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener(self.device.key, self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool | None:
        """Return observed state."""
        output = self.device.outputs.get(self.output_name)
        if output is None:
            return None
        return output.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return output diagnostics."""
        output = self.device.outputs.get(self.output_name)
        return {
            "output": self.output_name,
            "brightness": output.brightness if output else None,
            "raw_brightness": output.raw_brightness if output else None,
            "last_seen": output.last_seen if output else None,
            "read_only": self.runtime.read_only,
            "convert_to_light": "Use Home Assistant's Change device type / Switch as X helper for a UI-only conversion, or configure this output as a light for native dimming commands.",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on discovered output if writes are explicitly enabled."""
        if self.runtime.read_only:
            return
        output = self.device.outputs.get(self.output_name)
        switch_nr = output.switch_nr if output else int(self.output_name[1:]) - 1
        await self.runtime.async_set_bloc9_output(self.device, switch_nr, True, 255)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off discovered output if writes are explicitly enabled."""
        if self.runtime.read_only:
            return
        output = self.device.outputs.get(self.output_name)
        switch_nr = output.switch_nr if output else int(self.output_name[1:]) - 1
        await self.runtime.async_set_bloc9_output(self.device, switch_nr, False, 0)


class ScheiberConfiguredSwitch(ScheiberEntity, SwitchEntity):
    """Configured Bloc9 switch entity backed by the core Switch object."""

    _attr_device_class = SwitchDeviceClass.SWITCH


    def __init__(self, runtime, device, hardware_switch: HardwareSwitch) -> None:
        """Initialize configured switch."""
        output_name = f"s{hardware_switch.switch_nr + 1}"
        route_slug = device.route_slug
        super().__init__(runtime, f"bloc9_{route_slug}_{output_name}")
        self.device = device
        self.hardware_switch = hardware_switch
        self._attr_name = hardware_switch.name or output_name.upper()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"bloc9_{route_slug}")},
            "manufacturer": "Scheiber",
            "name": f"Scheiber Bloc9 {route_slug}",
            "model": "Bloc9",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to hardware changes."""
        self.hardware_switch.subscribe(self._handle_hardware_update)
        self.async_on_remove(
            lambda: self.hardware_switch.unsubscribe(self._handle_hardware_update)
        )

    def _handle_hardware_update(self, _state: dict[str, Any]) -> None:
        self.schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        """Return switch state."""
        return bool(self.hardware_switch.get_state())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        if not self.runtime.read_only:
            await self.hass.async_add_executor_job(self.hardware_switch.set, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        if not self.runtime.read_only:
            await self.hass.async_add_executor_job(self.hardware_switch.set, False)
