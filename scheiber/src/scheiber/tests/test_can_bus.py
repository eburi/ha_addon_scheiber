"""
Tests for ScheiberCanBus CAN I/O wrapper.

Tests CAN message sending/receiving, read-only mode, statistics, and observer pattern.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
import can

from scheiber.can_bus import ScheiberCanBus


class TestCanBusInitialization:
    """Test ScheiberCanBus initialization."""

    def test_initialization_with_bus(self, mock_logger):
        """Test initialization with existing CAN bus."""
        mock_bus = Mock(spec=can.BusABC)

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        assert can_bus.bus == mock_bus
        assert can_bus.read_only is False
        assert can_bus.messages_sent == 0
        assert can_bus.messages_received == 0

    def test_initialization_read_only(self, mock_logger):
        """Test initialization in read-only mode."""
        mock_bus = Mock(spec=can.BusABC)

        can_bus = ScheiberCanBus(bus=mock_bus, read_only=True, logger=mock_logger)

        assert can_bus.read_only is True

    def test_initialization_creates_bus_from_params(self, mock_logger):
        """Test initialization creates CAN bus from parameters."""
        with patch("can.interface.Bus") as mock_bus_class:
            mock_bus_instance = Mock(spec=can.BusABC)
            mock_bus_class.return_value = mock_bus_instance

            can_bus = ScheiberCanBus(
                channel="can0",
                interface="socketcan",
                bitrate=250000,
                logger=mock_logger,
            )

            # Should have created bus
            mock_bus_class.assert_called_once_with(
                channel="can0", interface="socketcan", bitrate=250000
            )
            assert can_bus.bus == mock_bus_instance


class TestCanBusSend:
    """Test sending CAN messages."""

    def test_send_message(self, mock_logger):
        """Test sending a CAN message."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        msg = can.Message(
            arbitration_id=0x02360698, data=[0, 0x01, 0x00, 0x00], is_extended_id=False
        )

        can_bus.send(msg)

        mock_bus.send.assert_called_once_with(msg)
        assert can_bus.messages_sent == 1

    def test_send_multiple_messages(self, mock_logger):
        """Test sending multiple messages updates counter."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        for i in range(5):
            msg = can.Message(
                arbitration_id=0x02360698,
                data=[i, 0x01, 0x00, 0x00],
                is_extended_id=False,
            )
            can_bus.send(msg)

        assert can_bus.messages_sent == 5

    def test_send_in_read_only_mode_blocks(self, mock_logger):
        """Test sending in read-only mode does not send to bus."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, read_only=True, logger=mock_logger)

        msg = can.Message(
            arbitration_id=0x02360698, data=[0, 0x01, 0x00, 0x00], is_extended_id=False
        )

        can_bus.send(msg)

        # Should NOT have sent to bus
        mock_bus.send.assert_not_called()
        # But should still count (for testing)
        assert can_bus.messages_sent == 1

    def test_send_error_handling(self, mock_logger):
        """Test send handles CAN errors gracefully."""
        mock_bus = Mock(spec=can.BusABC)
        mock_bus.send.side_effect = can.CanError("Bus error")

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        msg = can.Message(
            arbitration_id=0x02360698, data=[0, 0x01, 0x00, 0x00], is_extended_id=False
        )

        # Should not raise exception
        can_bus.send(msg)


class TestCanBusReceive:
    """Test receiving CAN messages."""

    def test_recv_message(self, mock_logger):
        """Test receiving a CAN message."""
        mock_bus = Mock(spec=can.BusABC)

        test_msg = can.Message(
            arbitration_id=0x02160698,
            data=[0x01, 150, 0x00, 0x00],
            is_extended_id=False,
        )
        mock_bus.recv.return_value = test_msg

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        msg = can_bus.recv(timeout=0.1)

        assert msg == test_msg
        assert can_bus.messages_received == 1

    def test_recv_timeout(self, mock_logger):
        """Test recv with timeout returns None."""
        mock_bus = Mock(spec=can.BusABC)
        mock_bus.recv.return_value = None  # Timeout

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        msg = can_bus.recv(timeout=0.1)

        assert msg is None
        assert can_bus.messages_received == 0

    def test_recv_multiple_messages(self, mock_logger):
        """Test receiving multiple messages updates counter."""
        mock_bus = Mock(spec=can.BusABC)

        test_msgs = [
            can.Message(arbitration_id=0x02160698, data=[i, 0, 0, 0]) for i in range(3)
        ]
        mock_bus.recv.side_effect = test_msgs

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        for _ in range(3):
            can_bus.recv(timeout=0.1)

        assert can_bus.messages_received == 3

    def test_recv_error_handling(self, mock_logger):
        """Test recv handles CAN errors gracefully."""
        mock_bus = Mock(spec=can.BusABC)
        mock_bus.recv.side_effect = can.CanError("Bus error")

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        # Should return None on error
        msg = can_bus.recv(timeout=0.1)
        assert msg is None


