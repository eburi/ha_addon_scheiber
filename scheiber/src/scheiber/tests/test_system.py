"""
Tests for ScheiberSystem device management and message routing.

Tests device registration, message routing, state persistence, and system lifecycle.
"""

import pytest
import time
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from scheiber.system import ScheiberSystem
from scheiber.bloc9 import Bloc9Device


class TestSystemInitialization:
    """Test ScheiberSystem initialization."""

    def test_initialization(self, mock_can_bus, mock_logger):
        """Test system initializes correctly."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        assert system.can_bus == mock_can_bus
        assert len(system.devices) == 0
        assert not system.running

    def test_initialization_with_state_file(self, mock_can_bus, mock_logger):
        """Test initialization with state file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_state.json"

            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            assert system.state_file == state_file


class TestDeviceRegistration:
    """Test device registration and management."""

    def test_add_device(self, mock_can_bus, mock_logger):
        """Test adding a device to the system."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        device = Bloc9Device(device_id=3, can_bus=mock_can_bus, logger=mock_logger)

        system.add_device(device)

        assert len(system.devices) == 1
        assert 3 in system.devices
        assert system.devices[3] == device

    def test_add_multiple_devices(self, mock_can_bus, mock_logger):
        """Test adding multiple devices."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        device1 = Bloc9Device(device_id=3, can_bus=mock_can_bus, logger=mock_logger)
        device2 = Bloc9Device(device_id=7, can_bus=mock_can_bus, logger=mock_logger)
        device3 = Bloc9Device(device_id=10, can_bus=mock_can_bus, logger=mock_logger)

        system.add_device(device1)
        system.add_device(device2)
        system.add_device(device3)

        assert len(system.devices) == 3
        assert 3 in system.devices
        assert 7 in system.devices
        assert 10 in system.devices

    def test_add_duplicate_device_id_raises_error(self, mock_can_bus, mock_logger):
        """Test adding device with duplicate ID raises ValueError."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        device1 = Bloc9Device(device_id=5, can_bus=mock_can_bus, logger=mock_logger)
        device2 = Bloc9Device(device_id=5, can_bus=mock_can_bus, logger=mock_logger)

        system.add_device(device1)

        with pytest.raises(ValueError, match="Device with id 5 already registered"):
            system.add_device(device2)

    def test_get_device(self, mock_can_bus, mock_logger):
        """Test retrieving device by ID."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        device = Bloc9Device(device_id=7, can_bus=mock_can_bus, logger=mock_logger)
        system.add_device(device)

        retrieved = system.get_device(7)
        assert retrieved == device

    def test_get_nonexistent_device(self, mock_can_bus, mock_logger):
        """Test retrieving nonexistent device returns None."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        assert system.get_device(999) is None


class TestMessageRouting:
    """Test CAN message routing to devices."""

    def test_route_message_to_device(self, mock_can_bus, mock_logger, mock_can_message):
        """Test message is routed to correct device."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        lights_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )
        system.add_device(device)

        # S1/S2 change message for device 3
        msg = mock_can_message(
            arbitration_id=0x02160698, data=[0x01, 150, 0x00, 0x00]  # device_id=3
        )

        system.process_message(msg)

        # Device should have processed the message
        assert device.lights["test"].get_brightness() == 150

    def test_route_message_to_multiple_devices(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test messages are routed to correct devices."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        lights_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device3 = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )
        device7 = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        system.add_device(device3)
        system.add_device(device7)

        # Message for device 3
        msg1 = mock_can_message(
            arbitration_id=0x02160698, data=[0x01, 100, 0x00, 0x00]  # device_id=3
        )
        system.process_message(msg1)

        # Message for device 7
        msg2 = mock_can_message(
            arbitration_id=0x021606B8, data=[0x01, 200, 0x00, 0x00]  # device_id=7
        )
        system.process_message(msg2)

        # Each device should have received only its message
        assert device3.lights["test"].get_brightness() == 100
        assert device7.lights["test"].get_brightness() == 200

    def test_ignore_message_for_unregistered_device(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test messages for unregistered devices are ignored."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        lights_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )
        system.add_device(device)

        # Message for device 7 (not registered)
        msg = mock_can_message(
            arbitration_id=0x021606B8, data=[0x01, 100, 0x00, 0x00]  # device_id=7
        )

        # Should not raise exception
        system.process_message(msg)

        # Device 3 should be unaffected
        assert device.lights["test"].get_brightness() == 0


class TestStatePersistence:
    """Test state save/restore functionality."""

    def test_save_state(self, mock_can_bus, mock_logger):
        """Test saving system state to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}
            device = Bloc9Device(
                device_id=3,
                lights_config=lights_config,
                can_bus=mock_can_bus,
                logger=mock_logger,
            )
            system.add_device(device)

            # Set some state
            device.lights["light1"].set_brightness(150)

            # Save state
            system.save_state()

            # Check file was created
            assert state_file.exists()

            # Read and verify content
            with open(state_file) as f:
                saved_state = json.load(f)

            assert "devices" in saved_state
            assert "3" in saved_state["devices"]
            assert saved_state["devices"]["3"]["lights"]["light1"]["brightness"] == 150

    def test_restore_state(self, mock_can_bus, mock_logger):
        """Test restoring system state from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            # Create state file
            state_data = {
                "devices": {
                    "3": {
                        "device_id": 3,
                        "lights": {"light1": {"brightness": 200, "is_on": True}},
                        "switches": {},
                    }
                }
            }

            with open(state_file, "w") as f:
                json.dump(state_data, f)

            # Create system and device
            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}
            device = Bloc9Device(
                device_id=3,
                lights_config=lights_config,
                can_bus=mock_can_bus,
                logger=mock_logger,
            )
            system.add_device(device)

            # Restore state
            system.restore_state()

            # Check device state was restored
            assert device.lights["light1"].get_brightness() == 200
            assert device.lights["light1"].is_on() is True

            # CRITICAL: No CAN commands should be sent
            mock_can_bus.send.assert_not_called()

    def test_restore_state_missing_file(self, mock_can_bus, mock_logger):
        """Test restoring with missing state file is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "nonexistent.json"

            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}
            device = Bloc9Device(
                device_id=3,
                lights_config=lights_config,
                can_bus=mock_can_bus,
                logger=mock_logger,
            )
            system.add_device(device)

            # Should not raise exception
            system.restore_state()

            # Device should remain in default state
            assert device.lights["light1"].get_brightness() == 0

    def test_restore_state_corrupt_file(self, mock_can_bus, mock_logger):
        """Test restoring with corrupt state file is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "corrupt.json"

            # Write invalid JSON
            with open(state_file, "w") as f:
                f.write("{ invalid json content }")

            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}
            device = Bloc9Device(
                device_id=3,
                lights_config=lights_config,
                can_bus=mock_can_bus,
                logger=mock_logger,
            )
            system.add_device(device)

            # Should not raise exception
            system.restore_state()

            # Device should remain in default state
            assert device.lights["light1"].get_brightness() == 0


