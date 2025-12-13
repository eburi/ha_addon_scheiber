"""
Low-level CAN bus wrapper.

Handles CAN socket I/O, statistics tracking, and observer notifications.
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

import can


class ScheiberCanBus:
    """
    Low-level CAN bus wrapper with statistics tracking.

    Provides clean interface for sending/receiving CAN messages with optional
    read-only mode and periodic statistics notifications.
    """

    def __init__(
        self,
        interface: str,
        read_only: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize CAN bus wrapper.

        Args:
            interface: CAN interface name (e.g., 'can0', 'can1')
            read_only: If True, block all message sending
            logger: Optional logger instance
        """
        self.interface = interface
        self.read_only = read_only
        self.logger = logger or logging.getLogger(__name__)

        self.bus: Optional[can.BusABC] = None
        self.notifier: Optional[can.Notifier] = None
        self._message_callback: Optional[Callable[[can.Message], None]] = None
        self._running = False

        # Statistics tracking
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "unique_ids": set(),
            "start_time": None,
        }
        self.stats_lock = threading.Lock()

        # Observer pattern for statistics updates
        self._stats_observers: List[Callable[[Dict[str, Any]], None]] = []
        self._stats_timer: Optional[threading.Timer] = None
        self._stats_interval = 10.0  # seconds

    def send_message(self, arbitration_id: int, data: bytes) -> None:
        """
        Send CAN message if not in read-only mode.

        Args:
            arbitration_id: CAN message arbitration ID
            data: Message data bytes

        Raises:
            RuntimeError: If bus not initialized or in read-only mode
        """
        if self.read_only:
            self.logger.warning(
                f"Cannot send message in read-only mode: 0x{arbitration_id:08X}"
            )
            return

        if not self.bus:
            raise RuntimeError("CAN bus not initialized")

        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)
        try:
            self.bus.send(msg)
            with self.stats_lock:
                self.stats["messages_sent"] += 1
            self.logger.debug(f"CAN TX: ID=0x{arbitration_id:08X} Data={data.hex()}")
        except Exception as e:
            self.logger.error(f"Failed to send CAN message: {e}")
            raise

    def start_listening(
        self, on_message_callback: Callable[[can.Message], None]
    ) -> None:
        """
        Start listening for CAN messages.

        Args:
            on_message_callback: Callback function called for each received message

        Raises:
            RuntimeError: If already listening or bus initialization fails
        """
        if self._running:
            raise RuntimeError("Already listening")

        self._message_callback = on_message_callback

        try:
            # Open CAN bus
            self.bus = can.interface.Bus(channel=self.interface, interface="socketcan")
            self.logger.info(
                f"Opened CAN interface: {self.interface} (read_only={self.read_only})"
            )

            # Set up message receiver
            self.notifier = can.Notifier(self.bus, [self._on_message_received])

            self._running = True
            with self.stats_lock:
                self.stats["start_time"] = time.time()

            # Start periodic statistics notifications
            self._schedule_stats_notification()

        except Exception as e:
            self.logger.error(f"Failed to start CAN bus: {e}")
            self.stop()
            raise

    def stop(self) -> None:
        """Stop listening and close CAN bus."""
        self._running = False

        # Cancel statistics timer
        if self._stats_timer:
            self._stats_timer.cancel()
            self._stats_timer = None

        # Stop notifier
        if self.notifier:
            self.notifier.stop()
            self.notifier = None

        # Close bus
        if self.bus:
            try:
                self.bus.shutdown()
                self.logger.info(f"Closed CAN interface: {self.interface}")
            except Exception as e:
                self.logger.error(f"Error closing CAN bus: {e}")
            finally:
                self.bus = None

    def get_stats(self) -> Dict[str, Any]:
        """
        Return current CAN bus statistics.

        Returns:
            Dictionary with statistics (messages_received, messages_sent, unique_ids, uptime)
        """
        with self.stats_lock:
            uptime = None
            if self.stats["start_time"]:
                uptime = time.time() - self.stats["start_time"]

            return {
                "messages_received": self.stats["messages_received"],
                "messages_sent": self.stats["messages_sent"],
                "unique_ids": len(self.stats["unique_ids"]),
                "uptime_seconds": uptime,
            }

    def subscribe_to_stats(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to periodic statistics updates.

        Args:
            callback: Function called with statistics dict
        """
        if callback not in self._stats_observers:
            self._stats_observers.append(callback)

    def unsubscribe_from_stats(
        self, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Unsubscribe from statistics updates.

        Args:
            callback: Previously subscribed callback
        """
        if callback in self._stats_observers:
            self._stats_observers.remove(callback)

    def _on_message_received(self, msg: can.Message) -> None:
        """Internal callback for received CAN messages."""
        # Update statistics
        with self.stats_lock:
            self.stats["messages_received"] += 1
            self.stats["unique_ids"].add(msg.arbitration_id)

        # Forward to user callback
        if self._message_callback:
            try:
                self._message_callback(msg)
            except Exception as e:
                self.logger.error(f"Error in message callback: {e}", exc_info=True)

    def _schedule_stats_notification(self) -> None:
        """Schedule next statistics notification."""
        if not self._running:
            return

        def notify_stats():
            if self._running:
                stats = self.get_stats()
                for observer in self._stats_observers:
                    try:
                        observer(stats)
                    except Exception as e:
                        self.logger.error(f"Error in stats observer: {e}")

                # Schedule next notification
                self._schedule_stats_notification()

        self._stats_timer = threading.Timer(self._stats_interval, notify_stats)
        self._stats_timer.daemon = True
        self._stats_timer.start()
