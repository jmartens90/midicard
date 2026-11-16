#!/usr/bin/python3
"""Check that every pad on the board carries the net design.py says it should."""
import os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(__file__))
import design
b = pcbnew.LoadBoard(sys.argv[1])
want = {p["ref"]: p["pins"] for p in design.PARTS}
bad = 0
seen = set()
for fp in b.GetFootprints():
    ref = fp.GetReference(); seen.add(ref)
    for pad in fp.Pads():
        if not pad.GetNumber():
            continue
        w = want[ref].get(pad.GetNumber()) or ""
        if pad.GetNetname() != w:
            bad += 1; print("MISMATCH", ref, pad.GetNumber(), "board", pad.GetNetname(), "design", w)
missing = set(want) - seen
if missing:
    bad += 1; print("missing footprints", missing)
print("board nets OK" if not bad else "%d problems" % bad)
sys.exit(bool(bad))
