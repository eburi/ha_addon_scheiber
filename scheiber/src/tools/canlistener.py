import os
import sys
import time
from collections import defaultdict

import can

# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import CAN decoding utilities
from can_decoder import DEVICE_TYPES, extract_property_value, find_device_and_matcher


def listen(can_interface="can1"):
    """Listen on `can_interface` and process known device patterns.

    Prints a line when the message data for a (device, bus_id, matcher) changes.
    Tracks device state across multiple message types.
    """
    last_seen = {}
    device_states = defaultdict(dict)  # (device_type, bus_id) -> {prop: value}

    bus = can.interface.Bus(channel=can_interface, interface="socketcan")
    try:
        print(f"Listening on {can_interface} (known device types only). Ctrl+C to stop")
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            arb = msg.arbitration_id
            device_key, device_config, matcher, bus_id = find_device_and_matcher(arb)

            if device_config is None or matcher is None:
                continue

            raw = bytes(msg.data)
            # Track per-matcher messages to detect changes
            id_triple = (device_key, bus_id, matcher["name"])
            prev = last_seen.get(id_triple)
            if prev == raw:
                continue
            last_seen[id_triple] = raw

            # Extract and update properties for this device instance
            device_instance = (device_key, bus_id)
            properties = matcher.get("properties", {})
            decoded_parts = []

            for prop_name, prop_config in properties.items():
                template = prop_config.get("template")
                formatter = prop_config.get("formatter", "{}")

                value = extract_property_value(raw, template)

                if value is not None:
                    # Update device state
                    device_states[device_instance][prop_name] = value
                    # Apply custom formatter if provided
                    formatted = formatter.format(value)
                    decoded_parts.append(formatted)
                else:
                    # Property extraction failed
                    decoded_parts.append(formatter.format("?"))

            decoded_str = " ".join(decoded_parts)
            # Include full hex dump for analysis (helps identify dimming bytes)
            hex_dump = " ".join(f"{i}:{b:02X}" for i, b in enumerate(raw))
            print(
                f"{device_config['name']} ID:{bus_id} [{matcher['name']}] PROPS:[{decoded_str}] HEX:[{hex_dump}]"
            )
    except KeyboardInterrupt:
        print("\n[listen] Stopping and shutting down bus")
    finally:
        bus.shutdown()


if __name__ == "__main__":
    import sys

    iface = sys.argv[1] if len(sys.argv) > 1 else "can1"
    listen(iface)
