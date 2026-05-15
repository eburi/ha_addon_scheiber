"""Shared bridge runtime management for the Scheiber web app."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import can
from can_mqtt_bridge import MQTTBridge


@dataclass
class RuntimeSettings:
    """Runtime settings shared between the web app and the bridge."""

    can_interface: str
    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_user: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_prefix: str = "homeassistant"
    config_path: str = "/config/scheiber-config.yaml"
    state_file: Optional[str] = None
    log_level: str = "info"
    read_only: bool = False
    host: str = "0.0.0.0"
    port: int = 8099


class BridgeRuntimeController:
    """Manage a single shared MQTT bridge instance for the web app."""

    def __init__(
        self,
        settings: RuntimeSettings,
        bridge_factory=MQTTBridge,
        logger: Optional[logging.Logger] = None,
    ):
        self.settings = settings
        self.bridge_factory = bridge_factory
        self.logger = logger or logging.getLogger(__name__)

        self._bridge = None
        self._lock = threading.RLock()
        self._raw_message_subscribers: List[Callable[[can.Message], None]] = []
        self._last_error: Optional[str] = None
        self._started_at: Optional[float] = None
        self._last_reload_at: Optional[float] = None

    def start(self) -> None:
        """Start the managed bridge."""
        with self._lock:
            if self._bridge is not None:
                return
            bridge = self._create_bridge()
            try:
                bridge.start()
                self._attach_subscribers(bridge)
            except Exception as exc:
                self._last_error = str(exc)
                bridge.stop()
                raise

            self._bridge = bridge
            self._started_at = time.time()
            self._last_reload_at = self._started_at
            self._last_error = None
            self.logger.info("Scheiber bridge runtime started")

    def stop(self) -> None:
        """Stop the managed bridge."""
        with self._lock:
            if self._bridge is None:
                return
            try:
                self._bridge.stop()
            finally:
                self._bridge = None
            self.logger.info("Scheiber bridge runtime stopped")

    def reload(self) -> None:
        """Reload the bridge using the current settings/config file."""
        with self._lock:
            old_bridge = self._bridge
            self._bridge = None

            if old_bridge is not None:
                old_bridge.stop()

            bridge = self._create_bridge()
            try:
                bridge.start()
                self._attach_subscribers(bridge)
            except Exception as exc:
                self._last_error = str(exc)
                try:
                    bridge.stop()
                except Exception:
                    pass
                self.logger.error(f"Failed to reload bridge runtime: {exc}")
                raise

            self._bridge = bridge
            self._last_reload_at = time.time()
            self._last_error = None
            self.logger.info("Scheiber bridge runtime reloaded")

    def subscribe_to_messages(self, callback: Callable[[can.Message], None]) -> None:
        """Subscribe to raw CAN messages from the shared runtime."""
        with self._lock:
            if callback not in self._raw_message_subscribers:
                self._raw_message_subscribers.append(callback)
                if self._bridge is not None:
                    self._bridge.system.subscribe_to_messages(callback)

    def unsubscribe_from_messages(
        self, callback: Callable[[can.Message], None]
    ) -> None:
        """Remove a raw CAN message subscriber."""
        with self._lock:
            if callback in self._raw_message_subscribers:
                self._raw_message_subscribers.remove(callback)
                if self._bridge is not None:
                    self._bridge.system.unsubscribe_from_messages(callback)

    def has_live_runtime(self) -> bool:
        """Return whether the bridge is active."""
        with self._lock:
            return self._bridge is not None

    def get_status(self) -> dict:
        """Return a JSON-serializable runtime status snapshot."""
        with self._lock:
            effective_config_path = self._effective_config_path()
            config_exists = Path(self.settings.config_path).exists()
            return {
                "running": self._bridge is not None,
                "last_error": self._last_error,
                "started_at": self._started_at,
                "last_reload_at": self._last_reload_at,
                "can_interface": self.settings.can_interface,
                "mqtt_host": self.settings.mqtt_host,
                "mqtt_port": self.settings.mqtt_port,
                "config_path": self.settings.config_path,
                "effective_config_path": effective_config_path,
                "config_exists": config_exists,
                "state_file": self.settings.state_file,
            }

    def _attach_subscribers(self, bridge) -> None:
        for callback in self._raw_message_subscribers:
            bridge.system.subscribe_to_messages(callback)

    def _effective_config_path(self) -> Optional[str]:
        path = Path(self.settings.config_path)
        return self.settings.config_path if path.exists() else None

    def _create_bridge(self):
        config_path = self._effective_config_path()
        return self.bridge_factory(
            can_interface=self.settings.can_interface,
            mqtt_host=self.settings.mqtt_host,
            mqtt_port=self.settings.mqtt_port,
            mqtt_user=self.settings.mqtt_user,
            mqtt_password=self.settings.mqtt_password,
            mqtt_topic_prefix=self.settings.mqtt_topic_prefix,
            config_path=config_path,
            state_file=self.settings.state_file,
            log_level=self.settings.log_level,
            read_only=self.settings.read_only,
        )
