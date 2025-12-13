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

    # Load persisted state BEFORE creating devices
    initial_state = _load_state(state_file, logger)

    # Create CAN bus
    can_bus = ScheiberCanBus(
        interface=can_interface,
        read_only=read_only,
        logger=logging.getLogger("ScheiberCanBus"),
    )

    # Create devices from configuration with initial state
    devices = _create_devices(config, can_bus, initial_state, logger)

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


def _load_state(state_file: Optional[str], logger: logging.Logger) -> dict:
    """
    Load persisted state from JSON file.

    Args:
        state_file: Path to state file (None = no state)
        logger: Logger instance

    Returns:
        State dictionary (device_key -> device_state) or empty dict
    """
    if not state_file:
        return {}

    state_path = Path(state_file)
    if not state_path.exists():
        logger.info(f"No state file found: {state_file} (starting fresh)")
        return {}

    try:
        import json

        with open(state_path, "r") as f:
            state_data = json.load(f)
        logger.info(f"Loaded persisted state from: {state_file}")
        return state_data
    except Exception as e:
        logger.error(f"Failed to load state file: {e} (starting fresh)")
        return {}


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
    config: dict, can_bus: ScheiberCanBus, initial_state: dict, logger: logging.Logger
) -> list:
    """
    Create device instances from configuration with initial state.

    Args:
        config: Configuration dictionary
        can_bus: CAN bus instance
        initial_state: Persisted state dictionary (device_key -> device_state)
        logger: Logger instance

    Returns:
        List of device instances
    """
    devices = []
    device_configs = config.get("devices", [])

    for device_config in device_configs:
        device_type = device_config.get("type")
        device_id = device_config.get("bus_id")  # Changed from "id" to "bus_id"

        if not device_type or device_id is None:
            logger.warning(f"Invalid device config: {device_config}")
            continue

        # Extract device-specific state
        device_key = f"{device_type}_{device_id}"
        device_state = initial_state.get(device_key, {})

        # Create device based on type
        if device_type == "bloc9":
            # Extract lights and switches configuration
            lights_config = device_config.get("lights", {})
            switches_config = device_config.get("switches", {})

            device = Bloc9Device(
                device_id=device_id,
                can_bus=can_bus,
                lights_config=lights_config,
                switches_config=switches_config,
                initial_state=device_state,
                logger=logging.getLogger(f"Bloc9.{device_id}"),
            )
            devices.append(device)

            num_lights = len(lights_config)
            num_switches = len(switches_config)
            logger.info(
                f"Created Bloc9 device: bus_id={device_id}, "
                f"{num_lights} lights, {num_switches} switches"
            )
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
