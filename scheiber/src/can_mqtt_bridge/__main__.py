"""
Main entry point for can_mqtt_bridge command.

Usage:
    python -m can_mqtt_bridge --can-interface can0 --mqtt-host localhost [options]
"""

import argparse
import logging
import signal
import sys
from pathlib import Path

from .bridge import MQTTBridge


def main():
    """Main entry point for MQTT bridge."""
    parser = argparse.ArgumentParser(
        description="CAN MQTT Bridge - Connect Scheiber devices to Home Assistant"
    )

    # CAN options
    parser.add_argument(
        "--can-interface", required=True, help="CAN interface (e.g., can0, can1)"
    )

    # MQTT options
    parser.add_argument("--mqtt-host", required=True, help="MQTT broker host")
    parser.add_argument(
        "--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)"
    )
    parser.add_argument("--mqtt-user", help="MQTT username")
    parser.add_argument("--mqtt-password", help="MQTT password")
    parser.add_argument(
        "--mqtt-topic-prefix",
        default="homeassistant",
        help="MQTT topic prefix (default: homeassistant)",
    )

    # Configuration options
    parser.add_argument("--config", help="Path to scheiber.yaml config file")
    parser.add_argument("--state-file", help="Path to state persistence file")
    parser.add_argument("--data-dir", help="Data directory for state persistence")

    # Logging options
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )

    # Mode options
    parser.add_argument(
        "--read-only", action="store_true", help="Read-only mode (no CAN commands sent)"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting CAN MQTT Bridge v5.4.0-preview")
    logger.info(f"CAN Interface: {args.can_interface}")
    logger.info(f"MQTT Broker: {args.mqtt_host}:{args.mqtt_port}")
    logger.info(f"Topic Prefix: {args.mqtt_topic_prefix}")

    # Determine state file path
    state_file = args.state_file
    if not state_file and args.data_dir:
        state_file = str(Path(args.data_dir) / "scheiber_state.json")

    # Create bridge
    try:
        bridge = MQTTBridge(
            can_interface=args.can_interface,
            mqtt_host=args.mqtt_host,
            mqtt_port=args.mqtt_port,
            mqtt_user=args.mqtt_user,
            mqtt_password=args.mqtt_password,
            mqtt_topic_prefix=args.mqtt_topic_prefix,
            config_path=args.config,
            state_file=state_file,
            log_level=args.log_level,
            read_only=args.read_only,
        )
    except Exception as e:
        logger.error(f"Failed to create bridge: {e}")
        return 1

    # Setup signal handlers for clean shutdown
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start bridge
    try:
        bridge.start()
        logger.info("Bridge running... (Press Ctrl+C to stop)")

        # Keep running
        signal.pause()
    except Exception as e:
        logger.error(f"Bridge error: {e}")
        bridge.stop()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
