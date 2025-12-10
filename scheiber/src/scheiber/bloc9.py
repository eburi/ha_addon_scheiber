"""
Bloc9 device implementation.

Manages 6 dimmable light outputs (S1-S6) using the Bloc9 CAN protocol.
"""

from typing import Any, Dict, List, Optional
import can
import logging

from .base_device import ScheiberCanDevice
from .light import DimmableLight
from .switch import Switch
from .matchers import Matcher


class Bloc9Device(ScheiberCanDevice):
    """
    Bloc9 device with 6 dimmable light outputs (S1-S6).

    CAN Protocol:
    - Command ID: 0x02360600 | ((device_id << 3) | 0x80)
    - Data format: [switch_nr, mode_byte, 0x00, brightness_byte]
    - Mode byte: 0x00=OFF, 0x01=ON, 0x11=PWM dimming
    - Switch numbers: 0-5 (for S1-S6)

    Dimming threshold:
    - Brightness 0-2: OFF (no PWM)
    - Brightness 3-252: PWM dimming
    - Brightness 253-255: Full ON (no PWM)
    """

    # Hardcoded matchers (from device_types.yaml)
    STATUS_MATCHERS = [
        # Low-priority status messages
        {"pattern": 0x00000600, "mask": 0xFFFFFF00, "property": "low_priority_status"},
        # Switch change messages (pairs)
        {"pattern": 0x02160600, "mask": 0xFFFFFF00, "property": "s1_s2_change"},
        {"pattern": 0x02180600, "mask": 0xFFFFFF00, "property": "s3_s4_change"},
        {"pattern": 0x021A0600, "mask": 0xFFFFFF00, "property": "s5_s6_change"},
    ]

    # Dimming threshold (prevent LED flickering at extremes)
    DIMMING_THRESHOLD = 2

    def __init__(
        self,
        device_id: int,
        can_bus,
        lights_config: Optional[Dict[str, Dict[str, Any]]] = None,
        switches_config: Optional[Dict[str, Dict[str, Any]]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize Bloc9 device.

        Args:
            device_id: Device bus ID
            can_bus: ScheiberCanBus instance
            lights_config: Dict mapping output names (s1-s6) to light config
            switches_config: Dict mapping output names (s1-s6) to switch config
            logger: Optional logger
        """
        super().__init__(device_id, "bloc9", can_bus, logger)

        # Track all outputs (mix of switches and lights)
        self.switches: List[Switch] = []
        self.lights: List[DimmableLight] = []

        # Map output names to switch numbers
        output_map = {f"s{i+1}": i for i in range(6)}

        # Create lights for configured outputs
        if lights_config:
            for output_name, config in lights_config.items():
                switch_nr = output_map.get(output_name.lower())
                if switch_nr is None:
                    self.logger.warning(f"Invalid output name: {output_name}")
                    continue

                name = config.get("name", output_name)
                entity_id = config.get("entity_id", name.lower().replace(" ", "_"))
                initial_brightness = config.get("initial_brightness")  # None if not set

                light = DimmableLight(
                    device_id=device_id,
                    switch_nr=switch_nr,
                    name=name,
                    entity_id=entity_id,
                    send_command_func=self._send_switch_command,
                    logger=logging.getLogger(f"Bloc9.{device_id}.{output_name}"),
                )
                # Only set initial brightness if explicitly configured (DANGEROUS)
                # Otherwise brightness/state will be restored from saved state or remain at 0
                if initial_brightness is not None:
                    self.logger.warning(
                        f"Setting initial_brightness={initial_brightness} for {name} "
                        f"(this will send CAN command on startup)"
                    )
                    light._brightness = initial_brightness
                    light._state = initial_brightness > 0

                self.lights.append(light)
                self.logger.debug(
                    f"Created light {name} on {output_name} (brightness={initial_brightness})"
                )

        # Create switches for configured outputs
        if switches_config:
            for output_name, config in switches_config.items():
                switch_nr = output_map.get(output_name.lower())
                if switch_nr is None:
                    self.logger.warning(f"Invalid output name: {output_name}")
                    continue

                name = config.get("name", output_name)
                entity_id = config.get("entity_id", name.lower().replace(" ", "_"))

                switch = Switch(
                    device_id=device_id,
                    switch_nr=switch_nr,
                    name=name,
                    entity_id=entity_id,
                    can_bus=can_bus,
                    logger=logging.getLogger(f"Bloc9.{device_id}.{output_name}"),
                )
                self.switches.append(switch)
                self.logger.debug(f"Created switch {name} on {output_name}")

    def get_matchers(self) -> List[Matcher]:
        """
        Return all matchers for Bloc9 messages.

        Includes status matchers and command matcher for this device.
        """
        matchers = []

        # Add status matchers
        for m in self.STATUS_MATCHERS:
            # Match messages for this device ID
            # Low byte contains device_id, extract using mask
            pattern = m["pattern"] | ((self.device_id & 0x1F) << 3)
            matcher = Matcher(
                pattern=pattern, mask=m["mask"], property=m.get("property")
            )
            matchers.append(matcher)

        # Add command matcher (identify our own commands as known, not "unknown")
        command_id = 0x02360600 | ((self.device_id << 3) | 0x80)
        matchers.append(
            Matcher(pattern=command_id, mask=0xFFFFFFFF, property="command_echo")
        )

        return matchers

    def process_message(
        self, msg: can.Message, matched_property: Optional[str]
    ) -> None:
        """
        Process incoming CAN message.

        Args:
            msg: CAN message
            matched_property: Property name from matcher
        """
        if not matched_property:
            return

        # Handle different message types
        if matched_property in ("s1_s2_change", "s3_s4_change", "s5_s6_change"):
            self._process_switch_change(msg, matched_property)
        elif matched_property == "low_priority_status":
            self._process_status(msg)
        elif matched_property == "command_echo":
            # Our own command echo, ignore
            pass

    def _process_switch_change(self, msg: can.Message, property_name: str) -> None:
        """
        Process switch state change message.

        Format: Data[0-1] = S1/S3/S5 state/brightness
                Data[2-3] = S2/S4/S6 state/brightness
        """
        if len(msg.data) < 4:
            return

        # Determine which switch pair
        switch_offset = 0
        if property_name == "s1_s2_change":
            switch_offset = 0  # S1, S2
        elif property_name == "s3_s4_change":
            switch_offset = 2  # S3, S4
        elif property_name == "s5_s6_change":
            switch_offset = 4  # S5, S6

        # Parse first switch (odd-numbered: S1, S3, S5)
        state1_byte = msg.data[0]
        brightness1 = msg.data[1]
        state1 = state1_byte == 0x01 or brightness1 > self.DIMMING_THRESHOLD

        # Parse second switch (even-numbered: S2, S4, S6)
        state2_byte = msg.data[2]
        brightness2 = msg.data[3]
        state2 = state2_byte == 0x01 or brightness2 > self.DIMMING_THRESHOLD

        # Update lights
        self.lights[switch_offset].update_state(state1, brightness1)
        self.lights[switch_offset + 1].update_state(state2, brightness2)

    def _process_status(self, msg: can.Message) -> None:
        """
        Process low-priority status message.

        These contain overall device status.
        """
        # For now, just log
        self.logger.debug(f"Status message: {msg.data.hex()}")

    def _send_switch_command(
        self, switch_nr: int, state: bool, brightness: int
    ) -> None:
        """
        Send switch command via CAN bus.

        Args:
            switch_nr: Switch number (0-5)
            state: Desired state
            brightness: Desired brightness (0-255)
        """
        # Construct CAN ID
        low_byte = ((self.device_id << 3) | 0x80) & 0xFF
        can_id = 0x02360600 | low_byte

        # Apply dimming threshold logic
        if brightness <= self.DIMMING_THRESHOLD:
            # Low brightness = OFF (no PWM)
            data = bytes([switch_nr, 0x00, 0x00, 0x00])
            self.logger.debug(f"S{switch_nr+1} -> OFF (brightness={brightness})")
        elif brightness >= (255 - self.DIMMING_THRESHOLD):
            # High brightness = full ON (no PWM)
            data = bytes([switch_nr, 0x01, 0x00, 0x00])
            self.logger.debug(f"S{switch_nr+1} -> ON (brightness={brightness})")
        else:
            # Middle range = PWM dimming
            brightness_byte = max(1, min(254, brightness))
            data = bytes([switch_nr, 0x11, 0x00, brightness_byte])
            self.logger.debug(f"S{switch_nr+1} -> PWM brightness={brightness_byte}")

        # Send via CAN bus
        try:
            self.can_bus.send_message(can_id, data)
        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")

    def get_lights(self) -> List[DimmableLight]:
        """Return list of all lights (S1-S6)."""
        return self.lights

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """
        Restore device state from persisted data.

        Args:
            state: Dictionary with light states
        """
        for i, light in enumerate(self.lights):
            light_key = f"s{i+1}"
            if light_key in state:
                light_state = state[light_key]
                brightness = light_state.get("brightness", 0)
                # Restore without sending command (will sync on first CAN message)
                light._brightness = brightness
                light._state = brightness > 0
                self.logger.debug(f"Restored {light_key}: brightness={brightness}")

    def store_to_state(self) -> Dict[str, Any]:
        """
        Return current state for persistence.

        Returns:
            Dictionary with light states
        """
        state = {}
        for i, light in enumerate(self.lights):
            light_key = f"s{i+1}"
            state[light_key] = {
                "brightness": light._brightness,
                "state": light._state,
            }
        return state
