"""
Scheiber wireless Air Switch (Light Air Switch) device.

Air Switch buttons are battery-less, wireless push-button switches. A 2.4 GHz
interface receives the radio signal and reports each button press/release as
a compact CAN status frame (see plan/button-interaction-hypothesis.md for the
confirmed protocol). This module only observes those frames; it never sends
CAN commands, since there is no way to command a battery-less transmitter.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import can

from .base_device import ScheiberCanDevice
from .button_discovery import classify_air_switch_message
from .matchers import Matcher

logger = logging.getLogger(__name__)

# Matches the whole confirmed wireless Air Switch family
# (0x04001A80/0x04001A82/0x04001A83 and any other low byte under this
# prefix); the specific button is disambiguated by the payload, not the
# arbitration ID.
AIR_SWITCH_MATCH_PATTERN = 0x04001A00
AIR_SWITCH_MATCH_MASK = 0xFFFFFF00


class AirSwitchButton:
    """A single configured wireless Air Switch button.

    Buttons are stateless from a Home Assistant perspective (momentary
    press events, not persisted on/off state). This class only tracks the
    last-known pressed bit internally so it can detect the rising edge
    (key-down) and dedupe the redundant CAN frames the interface sends for
    every logical press.
    """

    def __init__(
        self,
        identity_hex: str,
        button_index: int,
        name: str = "",
        entity_id: Optional[str] = None,
        published: bool = True,
        device_name: str = "",
    ):
        self.identity_hex = identity_hex.upper()
        self.button_index = button_index
        self.name = name or f"Button {button_index}"
        self.entity_id = (
            entity_id or f"air_switch_{self.identity_hex.lower()}_{button_index}"
        )
        self.published = bool(published)
        self.device_name = device_name or f"AirSwitch {self.identity_hex}"
        self._pressed = False
        self._observers: List[Callable[[Dict[str, Any]], None]] = []

    @property
    def key(self) -> Tuple[str, int]:
        """Return the (identity, button_index) key used to match observations."""
        return (self.identity_hex, self.button_index)

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._observers:
            self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback in self._observers:
            self._observers.remove(callback)

    def handle_observation(self, pressed: bool) -> None:
        """Update internal press state and notify observers on a rising edge."""
        rising_edge = pressed and not self._pressed
        self._pressed = pressed
        if not rising_edge:
            return
        for observer in self._observers:
            try:
                observer({"event_type": "press"})
            except Exception as exc:
                logger.error(
                    f"Error in Air Switch button observer for {self.name}: {exc}"
                )

    def __str__(self) -> str:
        return f"AirSwitchButton({self.name}, identity={self.identity_hex}, index={self.button_index})"


class AirSwitchDevice(ScheiberCanDevice):
    """Read-only container for configured wireless Air Switch buttons.

    Unlike Bloc9/Bloc7/SourceSelector, this device is identified by the
    transmitter identity carried in the payload, not by a CAN bus route. The
    numeric `device_id` passed to the base class is derived from the identity
    only to fit the shared device container; external identity remains
    `identity_hex`.
    """

    def __init__(
        self,
        device_id: int,
        can_bus: Any,
        config: Dict[str, Any],
        segment_id: int = 0,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(
            device_id, "air_switch", can_bus, segment_id=segment_id, logger=logger
        )
        self.identity_hex = str(config.get("identity") or f"{device_id:06X}").upper()
        self.name = config.get("name") or f"AirSwitch {self.identity_hex}"
        self._buttons: Dict[Tuple[str, int], AirSwitchButton] = {}
        for button_config in _iter_button_configs(
            self.identity_hex, config.get("buttons", {})
        ):
            button = AirSwitchButton(
                identity_hex=button_config.get("identity", self.identity_hex),
                button_index=button_config["button_index"],
                name=button_config.get("name", ""),
                entity_id=button_config.get("entity_id"),
                published=button_config.get("published", True),
                device_name=self.name,
            )
            self._buttons[button.key] = button
        self._unknown_buttons: set = set()

    def get_matchers(self) -> List[Matcher]:
        """Match the whole confirmed wireless Air Switch family."""
        return [Matcher(pattern=AIR_SWITCH_MATCH_PATTERN, mask=AIR_SWITCH_MATCH_MASK)]

    @property
    def route_slug(self) -> str:
        """Use transmitter identity as the stable AirSwitch route slug."""
        return self.identity_hex

    @property
    def state_key(self) -> str:
        """Return the persistence key for this AirSwitch device."""
        return f"air_switch_{self.identity_hex}"

    def get_air_switch_buttons(self) -> List[AirSwitchButton]:
        """Return configured Air Switch button instances."""
        return list(self._buttons.values())

    def process_message(self, msg: can.Message) -> None:
        observation = classify_air_switch_message(msg)
        if observation is None:
            return

        key = (observation["identity_hex"], observation["button_index"])
        button = self._buttons.get(key)
        if button is None:
            if key not in self._unknown_buttons:
                self._unknown_buttons.add(key)
                self.logger.warning(
                    f"Unknown Air Switch button: identity={observation['identity_hex']} "
                    f"button_index={observation['button_index']} (not configured; use "
                    "the setup web UI Interactions tab to identify and add it)"
                )
            return

        button.handle_observation(observation["pressed"])

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Air Switch buttons are stateless; nothing to restore."""

    def store_to_state(self) -> Dict[str, Any]:
        """Air Switch buttons are stateless; nothing to persist."""
        return {}


def _iter_button_configs(
    identity_hex: str, buttons_config: Any
) -> List[Dict[str, Any]]:
    """Normalize legacy list and v7 index-keyed map button config shapes."""
    if isinstance(buttons_config, list):
        return buttons_config
    if not isinstance(buttons_config, dict):
        return []

    buttons = []
    for index_text, config in buttons_config.items():
        if not isinstance(config, dict):
            continue
        buttons.append(
            {
                "identity": identity_hex,
                "button_index": int(index_text),
                **config,
            }
        )
    return buttons
