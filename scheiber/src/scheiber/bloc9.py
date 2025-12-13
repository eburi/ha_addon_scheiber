"""
Bloc9 device implementation.

Manages 6 dimmable light outputs (S1-S6) using the Bloc9 CAN protocol.
"""

from typing import Any, Dict, List, Optional
import can
import logging
import time

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

        # Matcher-to-output mapping for direct dispatch
        # Will be built by get_matchers() when called
        self._matcher_to_outputs: Dict[int, List] = {}

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
                    send_command_func=self._send_switch_command,
                    logger=logging.getLogger(f"Bloc9.{device_id}.{output_name}"),
                )
                self.switches.append(switch)
                self.logger.debug(f"Created switch {name} on {output_name}")

        # Build matcher-to-outputs mapping for message dispatch
        self.get_matchers()

    def get_matchers(self) -> List[Matcher]:
        """
        Return all matchers for Bloc9 messages.

        Delegates to individual lights and switches to get their matchers,
        builds a mapping from matcher pattern to outputs for direct dispatch,
        then adds heartbeat and command echo matchers.
        """
        matchers = []
        self._matcher_to_outputs = {}  # Clear and rebuild

        # Collect matchers from all lights
        for light in self.lights:
            for matcher in light.get_matchers():
                pattern = matcher.pattern
                if pattern not in self._matcher_to_outputs:
                    self._matcher_to_outputs[pattern] = []
                    matchers.append(matcher)
                self._matcher_to_outputs[pattern].append(light)

        # Collect matchers from all switches
        for switch in self.switches:
            for matcher in switch.get_matchers():
                pattern = matcher.pattern
                if pattern not in self._matcher_to_outputs:
                    self._matcher_to_outputs[pattern] = []
                    matchers.append(matcher)
                self._matcher_to_outputs[pattern].append(switch)

        # Add heartbeat matcher (low-priority status)
        heartbeat_pattern = 0x00000600 | ((self.device_id & 0x1F) << 3)
        matchers.append(Matcher(pattern=heartbeat_pattern, mask=0xFFFFFFFF))

        # Add command matcher (identify our own commands as known, not "unknown")
        command_id = 0x02360600 | ((self.device_id << 3) | 0x80)
        matchers.append(Matcher(pattern=command_id, mask=0xFFFFFFFF))

        return matchers

    def process_message(self, msg: can.Message) -> None:
        """
        Process incoming CAN message.

        Dispatches to outputs based on matcher-to-output mapping.

        Args:
            msg: CAN message
        """
        # Check if this is heartbeat (low-priority status)
        heartbeat_pattern = 0x00000600 | ((self.device_id << 3) | 0x80)
        if msg.arbitration_id == heartbeat_pattern:
            self._process_status(msg)
            return

        # Check if this is command echo (ignore)
        command_id = 0x02360600 | ((self.device_id << 3) | 0x80)
        if msg.arbitration_id == command_id:
            return

        # Direct dispatch: look up outputs by arbitration ID
        outputs = self._matcher_to_outputs.get(msg.arbitration_id, [])
        if outputs:
            self._process_switch_change(msg, outputs)
        else:
            self.logger.debug(
                f"No outputs for arbitration_id 0x{msg.arbitration_id:08X}"
            )

    def _process_switch_change(self, msg: can.Message, outputs: List) -> None:
        """
        Process switch state change message and dispatch to matched outputs.

        Uses direct dispatch: each output processes the CAN message itself.
        """
        if len(msg.data) < 8:
            self.logger.warning(
                f"Switch change message too short: {len(msg.data)} bytes, expected 8"
            )
            return

        # Log the actual CAN message being processed
        self.logger.debug(
            f"Processing state change: ID=0x{msg.arbitration_id:08X} Data={msg.data.hex()}"
        )

        # Direct dispatch: each output knows how to process the message
        for output in outputs:
            output.process_matching_message(msg)

    def _process_status(self, msg: can.Message) -> None:
        """
        Process low-priority status message (heartbeat).

        This message is periodic and doesn't contain state changes.
        Use it to publish device info to MQTT.
        """
        # Build output info dict - include all 6 outputs
        outputs = {}

        # Initialize all as unknown
        for i in range(1, 7):
            outputs[f"s{i}"] = "unknown"

        # Fill in configured lights
        for light in self.lights:
            output_name = f"s{light.switch_nr + 1}"
            outputs[output_name] = light.name

        # Fill in configured switches
        for switch in self.switches:
            output_name = f"s{switch.switch_nr + 1}"
            outputs[output_name] = switch.name

        # Notify observers with device info
        device_info = {
            "device_type": "bloc9",
            "bus_id": self.device_id,
            "outputs": outputs,
        }
        self._notify_observers({"device_info": device_info})

    def _send_switch_command(
        self, switch_nr: int, state: bool, brightness: Optional[int] = None
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

        # Determine brightness
        brightness = brightness if brightness is not None else (255 if state else 0)

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

    def get_switches(self) -> List[Switch]:
        """Return list of all switches."""
        return self.switches

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
