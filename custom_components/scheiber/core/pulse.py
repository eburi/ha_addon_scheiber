"""
Momentary pulse output for Bloc9 channels.
"""

import logging
from typing import Callable, Dict, Optional

import can

from .output import Output


class PulseOutput(Output):
    """
    Momentary output that sends an ON impulse and expects hardware to self-reset.
    """

    def __init__(
        self,
        device_id: int,
        switch_nr: int,
        name: str,
        entity_id: str,
        send_command_func: Callable[[int, bool, Optional[int]], None],
        segment_id: int = 0,
        logger: Optional[logging.Logger] = None,
        dimming_threshold: int = 2,
    ):
        super().__init__(
            device_id,
            switch_nr,
            name,
            entity_id,
            send_command_func,
            segment_id,
            logger,
        )
        self.dimming_threshold = dimming_threshold

    def press(self) -> None:
        """Trigger the configured momentary output."""
        self.logger.info(f"Triggering pulse on S{self.switch_nr + 1}")
        self._send_command_func(self.switch_nr, True)

    def process_matching_message(self, msg: can.Message) -> None:
        """
        Track observed state changes for diagnostics without publishing HA state.
        """
        state, _brightness = self.get_state_from_can_message(
            msg, self.switch_nr, self.dimming_threshold
        )
        self._state = state

    def restore_from_state(self, state: Dict) -> None:
        """Pulse outputs do not restore persisted ON/OFF state."""

    def store_to_state(self) -> Dict:
        """Pulse outputs are stateless from the integration perspective."""
        return {}
