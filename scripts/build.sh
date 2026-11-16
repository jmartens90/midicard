#!/bin/sh
# Regenerate everything from scripts/design.py and scripts/gen_pcb.py.
# Needs KiCad 7 (kicad-cli + pcbnew in /usr/bin/python3) and python3 with numpy + shapely.
set -e
cd "$(dirname "$0")"
T=$(mktemp -d)
python3 gen_schematic.py
/usr/bin/python3 gen_pcb.py place
/usr/bin/python3 pcb_io.py export ../hardware/midicard_unrouted.kicad_pcb "$T/geom.json"
python3 router.py "$T/geom.json" "$T/routes.json"
/usr/bin/python3 pcb_io.py import ../hardware/midicard_unrouted.kicad_pcb "$T/routes.json" "$T/routed.kicad_pcb"
cp ../hardware/midicard.kicad_pro "$T/routed.kicad_pro"
/usr/bin/python3 gen_pcb.py finish "$T/routed.kicad_pcb" ../hardware/midicard.kicad_pcb
P=../hardware/production
mkdir -p $P/gerbers
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask --no-x2 -o $P/gerbers/ ../hardware/midicard.kicad_pcb
kicad-cli pcb export drill -o $P/gerbers/ --excellon-separate-th ../hardware/midicard.kicad_pcb
(cd $P/gerbers && rm -f ../midicard-gerbers-jlcpcb.zip && zip -q ../midicard-gerbers-jlcpcb.zip *)
kicad-cli pcb export pos --format csv --units mm --side both -o "$T/pos.csv" ../hardware/midicard.kicad_pcb
python3 gen_production.py "$T/pos.csv" $P
kicad-cli sch export netlist --format kicadxml -o "$T/net.xml" ../hardware/midicard.kicad_sch
python3 check_netlist.py "$T/net.xml"
/usr/bin/python3 check_pcb.py ../hardware/midicard.kicad_pcb
grep -i "unconnected pads" ../hardware/midicard-drc.rpt
