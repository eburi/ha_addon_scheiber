"""Pytest fixtures for scheiber module tests."""

import pytest
import logging
from unittest.mock import Mock, MagicMock
import can


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return Mock(spec=logging.Logger)


@pytest.fixture
def mock_can_bus():
    """Create a mock CAN bus."""
    bus = Mock()
    bus.send = Mock()
    bus.shutdown = Mock()
    return bus


@pytest.fixture
def mock_can_message():
    """Factory for creating mock CAN messages."""

    def _create_message(arbitration_id, data, timestamp=0.0):
        msg = Mock(spec=can.Message)
        msg.arbitration_id = arbitration_id
        msg.data = data
        msg.timestamp = timestamp
        return msg

    return _create_message


@pytest.fixture
def mock_scheiber_can_bus():
    """Create a mock ScheiberCanBus."""
    from scheiber.can_bus import ScheiberCanBus

    bus = Mock(spec=ScheiberCanBus)
    bus.send_message = Mock()
    bus.start_listening = Mock()
    bus.stop = Mock()
    bus.read_only = False
    return bus
