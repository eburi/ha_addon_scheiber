import time
import can
from collections import defaultdict

# Hardcoded patterns for known devices. Keys are descriptive names; each
# pattern contains an address, mask, and property mappings.
#
# Matching: (arbitration_id & mask) == (address & mask)
#
# The arbitration id structure used here is: full 32-bit id, where the
# lowest byte encodes the bloc9 id (with MSB set and ID shifted left by 3).
# The mask allows matching groups of IDs by masking out the variable bits.
#
# Properties: Each property has a template string that specifies extraction:
#   - Bit extraction: "(byte_index,bit_index)" - extracts single bit (0 or 1)
#   - Byte extraction: "[byte_index]" - extracts full byte value (0-255)
# Optional 'formatter' can customize how the property appears in logs.
# Optional 'type' field: 'bit' (default) or 'byte' for dimming levels.
PATTERNS = {
    'bloc9_lowprio': {
        'address': 0x00000600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 LowPrio',
        # Properties extracted from byte 1 bits 0-5
        'properties': {
            's1': {'template': '(1,0)', 'formatter': 'S1={}'},
            's2': {'template': '(1,1)', 'formatter': 'S2={}'},
            's3': {'template': '(1,2)', 'formatter': 'S3={}'},
            's4': {'template': '(1,3)', 'formatter': 'S4={}'},
            's5': {'template': '(1,4)', 'formatter': 'S5={}'},
            's6': {'template': '(1,5)', 'formatter': 'S6={}'}
        }
    },
    'bloc9_s12': {
        'address': 0x02160600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S1&S2',
        # Properties extracted from byte 3 bits 0-1
        'properties': {
            's1': {'template': '(3,0)', 'formatter': 'S1={}'},
            's2': {'template': '(3,1)', 'formatter': 'S2={}'}
            # Example for dimming (once protocol is known):
            # 's1_dim': {'template': '[4]', 'type': 'byte', 'formatter': 'S1_DIM={}'},
            # 's2_dim': {'template': '[5]', 'type': 'byte', 'formatter': 'S2_DIM={}'}
        }
    },
    'bloc9_s34': {
        'address': 0x02180600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S3&S4',
        # Properties extracted from byte 6 bits 0-1
        'properties': {
            's3': {'template': '(6,0)', 'formatter': 'S3={}'},
            's4': {'template': '(6,1)', 'formatter': 'S4={}'}
        }
    },
    'bloc9_s56': {
        'address': 0x021A0600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S5&S6',
        # Properties extracted from byte 6 bits 4-5
        'properties': {
            's5': {'template': '(6,4)', 'formatter': 'S5={}'},
            's6': {'template': '(6,5)', 'formatter': 'S6={}'}
        }
    }
}


def _prefix_lookup(arb):
    """Return matching pattern key and pattern dict for arbitration id, or (None, None).
    
    Matching: (arbitration_id & mask) == (address & mask)
    This allows flexible matching by masking out variable bits.
    """
    for k, p in PATTERNS.items():
        if (arb & p['mask']) == (p['address'] & p['mask']):
            return k, p
    return None, None


def _bloc9_id_from_low(low):
    """Translate lowest byte to bloc9 id by clearing MSB then shifting right 3."""
    return ((low & ~0x80) >> 3)


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
    """Listen on `can_interface` but only process known hardcoded patterns.

    Prints a line when the message data for a (pattern, bloc9_id) changes.
    """
    last_seen = {}

    bus = can.interface.Bus(channel=can_interface, interface='socketcan')
    try:
        print(f"Listening on {can_interface} (known patterns only). Ctrl+C to stop")
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            arb = msg.arbitration_id
            key, pattern = _prefix_lookup(arb)
            if pattern is None:
                continue

            low = arb & 0xFF
            bloc9_id = _bloc9_id_from_low(low)

            raw = bytes(msg.data)
            id_pair = (key, bloc9_id)
            prev = last_seen.get(id_pair)
            if prev == raw:
                continue
            last_seen[id_pair] = raw

            # Extract properties using templates
            properties = pattern.get('properties', {})
            decoded_parts = []
            
            for prop_name, prop_config in properties.items():
                template = prop_config.get('template')
                formatter = prop_config.get('formatter', '{}')
                
                value = _extract_property_value(raw, template)
                
                if value is not None:
                    # Apply custom formatter if provided
                    formatted = formatter.format(value)
                    decoded_parts.append(formatted)
                else:
                    # Property extraction failed
                    decoded_parts.append(formatter.format('?'))
            
            decoded_str = ' '.join(decoded_parts)
            # Include full hex dump for analysis (helps identify dimming bytes)
            hex_dump = ' '.join(f"{i}:{b:02X}" for i, b in enumerate(raw))
            print(f"{pattern['name']} ID:{bloc9_id} PROPS:[{decoded_str}] HEX:[{hex_dump}]")
    except KeyboardInterrupt:
        print("\n[listen] Stopping and shutting down bus")
    finally:
        bus.shutdown()


if __name__ == '__main__':
    import sys
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    listen(iface)
