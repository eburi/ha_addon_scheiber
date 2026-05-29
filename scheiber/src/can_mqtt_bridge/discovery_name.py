"""
Helpers for Home Assistant MQTT discovery naming.
"""

import re


def format_discovery_name(entity_id: str) -> str:
    """Convert an entity/topic slug into a human-readable discovery name."""
    parts = [part for part in re.split(r"[_-]+", entity_id.strip()) if part]
    return " ".join(part.capitalize() for part in parts)
