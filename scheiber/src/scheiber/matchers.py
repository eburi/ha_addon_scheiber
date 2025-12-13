"""
Message matching utilities for CAN bus messages.

Matchers use pattern/mask logic to identify CAN messages by arbitration ID.
"""

from dataclasses import dataclass
from typing import Optional
import can


@dataclass
class Matcher:
    """
    CAN message matcher using pattern and mask.

    A message matches if: (msg.arbitration_id & mask) == (pattern & mask)

    Args:
        pattern: The expected arbitration ID pattern
        mask: Bitmask to apply (0xFF masks all bits, 0x00 ignores all bits)
    """

    pattern: int
    mask: int

    def matches(self, msg: can.Message) -> bool:
        """Check if a CAN message matches this pattern."""
        return (msg.arbitration_id & self.mask) == (self.pattern & self.mask)

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"Matcher(pattern=0x{self.pattern:08X}, mask=0x{self.mask:08X})"
