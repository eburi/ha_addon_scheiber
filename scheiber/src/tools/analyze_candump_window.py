#!/usr/bin/env python3
"""Analyze a candump-L style log.
usage: analyze.py can.log [--from T0] [--to T1] [--iface can1] [--diff BASE_T0 BASE_T1]
Prints per-ID: count, rate, distinct payloads, first/last ts, and payload values (up to N).
--diff: compare window against baseline window: new IDs, IDs whose payload set changed.
"""

import argparse
import collections
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--from", dest="t0", type=float, default=0)
ap.add_argument("--to", dest="t1", type=float, default=1e12)
ap.add_argument("--iface", default="can1")
ap.add_argument("--max-payloads", type=int, default=6)
ap.add_argument(
    "--base", nargs=2, type=float, default=None, help="baseline window t0 t1"
)
ap.add_argument(
    "--timeline",
    action="store_true",
    help="print every payload change with ts for changing IDs",
)
ap.add_argument("--ids", default=None, help="comma list of IDs to restrict timeline")
a = ap.parse_args()
rx = re.compile(r"\((\d+\.\d+)\) (\S+) ([0-9A-F]+)#(R?)([0-9A-F]*)")


def load(t0, t1):
    d = collections.OrderedDict()
    seq = []
    for line in open(a.log):
        m = rx.match(line)
        if not m:
            continue
        ts = float(m.group(1))
        if ts < t0 or ts > t1:
            continue
        if m.group(2) != a.iface:
            continue
        cid, pl = m.group(3), m.group(5)
        e = d.setdefault(
            cid, {"n": 0, "pl": collections.Counter(), "first": ts, "last": ts}
        )
        e["n"] += 1
        e["pl"][pl] += 1
        e["last"] = ts
        seq.append((ts, cid, pl))
    return d, seq


win, seq = load(a.t0, a.t1)
span = (
    max(
        1e-9,
        (max(e["last"] for e in win.values()) - min(e["first"] for e in win.values())),
    )
    if win
    else 1
)
base = load(*a.base)[0] if a.base else None
print(
    f"# iface={a.iface} window={a.t0}..{a.t1} ids={len(win)} frames={sum(e['n'] for e in win.values())} span={span:.1f}s"
)
for cid, e in sorted(win.items(), key=lambda kv: -kv[1]["n"]):
    flag = ""
    if base is not None:
        if cid not in base:
            flag = "NEW "
        else:
            newpl = set(e["pl"]) - set(base[cid]["pl"])
            if newpl:
                flag = f"NEWPAYLOAD({len(newpl)}) "
    pls = " | ".join(f"{p}x{c}" for p, c in e["pl"].most_common(a.max_payloads))
    print(
        f"{flag}{cid:>8} n={e['n']:5d} {e['n']/span:6.2f}/s distinct={len(e['pl']):3d} {pls}"
    )
if base is not None:
    gone = set(base) - set(win)
    if gone:
        print("# IDs in baseline but absent in window:", " ".join(sorted(gone)))
if a.timeline:
    ids = (
        set(a.ids.split(","))
        if a.ids
        else {
            cid
            for cid, e in win.items()
            if len(e["pl"]) > 1
            or (base and (cid not in base or set(e["pl"]) - set(base[cid]["pl"])))
        }
    )
    last = {}
    print("# timeline of payload changes for:", " ".join(sorted(ids)))
    for ts, cid, pl in seq:
        if cid in ids and last.get(cid) != pl:
            print(f"{ts:.3f} {cid} {pl}  (prev {last.get(cid)})")
            last[cid] = pl