class TestCanBusObserver:
    """Test observer pattern for message notifications."""

    def test_subscribe_observer(self, mock_logger):
        """Test subscribing an observer."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        observer = Mock()
        can_bus.subscribe(observer)

        assert observer in can_bus.observers

    def test_unsubscribe_observer(self, mock_logger):
        """Test unsubscribing an observer."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        observer = Mock()
        can_bus.subscribe(observer)
        can_bus.unsubscribe(observer)

        assert observer not in can_bus.observers

    def test_notify_observers_on_recv(self, mock_logger):
        """Test observers are notified when messages are received."""
        mock_bus = Mock(spec=can.BusABC)

        test_msg = can.Message(arbitration_id=0x02160698, data=[0x01, 150, 0x00, 0x00])
        mock_bus.recv.return_value = test_msg

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        observer1 = Mock()
        observer2 = Mock()
        can_bus.subscribe(observer1)
        can_bus.subscribe(observer2)

        can_bus.recv(timeout=0.1)

        # Both observers should be called
        observer1.assert_called_once_with(test_msg)
        observer2.assert_called_once_with(test_msg)

    def test_notify_only_on_successful_recv(self, mock_logger):
        """Test observers not notified on recv timeout."""
        mock_bus = Mock(spec=can.BusABC)
        mock_bus.recv.return_value = None  # Timeout

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        observer = Mock()
        can_bus.subscribe(observer)

        can_bus.recv(timeout=0.1)

        # Observer should NOT be called
        observer.assert_not_called()


class TestCanBusStatistics:
    """Test statistics tracking and reporting."""

    def test_get_statistics(self, mock_logger):
        """Test getting statistics."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        # Send some messages
        for _ in range(3):
            msg = can.Message(arbitration_id=0x123, data=[])
            can_bus.send(msg)

        # Receive some messages
        test_msg = can.Message(arbitration_id=0x456, data=[])
        mock_bus.recv.return_value = test_msg
        for _ in range(2):
            can_bus.recv(timeout=0.1)

        stats = can_bus.get_statistics()

        assert stats["messages_sent"] == 3
        assert stats["messages_received"] == 2
        assert stats["read_only"] is False

    def test_statistics_in_read_only_mode(self, mock_logger):
        """Test statistics reflect read-only mode."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, read_only=True, logger=mock_logger)

        stats = can_bus.get_statistics()

        assert stats["read_only"] is True

    def test_reset_statistics(self, mock_logger):
        """Test resetting statistics counters."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        # Generate some activity
        msg = can.Message(arbitration_id=0x123, data=[])
        can_bus.send(msg)

        test_msg = can.Message(arbitration_id=0x456, data=[])
        mock_bus.recv.return_value = test_msg
        can_bus.recv(timeout=0.1)

        # Reset
        can_bus.reset_statistics()

        assert can_bus.messages_sent == 0
        assert can_bus.messages_received == 0


class TestCanBusShutdown:
    """Test CAN bus shutdown and cleanup."""

    def test_shutdown(self, mock_logger):
        """Test shutdown closes CAN bus."""
        mock_bus = Mock(spec=can.BusABC)
        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        can_bus.shutdown()

        mock_bus.shutdown.assert_called_once()

    def test_shutdown_error_handling(self, mock_logger):
        """Test shutdown handles errors gracefully."""
        mock_bus = Mock(spec=can.BusABC)
        mock_bus.shutdown.side_effect = Exception("Shutdown error")

        can_bus = ScheiberCanBus(bus=mock_bus, logger=mock_logger)

        # Should not raise exception
        can_bus.shutdown()


class TestCanBusContextManager:
    """Test ScheiberCanBus as context manager."""

    def test_context_manager(self, mock_logger):
        """Test using ScheiberCanBus with 'with' statement."""
        mock_bus = Mock(spec=can.BusABC)

        with ScheiberCanBus(bus=mock_bus, logger=mock_logger) as can_bus:
            msg = can.Message(arbitration_id=0x123, data=[])
            can_bus.send(msg)

        # Should have shut down
        mock_bus.shutdown.assert_called_once()

    def test_context_manager_with_exception(self, mock_logger):
        """Test context manager shuts down even on exception."""
        mock_bus = Mock(spec=can.BusABC)

        try:
            with ScheiberCanBus(bus=mock_bus, logger=mock_logger) as can_bus:
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should still have shut down
        mock_bus.shutdown.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
