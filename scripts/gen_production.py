#!/usr/bin/env python3
"""Write JLCPCB BOM and CPL from design.py and KiCad's position export.

    kicad-cli pcb export pos --format csv --units mm --side both -o pos.csv hardware/midicard.kicad_pcb
    python3 scripts/gen_production.py pos.csv hardware/production
"""
import csv
import os
import sys

import design

# Rotation corrections between KiCad footprints and JLCPCB's part models.
# None needed for these parts as far as we know; check the JLCPCB 3D preview.
ROT_FIX = {}

pos = {r["Ref"]: r for r in csv.DictReader(open(sys.argv[1]))}
out = sys.argv[2]
parts = [p for p in design.PARTS if p["lcsc"] and not p["dnp"]]

groups = {}
for p in parts:
    key = (p["value"], p["footprint"].split(":")[1], p["lcsc"])
    groups.setdefault(key, []).append(p["ref"])
with open(os.path.join(out, "midicard-bom-jlcpcb.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (val, fp, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
        refs.sort(key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):])))
        w.writerow([val, ",".join(refs), fp, lcsc])

with open(os.path.join(out, "midicard-cpl-jlcpcb.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for p in parts:
        r = pos[p["ref"]]
        rot = (float(r["Rot"]) + ROT_FIX.get(p["footprint"], 0)) % 360
        w.writerow([p["ref"], "%.3fmm" % float(r["PosX"]), "%.3fmm" % float(r["PosY"]),
                    "Top" if r["Side"] == "top" else "Bottom", "%g" % rot])
print("BOM groups:", len(groups), "placements:", len(parts))
