#!/usr/bin/env python3
"""Tests for data directory configuration."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scheiber" / "src"))

import tempfile
from unittest.mock import MagicMock

import pytest

from devices import Bloc9


class TestDataDirConfiguration:
    """Test that data_dir configuration works correctly."""

    def test_default_data_dir_uses_src_location(self):
        """When data_dir is None, state cache uses .state_cache in src directory."""
        mqtt_client = MagicMock()
        can_bus = MagicMock()

        device = Bloc9(
            device_type="bloc9",
            device_id=10,
            device_config={"name": "Bloc9", "matchers": []},
            mqtt_client=mqtt_client,
            mqtt_topic_prefix="homeassistant",
            can_bus=can_bus,
            data_dir=None,
        )

        # Should use .state_cache relative to devices.py
        assert device.state_cache_dir.name == ".state_cache"
        # Should be in the src directory
        assert device.state_cache_dir.parent.name == "src"

    def test_custom_data_dir_uses_provided_path(self):
        """When data_dir is provided, state cache uses that path."""
        mqtt_client = MagicMock()
        can_bus = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            device = Bloc9(
                device_type="bloc9",
                device_id=10,
                device_config={"name": "Bloc9", "matchers": []},
                mqtt_client=mqtt_client,
                mqtt_topic_prefix="homeassistant",
                can_bus=can_bus,
                data_dir=tmpdir,
            )

            # Should use state_cache under the provided directory
            assert device.state_cache_dir == Path(tmpdir) / "state_cache"
            assert str(device.state_cache_dir).startswith(tmpdir)

    def test_docker_data_dir_path(self):
        """Verify Docker-style /data path works correctly."""
        mqtt_client = MagicMock()
        can_bus = MagicMock()

        device = Bloc9(
            device_type="bloc9",
            device_id=10,
            device_config={"name": "Bloc9", "matchers": []},
            mqtt_client=mqtt_client,
            mqtt_topic_prefix="homeassistant",
            can_bus=can_bus,
            data_dir="/data",
        )

        # Should use /data/state_cache
        assert device.state_cache_dir == Path("/data/state_cache")

    def test_state_file_path_respects_data_dir(self):
        """State file path should use the configured data directory."""
        mqtt_client = MagicMock()
        can_bus = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            device = Bloc9(
                device_type="bloc9",
                device_id=10,
                device_config={"name": "Bloc9", "matchers": []},
                mqtt_client=mqtt_client,
                mqtt_topic_prefix="homeassistant",
                can_bus=can_bus,
                data_dir=tmpdir,
            )

            state_file = device._get_state_file_path()
            expected_path = Path(tmpdir) / "state_cache" / "bloc9_10.json"
            assert state_file == expected_path
