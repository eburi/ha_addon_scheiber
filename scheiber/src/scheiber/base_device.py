"""
Abstract base class for all Scheiber CAN devices.

Defines the interface that all device types (Bloc9, Bloc7, etc.) must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import can
import logging


class ScheiberCanDevice(ABC):
    """
    Abstract base class for Scheiber CAN devices.

    Subclasses must implement:
    - get_matchers(): Return CAN message matchers
    - process_message(): Handle incoming CAN messages
    - restore_from_state(): Restore persisted state
    - store_to_state(): Return current state for persistence
    """

    def __init__(
        self,
        device_id: int,
        device_type: str,
        can_bus,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize base device.

        Args:
            device_id: Unique device ID (bus_id)
            device_type: Device type name (e.g., 'bloc9', 'bloc7')
            can_bus: ScheiberCanBus instance for sending messages
            logger: Optional logger instance
        """
        self.device_id = device_id
        self.device_type = device_type
        self.can_bus = can_bus
        self.logger = logger or logging.getLogger(
            f"{self.__class__.__name__}.{device_id}"
        )
        self._observers: List[Any] = []

    @abstractmethod
    def get_matchers(self) -> List:
        """
        Return list of Matcher objects for this device's CAN messages.

        Returns:
            List of Matcher instances
        """
        pass

    @abstractmethod
    def process_message(self, msg: can.Message) -> None:
        """
        Process incoming CAN message that matched this device.

        Args:
            msg: CAN message that matched
        """
        pass

    @abstractmethod
    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """
        Restore device state from persisted data.

        Args:
            state: State dictionary (device-specific format)
        """
        pass

    @abstractmethod
    def store_to_state(self) -> Dict[str, Any]:
        """
        Return current state for persistence.

        Returns:
            State dictionary (device-specific format)
        """
        pass

    def get_switches(self) -> List:
        """
        Return list of Switch instances (if any).

        Returns:
            List of Switch objects (empty by default)
        """
        return []

    def get_lights(self) -> List:
        """
        Return list of DimmableLight instances (if any).

        Returns:
            List of DimmableLight objects (empty by default)
        """
        return []

    def __str__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(device_id={self.device_id})"

    def __repr__(self) -> str:
        """Debug representation."""
        return f"{self.__class__.__name__}(device_id={self.device_id}, device_type='{self.device_type}')"

    def subscribe(self, observer: Any) -> None:
        """
        Subscribe to device-level events (e.g., heartbeats, device info).

        Args:
            observer: Callable that will be notified with event data
        """
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: Any) -> None:
        """
        Unsubscribe from device-level events.

        Args:
            observer: Observer to remove
        """
        if observer in self._observers:
            self._observers.remove(observer)

    def _notify_observers(self, event_data: Dict[str, Any]) -> None:
        """
        Notify all device-level observers of an event.

        Args:
            event_data: Dict containing event information
        """
        for observer in self._observers:
            observer(event_data)
