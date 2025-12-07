#!/usr/bin/env python3
"""
Configuration loader for Scheiber MQTT Bridge.

Loads and validates scheiber.yaml configuration file that defines which
Bloc9 outputs should be exposed to Home Assistant via MQTT Discovery.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

import yaml


logger = logging.getLogger(__name__)


def generate_entity_id_from_name(name: str, component: str) -> str:
    """
    Generate entity_id from entity name.

    Removes special characters, converts to lowercase, replaces spaces with underscores.

    Args:
        name: Entity display name
        component: Component type ('light' or 'switch')

    Returns:
        Full entity_id with component prefix (e.g., 'light.my_light')
    """
    # Remove special characters (keep only alphanumeric, spaces, and underscores)
    clean_name = re.sub(r"[^a-zA-Z0-9\s_]", "", name)
    # Replace spaces with underscores and convert to lowercase
    object_id = clean_name.replace(" ", "_").lower()
    # Remove any multiple consecutive underscores
    object_id = re.sub(r"_+", "_", object_id)
    # Remove leading/trailing underscores
    object_id = object_id.strip("_")

    if not object_id:
        raise ValueError(
            f"Cannot generate entity_id from name '{name}': no valid characters"
        )

    return f"{component}.{object_id}"


class DiscoveryConfig:
    """Holds discovery configuration for a single entity."""

    def __init__(
        self,
        name: str,
        entity_id: str,
        output: str,
        component: str,  # 'light' or 'switch'
        device_name: str,
        bus_id: int,
    ):
        self.name = name
        self.entity_id = entity_id
        self.output = output  # s1-s6
        self.component = component
        self.device_name = device_name
        self.bus_id = bus_id

    def __repr__(self):
        return (
            f"DiscoveryConfig({self.component}.{self.entity_id}, output={self.output})"
        )


class ScheiberConfig:
    """Holds parsed configuration for all devices."""

    def __init__(self):
        self.bloc9_configs: Dict[int, List[DiscoveryConfig]] = {}

    def add_bloc9_entity(self, config: DiscoveryConfig):
        """Add a discovery config for a Bloc9 entity."""
        if config.bus_id not in self.bloc9_configs:
            self.bloc9_configs[config.bus_id] = []
        self.bloc9_configs[config.bus_id].append(config)

    def get_bloc9_configs(self, bus_id: int) -> List[DiscoveryConfig]:
        """Get all discovery configs for a specific Bloc9 device."""
        return self.bloc9_configs.get(bus_id, [])

    def get_all_bloc9_ids(self) -> List[int]:
        """Get list of all configured Bloc9 bus IDs."""
        return list(self.bloc9_configs.keys())

    def get_summary(self) -> str:
        """Get summary of configuration for logging."""
        total_lights = sum(
            1
            for configs in self.bloc9_configs.values()
            for c in configs
            if c.component == "light"
        )
        total_switches = sum(
            1
            for configs in self.bloc9_configs.values()
            for c in configs
            if c.component == "switch"
        )
        return f"{len(self.bloc9_configs)} Bloc9 devices, {total_lights} lights, {total_switches} switches"


def load_config(config_path: str) -> Optional[ScheiberConfig]:
    """
    Load and parse scheiber.yaml configuration file.

    Args:
        config_path: Path to configuration file

    Returns:
        ScheiberConfig object or None if file doesn't exist

    Raises:
        ValueError: If configuration is invalid
    """
    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(f"Configuration file not found: {config_path}")
        logger.info(
            "No entities will be discovered. Create scheiber.yaml to configure discovery."
        )
        return None

    try:
        with open(config_file, "r") as f:
            raw_config = yaml.safe_load(f)

        if not raw_config:
            logger.warning(f"Configuration file is empty: {config_path}")
            return None

        config = ScheiberConfig()

        # Parse Bloc9 configurations
        bloc9_list = raw_config.get("bloc9", [])
        if not isinstance(bloc9_list, list):
            raise ValueError("'bloc9' must be a list")

        # Track all entity_ids and outputs for integrity checks
        all_entity_ids: Set[str] = set()

        for bloc9_device in bloc9_list:
            if not isinstance(bloc9_device, dict):
                raise ValueError("Each bloc9 entry must be a dictionary")

            bus_id = bloc9_device.get("bus_id")
            device_name = bloc9_device.get("name", f"Bloc9 {bus_id}")

            if bus_id is None:
                raise ValueError("Each bloc9 entry must have a 'bus_id'")

            # Track outputs used on this device for integrity check
            device_outputs: Set[str] = set()

            # Parse lights
            lights = bloc9_device.get("lights", [])
            if not isinstance(lights, list):
                raise ValueError(f"Bloc9 {bus_id}: 'lights' must be a list")

            for light in lights:
                if not isinstance(light, dict):
                    raise ValueError(f"Bloc9 {bus_id}: Each light must be a dictionary")

                name = light.get("name")
                entity_id = light.get("entity_id")
                output = light.get("output")

                if not name or not output:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Light must have 'name' and 'output'"
                    )

                # Generate entity_id from name if not provided
                if not entity_id:
                    entity_id = generate_entity_id_from_name(name, "light")
                    logger.debug(
                        f"Generated entity_id '{entity_id}' from name '{name}'"
                    )

                # Validate output format (s1-s6)
                if not (
                    isinstance(output, str)
                    and output.startswith("s")
                    and len(output) == 2
                    and output[1].isdigit()
                    and 1 <= int(output[1]) <= 6
                ):
                    raise ValueError(
                        f"Bloc9 {bus_id}: Invalid output '{output}', must be s1-s6"
                    )

                # Integrity check: output already used on this device?
                if output in device_outputs:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Output '{output}' is assigned to multiple entities"
                    )
                device_outputs.add(output)

                # Extract object_id from entity_id (remove component prefix if present)
                object_id = entity_id
                if "." in entity_id:
                    object_id = entity_id.split(".", 1)[1]

                # Integrity check: entity_id already used?
                full_entity_id = f"light.{object_id}"
                if full_entity_id in all_entity_ids:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Entity ID '{full_entity_id}' is used multiple times"
                    )
                all_entity_ids.add(full_entity_id)

                config.add_bloc9_entity(
                    DiscoveryConfig(
                        name=name,
                        entity_id=object_id,
                        output=output,
                        component="light",
                        device_name=device_name,
                        bus_id=bus_id,
                    )
                )

            # Parse switches
            switches = bloc9_device.get("switches", [])
            if not isinstance(switches, list):
                raise ValueError(f"Bloc9 {bus_id}: 'switches' must be a list")

            for switch in switches:
                if not isinstance(switch, dict):
                    raise ValueError(
                        f"Bloc9 {bus_id}: Each switch must be a dictionary"
                    )

                name = switch.get("name")
                entity_id = switch.get("entity_id")
                output = switch.get("output")

                if not name or not output:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Switch must have 'name' and 'output'"
                    )

                # Generate entity_id from name if not provided
                if not entity_id:
                    entity_id = generate_entity_id_from_name(name, "switch")
                    logger.debug(
                        f"Generated entity_id '{entity_id}' from name '{name}'"
                    )

                # Validate output format (s1-s6)
                if not (
                    isinstance(output, str)
                    and output.startswith("s")
                    and len(output) == 2
                    and output[1].isdigit()
                    and 1 <= int(output[1]) <= 6
                ):
                    raise ValueError(
                        f"Bloc9 {bus_id}: Invalid output '{output}', must be s1-s6"
                    )

                # Integrity check: output already used on this device?
                if output in device_outputs:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Output '{output}' is assigned to multiple entities"
                    )
                device_outputs.add(output)

                # Extract object_id from entity_id (remove component prefix if present)
                object_id = entity_id
                if "." in entity_id:
                    object_id = entity_id.split(".", 1)[1]

                # Integrity check: entity_id already used?
                full_entity_id = f"switch.{object_id}"
                if full_entity_id in all_entity_ids:
                    raise ValueError(
                        f"Bloc9 {bus_id}: Entity ID '{full_entity_id}' is used multiple times"
                    )
                all_entity_ids.add(full_entity_id)

                config.add_bloc9_entity(
                    DiscoveryConfig(
                        name=name,
                        entity_id=object_id,
                        output=output,
                        component="switch",
                        device_name=device_name,
                        bus_id=bus_id,
                    )
                )

        logger.info(f"Loaded configuration from {config_path}: {config.get_summary()}")

        # Debug: Log detailed configuration for each device
        for bus_id in sorted(config.get_all_bloc9_ids()):
            device_configs = config.get_bloc9_configs(bus_id)
            logger.debug(f"Bloc9 {bus_id}: {len(device_configs)} entities configured")
            for dc in device_configs:
                logger.debug(
                    f"  - {dc.component}.{dc.entity_id} "
                    f"(name='{dc.name}', output={dc.output})"
                )

        return config

    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML configuration: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")
