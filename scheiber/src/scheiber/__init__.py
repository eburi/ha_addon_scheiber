"""
Scheiber Module - Client-agnostic CAN bus layer.

Public API for creating and managing Scheiber CAN devices.
"""

import logging
import yaml
from pathlib import Path
from typing import Optional

from .can_bus import ScheiberCanBus
from .system import ScheiberSystem
from .bloc9 import Bloc9Device
from .base_device import ScheiberCanDevice
from .matchers import Matcher

__version__ = "5.0.0"
__all__ = ["create_scheiber_system", "ScheiberSystem", "ScheiberCanBus", "Bloc9Device"]


def create_scheiber_system(
    can_interface: str,
    config_path: Optional[str] = None,
    state_file: Optional[str] = None,
    log_level: str = "info",
    read_only: bool = False,
) -> ScheiberSystem:
    """
    Factory method to create configured Scheiber system.

    Args:
        can_interface: CAN interface name (e.g., 'can0', 'can1')
        config_path: Path to scheiber.yaml configuration file (optional)
        state_file: Path to state persistence file (optional)
        log_level: Logging level ('debug', 'info', 'warning', 'error')
        read_only: If True, no CAN messages will be sent

    Returns:
        Configured ScheiberSystem instance

    Raises:
        ValueError: If configuration is invalid
        FileNotFoundError: If config file doesn't exist
    """
    # Setup logging
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    log_level_value = level_map.get(log_level.lower(), logging.INFO)
    logging.basicConfig(
        level=log_level_value,
        format="[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Parse configuration
    config = _load_config(config_path, logger)

    # Create CAN bus
    can_bus = ScheiberCanBus(
        interface=can_interface,
        read_only=read_only,
        logger=logging.getLogger("ScheiberCanBus"),
    )

    # Create devices from configuration
    devices = _create_devices(config, can_bus, logger)

    # Validate unique device IDs per type
    _validate_unique_ids(devices)

    # Create system
    system = ScheiberSystem(
        can_bus=can_bus,
        devices=devices,
        state_file=state_file,
        logger=logging.getLogger("ScheiberSystem"),
    )

    logger.info(
        f"Created Scheiber system with {len(devices)} devices on {can_interface}"
    )
    return system


def _load_config(config_path: Optional[str], logger: logging.Logger) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file (None = use defaults)
        logger: Logger instance

    Returns:
        Configuration dictionary
    """
    if not config_path:
        logger.info("No config file provided, using auto-discovery mode")
        return {"devices": []}

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from: {config_path}")
        return config
    except Exception as e:
        raise ValueError(f"Failed to parse configuration: {e}")


def _create_devices(
    config: dict, can_bus: ScheiberCanBus, logger: logging.Logger
) -> list:
    """
    Create device instances from configuration.

    Args:
        config: Configuration dictionary
        can_bus: CAN bus instance
        logger: Logger instance

    Returns:
        List of device instances
    """
    devices = []
    device_configs = config.get("devices", [])

    for device_config in device_configs:
        device_type = device_config.get("type")
        device_id = device_config.get("id")

        if not device_type or device_id is None:
            logger.warning(f"Invalid device config: {device_config}")
            continue

        # Create device based on type
        if device_type == "bloc9":
            device = Bloc9Device(
                device_id=device_id,
                can_bus=can_bus,
                logger=logging.getLogger(f"Bloc9.{device_id}"),
            )
            devices.append(device)
            logger.info(f"Created Bloc9 device: bus_id={device_id}")
        else:
            logger.warning(f"Unknown device type: {device_type}")

    return devices


def _validate_unique_ids(devices: list) -> None:
    """
    Validate that device IDs are unique per device type.

    Args:
        devices: List of device instances

    Raises:
        ValueError: If duplicate device ID found
    """
    seen = set()
    for device in devices:
        key = (device.device_type, device.device_id)
        if key in seen:
            raise ValueError(
                f"Duplicate device: {device.device_type} bus_id={device.device_id}"
            )
        seen.add(key)
