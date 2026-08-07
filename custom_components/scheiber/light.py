"""Light entities for configured Scheiber outputs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ScheiberConfigEntry
from .const import DOMAIN, LIGHT_EFFECTS
from .coordinator import DiscoveredDevice, ScheiberRuntime
from .core.light import DimmableLight
from .entity import ScheiberDiscoveredEntity, ScheiberEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScheiberConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up configured Scheiber lights."""
    runtime = entry.runtime_data
    if runtime.discovery_only:
        known: set[str] = set()
        entities: list[LightEntity] = []
        for device in runtime.discovered_devices.values():
            entities.extend(_discovery_lights(runtime, device, known))

        def _async_add_discovered_device(device: DiscoveredDevice) -> None:
            new_entities = _discovery_lights(runtime, device, known)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            runtime.async_add_discovery_listener(_async_add_discovered_device)
        )
        async_add_entities(entities)
        return

    entities: list[LightEntity] = []
    for device in runtime.get_configured_bloc9_devices():
        for hardware_light in device.get_lights():
            entities.append(ScheiberConfiguredLight(runtime, device, hardware_light))
    async_add_entities(entities)


def _discovery_lights(
    runtime: ScheiberRuntime, device: DiscoveredDevice, known: set[str]
) -> list[LightEntity]:
    if device.device_type != "bloc9":
        return []

    entities: list[LightEntity] = []
    for output_name in [f"s{i}" for i in range(1, 7)]:
        unique_key = f"{device.key}_{output_name}_light"
        if unique_key in known:
            continue
        known.add(unique_key)
        entities.append(ScheiberBloc9DiscoveryLight(runtime, device, output_name))
    return entities


class ScheiberBloc9DiscoveryLight(ScheiberDiscoveredEntity, LightEntity):
    """Disabled-by-default full light control for discovered Bloc9 outputs."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_effect_list = LIGHT_EFFECTS
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, runtime: ScheiberRuntime, device: DiscoveredDevice, output_name: str
    ) -> None:
        """Initialize discovered light."""
        super().__init__(runtime, device, f"{device.key}_{output_name}_light")
        self.output_name = output_name
        self.switch_nr = int(output_name[1:]) - 1
        self._attr_name = f"{output_name.upper()} light"

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.runtime.async_add_listener(self.device.key, self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool | None:
        """Return observed light state."""
        output = self.device.outputs.get(self.output_name)
        if output is None:
            return None
        return output.state

    @property
    def brightness(self) -> int | None:
        """Return observed brightness."""
        output = self.device.outputs.get(self.output_name)
        if output is None:
            return None
        return output.brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on discovered light if writes are enabled."""
        if self.runtime.read_only:
            return
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            output = self.device.outputs.get(self.output_name)
            brightness = output.brightness if output and output.brightness > 0 else 255
        await self.runtime.async_set_bloc9_output(
            self.device, self.switch_nr, True, brightness
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off discovered light if writes are enabled."""
        if self.runtime.read_only:
            return
        await self.runtime.async_set_bloc9_output(self.device, self.switch_nr, False, 0)


class ScheiberConfiguredLight(ScheiberEntity, LightEntity):
    """Configured Bloc9 dimmable light."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_effect_list = LIGHT_EFFECTS

    def __init__(self, runtime, device, hardware_light: DimmableLight) -> None:
        """Initialize configured light."""
        output_name = f"s{hardware_light.switch_nr + 1}"
        route_slug = device.route_slug
        super().__init__(runtime, f"bloc9_{route_slug}_{output_name}_light")
        self.device = device
        self.hardware_light = hardware_light
        self._attr_name = hardware_light.name or output_name.upper()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"bloc9_{route_slug}")},
            "manufacturer": "Scheiber",
            "name": f"Scheiber Bloc9 {route_slug}",
            "model": "Bloc9",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to hardware changes."""
        self.hardware_light.subscribe(self._handle_hardware_update)
        self.async_on_remove(
            lambda: self.hardware_light.unsubscribe(self._handle_hardware_update)
        )

    def _handle_hardware_update(self, _state: dict[str, Any]) -> None:
        self.schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        """Return light state."""
        return self.hardware_light.is_on()

    @property
    def brightness(self) -> int:
        """Return brightness."""
        return self.hardware_light.get_brightness()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn light on."""
        if self.runtime.read_only:
            return
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        effect = kwargs.get(ATTR_EFFECT)
        await self.hass.async_add_executor_job(
            self.hardware_light.set,
            True,
            brightness,
            0.0,
            None,
            1.0,
            None,
            effect,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn light off."""
        if self.runtime.read_only:
            return
        await self.hass.async_add_executor_job(self.hardware_light.set, False)
