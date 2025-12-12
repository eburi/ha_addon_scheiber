"""
CAN MQTT Bridge - Version 5.4.0 (Preview)

Prototype MQTT bridge using the new scheiber module for Home Assistant integration.
Uses factory pattern, observer notifications, and proper separation of concerns.

Note: This is a preview/prototype - not yet feature-complete.
"""

__version__ = "5.4.0-preview"

from .bridge import MQTTBridge
from .light import MQTTLight
from .switch import MQTTSwitch

__all__ = ["MQTTBridge", "MQTTLight", "MQTTSwitch"]
