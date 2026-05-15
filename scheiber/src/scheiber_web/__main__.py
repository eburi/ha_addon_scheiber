"""Command-line entry point for the Scheiber web interface."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .app import create_app
from .runtime import BridgeRuntimeController, RuntimeSettings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scheiber web setup interface with shared CAN/MQTT runtime"
    )

    parser.add_argument("--can-interface", required=True, help="CAN interface")
    parser.add_argument("--mqtt-host", required=True, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-user", help="MQTT username")
    parser.add_argument("--mqtt-password", help="MQTT password")
    parser.add_argument(
        "--mqtt-topic-prefix",
        default="homeassistant",
        help="MQTT topic prefix",
    )
    parser.add_argument("--config", help="Path to scheiber-config.yaml config file")
    parser.add_argument("--state-file", help="Path to state persistence file")
    parser.add_argument("--data-dir", help="Data directory for state persistence")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    parser.add_argument("--read-only", action="store_true", help="Read-only mode")
    parser.add_argument("--host", default="0.0.0.0", help="Web server host")
    parser.add_argument("--port", type=int, default=8099, help="Web server port")

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    state_file = args.state_file
    if not state_file and args.data_dir:
        state_file = str(Path(args.data_dir) / "scheiber_state.json")

    settings = RuntimeSettings(
        can_interface=args.can_interface,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_password=args.mqtt_password,
        mqtt_topic_prefix=args.mqtt_topic_prefix,
        config_path=args.config or "/config/scheiber-config.yaml",
        state_file=state_file,
        log_level=args.log_level,
        read_only=args.read_only,
        host=args.host,
        port=args.port,
    )

    runtime_controller = BridgeRuntimeController(settings)
    try:
        runtime_controller.start()
    except Exception as exc:
        logger.error(f"Bridge runtime did not start cleanly: {exc}")

    app = create_app(settings, runtime_controller=runtime_controller)
    app.run(host=settings.host, port=settings.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