class TestSystemLifecycle:
    """Test system start/stop lifecycle."""

    def test_start_system(self, mock_can_bus, mock_logger):
        """Test starting the system."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        # Mock the message reading thread
        with patch.object(system, "_message_loop"):
            system.start()

            assert system.running is True

    def test_stop_system(self, mock_can_bus, mock_logger):
        """Test stopping the system."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        # Mock the threads
        with patch.object(system, "_message_loop"):
            with patch.object(system, "_state_save_loop"):
                system.start()
                system.stop()

                assert system.running is False

    def test_stop_saves_state(self, mock_can_bus, mock_logger):
        """Test stop triggers state save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            system = ScheiberSystem(
                can_bus=mock_can_bus, state_file=state_file, logger=mock_logger
            )

            lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}
            device = Bloc9Device(
                device_id=3,
                lights_config=lights_config,
                can_bus=mock_can_bus,
                logger=mock_logger,
            )
            system.add_device(device)
            device.lights["light1"].set_brightness(180)

            # Mock threads
            with patch.object(system, "_message_loop"):
                with patch.object(system, "_state_save_loop"):
                    system.start()
                    system.stop()

            # State should be saved
            assert state_file.exists()

            with open(state_file) as f:
                saved = json.load(f)

            assert saved["devices"]["3"]["lights"]["light1"]["brightness"] == 180


class TestSystemMessageReading:
    """Test message reading from CAN bus."""

    def test_message_reading_routes_to_devices(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test messages from CAN bus are processed."""
        system = ScheiberSystem(can_bus=mock_can_bus, logger=mock_logger)

        lights_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )
        system.add_device(device)

        # Mock recv to return a message once, then None
        msg = mock_can_message(arbitration_id=0x02160698, data=[0x01, 100, 0x00, 0x00])

        mock_can_bus.recv.side_effect = [msg, None]

        # Start and quickly stop system
        with patch.object(system, "_state_save_loop"):
            system.start()
            time.sleep(0.05)  # Let message loop run briefly
            system.stop()

        # Device should have processed message
        assert device.lights["test"].get_brightness() == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
