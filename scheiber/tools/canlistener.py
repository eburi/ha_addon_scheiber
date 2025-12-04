import time
import can
from collections import defaultdict

# Device-centric configuration structure.
# Each device type has:
#   - bus_id_extractor: template to extract device instance ID from arbitration_id
#   - matchers: list of message patterns that update device properties
#     Each matcher has:
#       - address/mask: for matching CAN messages (arbitration_id & mask) == (address & mask)
#       - name: descriptive name for logging
#       - properties: dict of property_name -> extraction config
#
# Property extraction templates:
#   - Bit extraction: "(byte_index,bit_index)" - extracts single bit (0 or 1)
#   - Byte extraction: "[byte_index]" - extracts full byte value (0-255)
#   - Formatter: optional format string for logging (default: '{}')
DEVICE_TYPES = {
    'bloc9': {
        'name': 'Bloc9',
        # Extract bus ID from lowest byte: clear MSB, shift right 3
        'bus_id_extractor': lambda arb_id: ((arb_id & 0xFF) & ~0x80) >> 3,
        'matchers': [
            {
                'address': 0x00000600,
                'mask': 0xFFFFFF00,
                'name': 'LowPrio Status',
                'properties': {
                    's1': {'template': '(1,0)', 'formatter': 'S1={}'},
                    's2': {'template': '(1,1)', 'formatter': 'S2={}'},
                    's3': {'template': '(1,2)', 'formatter': 'S3={}'},
                    's4': {'template': '(1,3)', 'formatter': 'S4={}'},
                    's5': {'template': '(1,4)', 'formatter': 'S5={}'},
                    's6': {'template': '(1,5)', 'formatter': 'S6={}'}
                }
            },
            {
                'address': 0x02160600,
                'mask': 0xFFFFFF00,
                'name': 'S1&S2 Change',
                'properties': {
                    's1': {'template': '(3,0)', 'formatter': 'S1={}'},
                    's2': {'template': '(3,1)', 'formatter': 'S2={}'}
                    # Example for dimming (once protocol is known):
                    # 's1_dim': {'template': '[4]', 'formatter': 'S1_DIM={}'},
                    # 's2_dim': {'template': '[5]', 'formatter': 'S2_DIM={}'}
                }
            },
            {
                'address': 0x02180600,
                'mask': 0xFFFFFF00,
                'name': 'S3&S4 Change',
                'properties': {
                    's3': {'template': '(6,0)', 'formatter': 'S3={}'},
                    's4': {'template': '(6,1)', 'formatter': 'S4={}'}
                }
            },
            {
                'address': 0x021A0600,
                'mask': 0xFFFFFF00,
                'name': 'S5&S6 Change',
                'properties': {
                    's5': {'template': '(6,4)', 'formatter': 'S5={}'},
                    's6': {'template': '(6,5)', 'formatter': 'S6={}'}
                }
            }
        ]
    }
}


def _find_device_and_matcher(arb_id):
    """Find device type and matching matcher for an arbitration ID.
    
    Returns (device_type_key, device_config, matcher, bus_id) or (None, None, None, None).
    """
    for device_key, device_config in DEVICE_TYPES.items():
        for matcher in device_config['matchers']:
            if (arb_id & matcher['mask']) == (matcher['address'] & matcher['mask']):
                bus_id = device_config['bus_id_extractor'](arb_id)
                return device_key, device_config, matcher, bus_id
    return None, None, None, None


def _bloc9_id_from_low(low):
    """Translate lowest byte to bloc9 id by clearing MSB then shifting right 3.
    
    DEPRECATED: Use device's bus_id_extractor instead.
    Kept for backward compatibility with external code.
    """
    return ((low & ~0x80) >> 3)


# Backward compatibility: export old names
def _prefix_lookup(arb):
    """DEPRECATED: Use _find_device_and_matcher instead.
    
    Returns (matcher_name, matcher_dict) for backward compatibility.
    Note: This only returns the first matching matcher, not the full device context.
    """
    device_key, device_config, matcher, bus_id = _find_device_and_matcher(arb)
    if matcher is None:
        return None, None
    # Return a compatible structure with the old interface
    return f"{device_key}_{matcher['name']}", matcher


