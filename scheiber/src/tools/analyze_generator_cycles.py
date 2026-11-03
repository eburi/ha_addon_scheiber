#!/usr/bin/env python3
"""Build per-cycle event offset table for node 0B88 from candump-L logs."""

import re
import sys

rx = re.compile(r"\((\d+\.\d+)\) can1 (0[0-9A-F]{3})0B88#([0-9A-F]*)")
events = []
for f in sys.argv[1:]:
    for line in open(f):
        m = rx.match(line)
        if not m:
            continue
        ts, pre, pl = float(m.group(1)), m.group(2), m.group(3)
        if pre in ("0246", "0216", "0214", "0244"):
            events.append((ts, pre, pl))
        elif pre == "0204":
            events.append((ts, pre, pl))
events.sort()
# find command events
cmds = [(i, e) for i, e in enumerate(events) if e[1] == "0246"]
last04 = None
for i, (t0, _, cmd) in cmds:
    kind = {"01": "START", "02": "STOP"}.get(cmd, cmd)
    print(f"\n=== {kind} cmd at {t0:.3f}")
    # events within -2 .. +70 s
    genv_prev = None
    first_ac = None
    zero_ac = None
    for ts, pre, pl in events:
        if ts < t0 - 1 or ts > t0 + 70:
            continue
        if pre == "0204":
            gv = int(pl[0:4], 16)
            ghz = int(pl[4:8], 16)
            if kind == "START" and first_ac is None and gv > 0:
                first_ac = ts
                print(f"  +{ts-t0:6.2f}  0204 gen AC first nonzero V={gv} Hz={ghz}")
            if (
                kind == "START"
                and gv >= 200
                and genv_prev is not None
                and genv_prev < 200
            ):
                print(f"  +{ts-t0:6.2f}  0204 gen AC reached V={gv} Hz={ghz}")
            if kind == "STOP" and zero_ac is None and gv == 0 and ts > t0:
                zero_ac = ts
                print(f"  +{ts-t0:6.2f}  0204 gen AC zero")
            genv_prev = gv
        else:
            print(f"  +{ts-t0:6.2f}  {pre} {pl}")
