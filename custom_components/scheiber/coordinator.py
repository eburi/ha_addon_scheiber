"""Runtime coordinator for the Scheiber CAN integration."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

import can

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later

from .core import create_scheiber_system
from .core.bloc9 import Bloc9Device
from .core.button_discovery import classify_air_switch_message, classify_button_source_message
from .core.discovery import build_bloc9_address_byte, classify_bloc9_message
from .core.protocol import classify_message_family

from .const import (
    CONF_CAN_INTERFACE,
    CONF_CONFIG_PATH,
    CONF_DISCOVERY_ONLY,
    CONF_MAX_MESSAGE_IDS,
    CONF_READ_ONLY,
    CONF_STATE_FILE,
    DEFAULT_DISCOVERY_ONLY,
    DEFAULT_MAX_MESSAGE_IDS,
    DEFAULT_READ_ONLY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_NAME_BY_TYPE = {
    "bloc9": "Bloc9",
    "bloc7": "Bloc7",
    "air_switch": "AirSwitch",
    "source_selector": "Source Selector",
    "unknown": "Unknown Scheiber Device",
}


@dataclass
class DiscoveredOutput:
    """Discovered Bloc9 output state."""

    output: str
    switch_nr: int
    state: bool = False
    brightness: int = 0
    raw_brightness: int = 0
    last_seen: float = 0.0


@dataclass
class DiscoveredDevice:
    """Discovered CAN device."""

    device_type: str
    route_slug: str
    bus_id: int | None = None
    segment_id: int = 0
    identity_hex: str | None = None
    name: str = ""
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    observations: int = 0
    implemented: bool = True
    outputs: dict[str, DiscoveredOutput] = field(default_factory=dict)
    buttons: dict[int, dict[str, Any]] = field(default_factory=dict)
    families: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        """Return stable discovery key."""
        if self.identity_hex:
            return f"{self.device_type}_{self.identity_hex.lower()}"
        return f"{self.device_type}_{self.route_slug}"

    @property
    def display_name(self) -> str:
        """Return default device name."""
        if self.name:
            return self.name
        model = DEVICE_NAME_BY_TYPE.get(self.device_type, self.device_type.title())
        if self.identity_hex:
            return f"Scheiber {model} {self.identity_hex}"
        return f"Scheiber {model} {self.route_slug}"


@dataclass
class MessageSummary:
    """Summary for a raw CAN arbitration ID."""

    arbitration_id: int
    count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    dlc: int = 0
    data_hex: str = ""
    family: str = "unknown"

    @property
    def key(self) -> str:
        """Return message key."""
        return f"0x{self.arbitration_id:08X}"


class ScheiberRuntime:
    """Own the Scheiber core runtime and expose HA-safe observations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the runtime."""
        self.hass = hass
        self.entry = entry
        self.system: Any | None = None
        self.connected = False
        self.last_error: str | None = None
        self.stats: dict[str, Any] = {}
        self.discovered_devices: dict[str, DiscoveredDevice] = {}
        self.message_summaries: OrderedDict[int, MessageSummary] = OrderedDict()
        self._listeners: dict[str, list[Callable[[], None]]] = {}
        self._discovery_callbacks: list[Callable[[DiscoveredDevice], None]] = []
        self._pending_notify_keys: set[str] = set()
        self._notify_unsub: CALLBACK_TYPE | None = None
        self._max_message_ids = int(
            self.options.get(CONF_MAX_MESSAGE_IDS, DEFAULT_MAX_MESSAGE_IDS)
        )

    @property
    def options(self) -> dict[str, Any]:
        """Return merged config entry data and options."""
        return {**self.entry.data, **self.entry.options}

    @property
    def can_interface(self) -> str:
        """Return configured CAN interface."""
        return str(self.options[CONF_CAN_INTERFACE])

    @property
    def read_only(self) -> bool:
        """Return whether commands are disabled."""
        return bool(self.options.get(CONF_READ_ONLY, DEFAULT_READ_ONLY))

    @property
    def discovery_only(self) -> bool:
        """Return whether configured devices should be ignored."""
        return bool(self.options.get(CONF_DISCOVERY_ONLY, DEFAULT_DISCOVERY_ONLY))

    async def async_start(self) -> None:
        """Start the CAN runtime in an executor."""
        try:
            await self.hass.async_add_executor_job(self._start)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            raise ConfigEntryNotReady(f"Failed to open CAN interface: {exc}") from exc

    def _start(self) -> None:
        """Start the Scheiber system in the executor."""
        config_path = None if self.discovery_only else self.options.get(CONF_CONFIG_PATH)
        state_file = self.options.get(CONF_STATE_FILE)
        self.system = create_scheiber_system(
            can_interface=self.can_interface,
            config_path=config_path,
            state_file=state_file,
            read_only=self.read_only,
        )
        self.system.subscribe_to_stats(self._handle_stats_threadsafe)
        if self.discovery_only:
            self.system.can_bus.start_listening(self._handle_message_threadsafe)
        else:
            self.system.start()
            self.system.subscribe_to_messages(self._handle_message_threadsafe)
        self.connected = True
        self.last_error = None

    async def async_stop(self) -> None:
        """Stop the CAN runtime in an executor."""
        await self.hass.async_add_executor_job(self._stop)

    def _stop(self) -> None:
        """Stop the Scheiber system."""
        if self.system is not None:
            self.system.stop()
            self.system = None
        self.connected = False

    @callback
    def async_add_listener(self, key: str, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a listener for runtime updates."""
        self._listeners.setdefault(key, []).append(update_callback)

        @callback
        def remove_listener() -> None:
            self._listeners[key].remove(update_callback)

        return remove_listener

    @callback
    def async_add_discovery_listener(
        self, update_callback: Callable[[DiscoveredDevice], None]
    ) -> CALLBACK_TYPE:
        """Register a listener for newly discovered devices."""
        self._discovery_callbacks.append(update_callback)

        @callback
        def remove_listener() -> None:
            self._discovery_callbacks.remove(update_callback)

        return remove_listener

    @callback
    def _notify(self, *keys: str) -> None:
        """Notify registered HA entity listeners."""
        for key in ("all", *keys):
            for listener in self._listeners.get(key, []):
                listener()

    @callback
    def _schedule_notify(self, *keys: str) -> None:
        """Batch high-frequency CAN updates before writing HA state."""
        self._pending_notify_keys.update(keys)
        if self._notify_unsub is not None:
            return
        self._notify_unsub = async_call_later(self.hass, 0.25, self._flush_notify)

    @callback
    def _flush_notify(self, _now: Any) -> None:
        """Flush batched entity updates."""
        self._notify_unsub = None
        keys = tuple(self._pending_notify_keys)
        self._pending_notify_keys.clear()
        self._notify(*keys)

    def _handle_stats_threadsafe(self, stats: dict[str, Any]) -> None:
        """Move stats update from CAN thread into HA event loop."""
        self.hass.loop.call_soon_threadsafe(self._async_handle_stats, stats)

    @callback
    def _async_handle_stats(self, stats: dict[str, Any]) -> None:
        self.stats = stats
        self.connected = True
        self._notify("network")

    def _handle_message_threadsafe(self, msg: can.Message) -> None:
        """Move raw message observation from CAN thread into HA event loop."""
        self.hass.loop.call_soon_threadsafe(self._async_handle_message, msg)

    @callback
    def _async_handle_message(self, msg: can.Message) -> None:
        """Record message observations and discovery hints."""
        now = time.time()
        self._observe_message(msg, now)
        changed_keys, new_devices = self._observe_device(msg, now)
        for device in new_devices:
            for listener in self._discovery_callbacks:
                listener(device)
        self._schedule_notify("network", "messages", *changed_keys)

    @callback
    def _observe_message(self, msg: can.Message, now: float) -> None:
        summary = self.message_summaries.get(msg.arbitration_id)
        if summary is None:
            summary = MessageSummary(arbitration_id=msg.arbitration_id)
            self.message_summaries[msg.arbitration_id] = summary
            while len(self.message_summaries) > self._max_message_ids:
                self.message_summaries.popitem(last=False)

        family = classify_message_family(msg.arbitration_id)
        air_switch = classify_air_switch_message(msg)
        button_source = classify_button_source_message(msg)
        summary.count += 1
        summary.last_seen = now
        summary.dlc = len(msg.data)
        summary.data_hex = bytes(msg.data).hex().upper()
        if air_switch is not None:
            summary.family = "air_switch"
        elif family is not None:
            summary.family = f"{family['device_type']}.{family['family']}"
        elif button_source is not None:
            summary.family = "button_source_candidate"

    @callback
    def _observe_device(
        self, msg: can.Message, now: float
    ) -> tuple[set[str], list[DiscoveredDevice]]:
        changed_keys: set[str] = set()
        new_devices: list[DiscoveredDevice] = []
        bloc9 = classify_bloc9_message(msg)
        if bloc9 is not None:
            device, is_new = self._get_or_create_device(
                "bloc9",
                bloc9["route_slug"],
                now,
                bus_id=bloc9["bus_id"],
                segment_id=bloc9["segment_id"],
            )
            if is_new:
                new_devices.append(device)
            device.families.add(bloc9["kind"])
            if bloc9["kind"] == "state_update":
                for output, sample in bloc9["outputs"].items():
                    switch_nr = int(output[1:]) - 1
                    device.outputs[output] = DiscoveredOutput(
                        output=output,
                        switch_nr=switch_nr,
                        state=bool(sample["state"]),
                        brightness=int(sample["effective_brightness"]),
                        raw_brightness=int(sample["raw_brightness"]),
                        last_seen=now,
                    )
            changed_keys.add(device.key)

        family = classify_message_family(msg.arbitration_id)
        if family is not None and family["device_type"] in {"bloc7", "source_selector"}:
            device, is_new = self._get_or_create_device(
                family["device_type"],
                family["route_slug"],
                now,
                bus_id=family["bus_id"],
                segment_id=family["segment_id"],
                implemented=family["device_type"] == "bloc7",
            )
            if is_new:
                new_devices.append(device)
            device.families.add(family["family"])
            changed_keys.add(device.key)

        air_switch = classify_air_switch_message(msg)
        if air_switch is not None:
            identity = air_switch["identity_hex"]
            device, is_new = self._get_or_create_device(
                "air_switch",
                identity,
                now,
                identity_hex=identity,
            )
            if is_new:
                new_devices.append(device)
            device.buttons[int(air_switch["button_index"])] = {
                "pressed": bool(air_switch["pressed"]),
                "last_seen": now,
            }
            changed_keys.add(device.key)

        if not changed_keys:
            family = classify_message_family(msg.arbitration_id)
            if family is None:
                unknown_key = f"unknown_0x{msg.arbitration_id:08X}"
                device = self.discovered_devices.get(unknown_key)
                if device is None:
                    device = DiscoveredDevice(
                        device_type="unknown",
                        route_slug=f"0x{msg.arbitration_id:08X}",
                        name=f"Scheiber Unknown 0x{msg.arbitration_id:08X}",
                        implemented=False,
                    )
                    self.discovered_devices[unknown_key] = device
                    new_devices.append(device)
                device.observations += 1
                device.last_seen = now
                changed_keys.add(device.key)

        return changed_keys, new_devices

    @callback
    def _get_or_create_device(
        self,
        device_type: str,
        route_slug: str,
        now: float,
        *,
        bus_id: int | None = None,
        segment_id: int = 0,
        identity_hex: str | None = None,
        implemented: bool = True,
    ) -> tuple[DiscoveredDevice, bool]:
        key = f"{device_type}_{identity_hex.lower() if identity_hex else route_slug}"
        device = self.discovered_devices.get(key)
        is_new = device is None
        if device is None:
            device = DiscoveredDevice(
                device_type=device_type,
                route_slug=route_slug,
                bus_id=bus_id,
                segment_id=segment_id,
                identity_hex=identity_hex,
                implemented=implemented,
            )
            self.discovered_devices[key] = device
        device.observations += 1
        device.last_seen = now
        return device, is_new

    def get_configured_bloc9_devices(self) -> list[Bloc9Device]:
        """Return configured Bloc9 devices from a non-discovery runtime."""
        if self.system is None:
            return []
        return [
            device
            for device in self.system.get_all_devices()
            if isinstance(device, Bloc9Device)
        ]

    async def async_set_bloc9_output(
        self,
        device: DiscoveredDevice,
        switch_nr: int,
        state: bool,
        brightness: int | None = None,
    ) -> None:
        """Set a discovered Bloc9 output through the shared CAN runtime."""
        await self.hass.async_add_executor_job(
            self._set_bloc9_output, device, switch_nr, state, brightness
        )

    def _set_bloc9_output(
        self,
        device: DiscoveredDevice,
        switch_nr: int,
        state: bool,
        brightness: int | None = None,
    ) -> None:
        """Send a Bloc9 output command if command sending is enabled."""
        if self.read_only or self.system is None or device.bus_id is None:
            return

        can_id = 0x02360600 | build_bloc9_address_byte(device.bus_id, device.segment_id)
        target_brightness = brightness if brightness is not None else (255 if state else 0)
        target_brightness = max(0, min(255, int(target_brightness)))

        if target_brightness <= Bloc9Device.DIMMING_THRESHOLD:
            data = bytes([switch_nr, 0x00, 0x00, 0x00])
        elif target_brightness >= (255 - Bloc9Device.DIMMING_THRESHOLD):
            data = bytes([switch_nr, 0x01, 0x00, 0x00])
        else:
            data = bytes([switch_nr, 0x11, 0x00, target_brightness])

        self.system.can_bus.send_message(can_id, data)

    def build_device_info(self, device: DiscoveredDevice) -> dict[str, Any]:
        """Return HA device registry metadata."""
        identifiers = {(DOMAIN, device.key)}
        return {
            "identifiers": identifiers,
            "manufacturer": "Scheiber",
            "name": device.display_name,
            "model": DEVICE_NAME_BY_TYPE.get(device.device_type, device.device_type),
            "configuration_url": "homeassistant://config/devices/dashboard",
        }

    def build_network_device_info(self) -> dict[str, Any]:
        """Return HA device metadata for the CAN network."""
        return {
            "identifiers": {(DOMAIN, f"network_{self.can_interface}")},
            "manufacturer": "Scheiber",
            "name": f"Scheiber CAN Network {self.can_interface}",
            "model": "CAN Network",
        }
