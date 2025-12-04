import time
import can
from collections import defaultdict

# Hardcoded patterns for known devices. Keys are descriptive names; each
# pattern contains an address, mask, and a heuristic mapping of switches 
# to (byte_index, bit_index).
#
# Matching: (arbitration_id & mask) == (address & mask)
#
# The arbitration id structure used here is: full 32-bit id, where the
# lowest byte encodes the bloc9 id (with MSB set and ID shifted left by 3).
# The mask allows matching groups of IDs by masking out the variable bits.
PATTERNS = {
    'bloc9_lowprio': {
        'address': 0x00000600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 LowPrio',
        # heuristic: use byte 1 bits 0-5 for S1..S6
        'switches': {
            1: (1, 0), 2: (1, 1), 3: (1, 2), 4: (1, 3), 5: (1, 4), 6: (1, 5)
        }
    },
    'bloc9_s12': {
        'address': 0x02160600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S1&S2',
        # heuristic: byte 4 bits 0-1
        'switches': {1: (4, 0), 2: (4, 1)}
    },
    'bloc9_s34': {
        'address': 0x02180600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S3&S4',
        # heuristic: byte 6 bits 0-1
        'switches': {3: (6, 0), 4: (6, 1)}
    },
    'bloc9_s56': {
        'address': 0x021A0600,
        'mask': 0xFFFFFF00,  # Match upper 24 bits, ignore lowest byte
        'name': 'Bloc9 S5&S6',
        # heuristic: byte 6 bits 4-5
        'switches': {5: (6, 4), 6: (6, 5)}
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

            # decode switches if mapping available
            switches = pattern.get('switches', {})
            decoded = {}
            for s, (bi, bit) in switches.items():
                if bi < len(raw):
                    decoded[s] = 1 if (raw[bi] & (1 << bit)) else 0
                else:
                    decoded[s] = None

            # Build output
            decoded_str = ' '.join(str(decoded.get(i, '?')) if decoded.get(i, '?') is not None else '?' for i in range(1, 7))
            print(f"{pattern['name']} ID:{bloc9_id} RAW:{_format_data(raw)} DECODED:{decoded_str}")
    except KeyboardInterrupt:
        print("\n[listen] Stopping and shutting down bus")
    finally:
        bus.shutdown()


if __name__ == '__main__':
    import sys
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    listen(iface)


if __name__ == '__main__':
    import sys
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    listen(iface)
