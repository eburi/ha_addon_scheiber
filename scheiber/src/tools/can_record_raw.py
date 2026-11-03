#!/usr/bin/env python3
"""Minimal candump -L style recorder using raw AF_CAN sockets (all interfaces)."""

import os
import socket
import struct
import sys
import time

out = sys.argv[1]
CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000
s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind(("",))  # all interfaces
f = open(out, "a", buffering=1)
f.write(
    f"# start {time.time():.6f} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
)
n = 0
while True:
    data, addr = s.recvfrom(16)
    ts = time.time()
    can_id, dlc = struct.unpack("<IB3x", data[:8])
    payload = data[8 : 8 + dlc]
    if can_id & CAN_ERR_FLAG:
        idstr = f"ERR{can_id & 0x1FFFFFFF:08X}"
    elif can_id & CAN_EFF_FLAG:
        idstr = f"{can_id & 0x1FFFFFFF:08X}"
    else:
        idstr = f"{can_id & 0x7FF:03X}"
    rtr = "R" if can_id & CAN_RTR_FLAG else ""
    f.write(f"({ts:.6f}) {addr[0]} {idstr}#{rtr}{payload.hex().upper()}\n")
    n += 1
