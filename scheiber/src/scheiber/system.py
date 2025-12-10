"""
High-level device manager for Scheiber CAN system.

Manages device instances, routes CAN messages, coordinates state persistence.
"""

import logging
import threading
import time
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import can

from .can_bus import ScheiberCanBus
from .base_device import ScheiberCanDevice


class ScheiberSystem:
    """
    High-level device manager.

    Responsibilities:
    - Manage device instances
    - Route incoming CAN messages to devices
    - Coordinate state persistence
    - Provide device access API
    - Track unknown messages
    """

    def __init__(
        self,
        can_bus: ScheiberCanBus,
        devices: List[ScheiberCanDevice],
        state_file: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize Scheiber system.

        Args:
            can_bus: ScheiberCanBus instance
            devices: List of device instances
            state_file: Optional path to state persistence file
            logger: Optional logger
        """
        self.can_bus = can_bus
        self.devices = devices
        self.state_file = state_file
        self.logger = logger or logging.getLogger(__name__)

        # Build device lookup: (device_type, device_id) -> device
        self._device_map: Dict[Tuple[str, int], ScheiberCanDevice] = {}
        for device in devices:
            key = (device.device_type, device.device_id)
            if key in self._device_map:
                raise ValueError(
                    f"Duplicate device: {device.device_type} bus_id={device.device_id}"
                )
            self._device_map[key] = device

        # Build matcher lookup: list of (device, matcher, property_name)
        self._matchers = []
        for device in devices:
            for matcher in device.get_matchers():
                self._matchers.append((device, matcher))

        # Track unknown arbitration IDs (log once)
        self._unknown_ids = set()

        # State persistence
        self._state_dirty = False
        self._state_lock = threading.Lock()
        self._state_timer: Optional[threading.Timer] = None
        self._state_interval = 30.0  # Save every 30 seconds if dirty
        self._running = False

    def get_device(
        self, device_type: str, device_id: int
    ) -> Optional[ScheiberCanDevice]:
        """
        Get device by type and ID.

        Args:
            device_type: Device type name (e.g., 'bloc9')
            device_id: Device bus ID

        Returns:
            Device instance or None if not found
        """
        key = (device_type, device_id)
        return self._device_map.get(key)

    def get_all_devices(self) -> List[ScheiberCanDevice]:
        """
        Get all registered devices.

        Returns:
            List of all device instances
        """
        return self.devices.copy()

    def restore_state(self, state_data: Dict[str, Any]) -> None:
        """
        Restore state for all devices.

        Args:
            state_data: State dictionary (device_type -> device_id -> device_state)
        """
        for device in self.devices:
            device_key = f"{device.device_type}_{device.device_id}"
            if device_key in state_data:
                try:
                    device.restore_from_state(state_data[device_key])
                    self.logger.info(f"Restored state for {device}")
                except Exception as e:
                    self.logger.error(f"Failed to restore state for {device}: {e}")

    def save_state(self) -> Dict[str, Any]:
        """
        Collect state from all devices.

        Returns:
            State dictionary (device_type -> device_id -> device_state)
        """
        state_data = {}
        for device in self.devices:
            device_key = f"{device.device_type}_{device.device_id}"
            try:
                state_data[device_key] = device.store_to_state()
            except Exception as e:
                self.logger.error(f"Failed to collect state from {device}: {e}")
        return state_data

    def start(self) -> None:
        """Start CAN message processing."""
        if self._running:
            raise RuntimeError("Already started")

        self._running = True

        # Load state if available
        if self.state_file:
            self._load_state()

        # Start CAN bus listening
        self.can_bus.start_listening(self._on_can_message)

        # Start periodic state saving
        if self.state_file:
            self._schedule_state_save()

        self.logger.info(f"Scheiber system started with {len(self.devices)} devices")

    def stop(self) -> None:
        """Stop CAN message processing."""
        self._running = False

        # Cancel state save timer
        if self._state_timer:
            self._state_timer.cancel()
            self._state_timer = None

        # Save state one last time
        if self.state_file and self._state_dirty:
            self._save_state()

        # Stop CAN bus
        self.can_bus.stop()

        self.logger.info("Scheiber system stopped")

    def subscribe_to_stats(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to CAN bus statistics updates.

        Args:
            callback: Function called with statistics dict
        """
        self.can_bus.subscribe_to_stats(callback)

    def _on_can_message(self, msg: can.Message) -> None:
        """
        Handle incoming CAN message.

        Routes message to matching device(s).
        """
        # Find matching device(s)
        matched = False
        for device, matcher in self._matchers:
            if matcher.matches(msg):
                matched = True
                try:
                    device.process_message(msg, matcher.property)
                    self._mark_state_dirty()
                except Exception as e:
                    self.logger.error(
                        f"Error processing message in {device}: {e}", exc_info=True
                    )

        # Log unknown arbitration IDs (once)
        if not matched:
            if msg.arbitration_id not in self._unknown_ids:
                self._unknown_ids.add(msg.arbitration_id)
                self.logger.warning(
                    f"Unknown CAN ID: 0x{msg.arbitration_id:08X} "
                    f"Data: {msg.data.hex()}"
                )

    def _mark_state_dirty(self) -> None:
        """Mark state as dirty (needs saving)."""
        with self._state_lock:
            self._state_dirty = True

    def _load_state(self) -> None:
        """Load state from file."""
        if not self.state_file:
            return

        state_path = Path(self.state_file)
        if not state_path.exists():
            self.logger.info(f"No state file found: {self.state_file}")
            return

        try:
            with open(state_path, "r") as f:
                state_data = json.load(f)
            self.restore_state(state_data)
            self.logger.info(f"Loaded state from: {self.state_file}")
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")

    def _save_state(self) -> None:
        """Save state to file."""
        if not self.state_file:
            return

        try:
            state_data = self.save_state()
            state_path = Path(self.state_file)
            state_path.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically (write to temp, then rename)
            temp_path = state_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(state_data, f, indent=2)
            temp_path.replace(state_path)

            with self._state_lock:
                self._state_dirty = False

            self.logger.debug(f"Saved state to: {self.state_file}")
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")

    def _schedule_state_save(self) -> None:
        """Schedule periodic state saving."""
        if not self._running:
            return

        def save_if_dirty():
            if self._running:
                with self._state_lock:
                    should_save = self._state_dirty

                if should_save:
                    self._save_state()

                # Schedule next save
                self._schedule_state_save()

        self._state_timer = threading.Timer(self._state_interval, save_if_dirty)
        self._state_timer.daemon = True
        self._state_timer.start()
