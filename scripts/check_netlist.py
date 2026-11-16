#!/usr/bin/env python3
"""Compare a KiCad-exported XML netlist with design.py (schematic or board side)."""
import sys, xml.etree.ElementTree as ET
import design
want = {n: set(c) for n, c in design.nets().items()}
root = ET.parse(sys.argv[1]).getroot()
got = {}
for net in root.iter("net"):
    nodes = {(n.get("ref"), n.get("pin")) for n in net.iter("node")}
    got[net.get("name").lstrip("/")] = nodes
bad = 0
for n, c in want.items():
    if got.get(n) != c:
        bad += 1; print("MISMATCH", n, "want", sorted(c), "got", sorted(got.get(n, [])))
for n, c in got.items():
    if n not in want and len(c) > 1:
        bad += 1; print("EXTRA NET", n, sorted(c))
print("netlist OK" if not bad else "%d problems" % bad)
sys.exit(1 if bad else 0)