# Backward compatibility: PATTERNS as a flattened view
# This allows old code to iterate PATTERNS.items() but should be migrated to DEVICE_TYPES
PATTERNS = {}
for device_key, device_config in DEVICE_TYPES.items():
    for matcher in device_config['matchers']:
        # Create unique key combining device and matcher
        pattern_key = f"{device_key}_{matcher['name'].lower().replace('&', '').replace(' ', '_')}"
        PATTERNS[pattern_key] = matcher


def _format_data(data):
    return " ".join(f"{b:02X}" for b in data)


def _parse_template(template):
    """Parse a template string into extraction parameters.
    
    Supports:
      - Bit extraction: '(byte_index,bit_index)' -> ('bit', byte_idx, bit_idx)
      - Byte extraction: '[byte_index]' -> ('byte', byte_idx, None)
    
    Returns ('bit'|'byte', byte_index, bit_index|None) or None if parsing fails.
    """
    try:
        template = template.strip()
        
        # Bit extraction: (byte_idx, bit_idx)
        if template.startswith('(') and template.endswith(')'):
            parts = template[1:-1].split(',')
            if len(parts) == 2:
                byte_idx = int(parts[0].strip())
                bit_idx = int(parts[1].strip())
                return ('bit', byte_idx, bit_idx)
        
        # Byte extraction: [byte_idx]
        elif template.startswith('[') and template.endswith(']'):
            byte_idx = int(template[1:-1].strip())
            return ('byte', byte_idx, None)
            
    except (ValueError, AttributeError):
        pass
    return None


def _extract_property_value(raw, template):
    """Extract a property value from raw CAN data using a template.
    
    Args:
        raw: bytes object containing CAN message data
        template: string like '(3,0)' for bit or '[4]' for byte extraction
    
    Returns:
        For bit extraction: 1 if bit is set, 0 if bit is clear
        For byte extraction: integer value 0-255
        None if extraction fails
    """
    parsed = _parse_template(template)
    if parsed is None:
        return None
    
    extract_type, byte_idx, bit_idx = parsed
    if byte_idx >= len(raw):
        return None
    
    if extract_type == 'bit':
        if bit_idx is None:
            return None
        return 1 if (raw[byte_idx] & (1 << bit_idx)) else 0
    elif extract_type == 'byte':
        return raw[byte_idx]
    
    return None


def listen(can_interface='can1'):
    """Listen on `can_interface` and process known device patterns.

    Prints a line when the message data for a (device, bus_id, matcher) changes.
    Tracks device state across multiple message types.
    """
    last_seen = {}
    device_states = defaultdict(dict)  # (device_type, bus_id) -> {prop: value}

    bus = can.interface.Bus(channel=can_interface, interface='socketcan')
    try:
        print(f"Listening on {can_interface} (known device types only). Ctrl+C to stop")
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            arb = msg.arbitration_id
            device_key, device_config, matcher, bus_id = _find_device_and_matcher(arb)
            
            if device_config is None or matcher is None:
                continue

            raw = bytes(msg.data)
            # Track per-matcher messages to detect changes
            id_triple = (device_key, bus_id, matcher['name'])
            prev = last_seen.get(id_triple)
            if prev == raw:
                continue
            last_seen[id_triple] = raw

            # Extract and update properties for this device instance
            device_instance = (device_key, bus_id)
            properties = matcher.get('properties', {})
            decoded_parts = []
            
            for prop_name, prop_config in properties.items():
                template = prop_config.get('template')
                formatter = prop_config.get('formatter', '{}')
                
                value = _extract_property_value(raw, template)
                
                if value is not None:
                    # Update device state
                    device_states[device_instance][prop_name] = value
                    # Apply custom formatter if provided
                    formatted = formatter.format(value)
                    decoded_parts.append(formatted)
                else:
                    # Property extraction failed
                    decoded_parts.append(formatter.format('?'))
            
            decoded_str = ' '.join(decoded_parts)
            # Include full hex dump for analysis (helps identify dimming bytes)
            hex_dump = ' '.join(f"{i}:{b:02X}" for i, b in enumerate(raw))
            print(f"{device_config['name']} ID:{bus_id} [{matcher['name']}] PROPS:[{decoded_str}] HEX:[{hex_dump}]")
    except KeyboardInterrupt:
        print("\n[listen] Stopping and shutting down bus")
    finally:
        bus.shutdown()


if __name__ == '__main__':
    import sys
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    listen(iface)
