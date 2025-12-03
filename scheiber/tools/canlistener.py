import os
import re
import time
import can
from collections import defaultdict


def _parse_dump_messages():
    """Parse sample dump files in `data/` and return a list of messages.

    Returns a list of dicts: {'arbitration_id': int, 'data': [ints], 'line_no': int, 'file': str}
    """
    msgs = []
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.isdir(data_dir):
        return msgs

    # Regex: capture 8-hex arbitration id and following hex byte sequence
    id_re = re.compile(r'\b([0-9A-Fa-f]{8})\b')
    data_re = re.compile(r'([0-9A-Fa-f]{2})(?:\s+|$)')

    for fname in os.listdir(data_dir):
        path = os.path.join(data_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f, start=1):
                    m = id_re.search(line)
                    if not m:
                        continue
                    arb_hex = m.group(1)
                    data_bytes = data_re.findall(line[m.end():])
                    if not data_bytes:
                        continue
                    try:
                        arb = int(arb_hex, 16)
                    except ValueError:
                        continue
                    data = [int(b, 16) for b in data_bytes]
                    msgs.append({'arbitration_id': arb, 'data': data, 'line_no': i, 'file': fname})
        except Exception:
            continue

    return msgs


def _build_switch_bit_mapping():
    """Build mapping of bloc9_id -> switch_nr -> (byte_index, bit_index)

    Uses sample dumps to infer which payload bit corresponds to which switch number.
    """
    msgs = _parse_dump_messages()
    if not msgs:
        return {}, set()

    # Index messages by low byte (lowest 8 bits of arbitration id)
    by_low = defaultdict(list)
    for m in msgs:
        low = m['arbitration_id'] & 0xFF
        by_low[low].append(m)

    mapping = defaultdict(dict)
    status_prefixes = set()

    for low, msg_list in by_low.items():
        msg_list.sort(key=lambda x: (x['file'], x['line_no']))

        for idx, m in enumerate(msg_list[:-1]):
            arb_hex = f"{m['arbitration_id']:08X}"
            if not arb_hex.startswith('0236'):
                continue
            if not m['data']:
                continue
            switch_nr = m['data'][0]

            # find next status message candidate
            for nxt in msg_list[idx+1:idx+6]:
                nxt_hex = f"{nxt['arbitration_id']:08X}"
                if not nxt_hex.startswith('02'):
                    continue
                status_prefixes.add(nxt['arbitration_id'] & 0xFFFFFF00)

                prev = None
                for back in reversed(msg_list[:idx]):
                    back_hex = f"{back['arbitration_id']:08X}"
                    if back_hex.startswith('02'):
                        prev = back
                        break

                if prev is None:
                    prev_data = [0] * len(nxt['data'])
                else:
                    prev_data = prev['data']

                L = max(len(prev_data), len(nxt['data']))
                pd = prev_data + [0] * (L - len(prev_data))
                nd = nxt['data'] + [0] * (L - len(nxt['data']))

                diffs = []
                for bi in range(L):
                    diff = (~pd[bi]) & nd[bi]
                    if diff:
                        for bit in range(8):
                            if diff & (1 << bit):
                                diffs.append((bi, bit))

                if diffs:
                    bloc9_id = ((low & ~0x80) >> 3)
                    byte_i, bit_i = diffs[0]
                    mapping[bloc9_id][switch_nr] = (byte_i, bit_i)
                    break

    return mapping, status_prefixes


def listen(can_interface='can1'):
    """Open the CAN interface and listen for Bloc9 status messages until killed.

    For each Bloc9 status message found, print a line:
      ID:<id> <s1> <s2> <s3> <s4> <s5> <s6>
    """
    mapping, status_prefixes = _build_switch_bit_mapping()
    print(f"[listen] Learned mappings for {len(mapping)} devices")

    bus = can.interface.Bus(channel=can_interface, interface='socketcan')
    try:
        print(f"Listening on {can_interface} — press Ctrl+C to stop")
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            arb = msg.arbitration_id
            low = arb & 0xFF
            prefix = arb & 0xFFFFFF00

            if status_prefixes and prefix not in status_prefixes:
                continue

            if not msg.data:
                continue

            bloc9_id = ((low & ~0x80) >> 3)

            out_states = []
            for s in range(1, 7):
                if bloc9_id in mapping and s in mapping[bloc9_id]:
                    bi, bit = mapping[bloc9_id][s]
                    if bi < len(msg.data):
                        val = 1 if (msg.data[bi] & (1 << bit)) else 0
                    else:
                        val = 0
                    out_states.append(str(val))
                else:
                    out_states.append('?')

            print(f"ID:{bloc9_id} {' '.join(out_states)}")
    except KeyboardInterrupt:
        print("\n[listen] Stopping and shutting down bus")
    finally:
        bus.shutdown()


if __name__ == '__main__':
    import sys
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    listen(iface)
