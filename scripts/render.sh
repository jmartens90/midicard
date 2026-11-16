#!/bin/sh
# render.sh board.kicad_pcb outprefix : front/back PNG previews via kicad-cli SVG
set -e
B=$1; O=$2
kicad-cli pcb export svg --exclude-drawing-sheet --page-size-mode 2 -l F.Cu,F.Mask,F.SilkS,Edge.Cuts -o $O-front.svg $B >/dev/null
kicad-cli pcb export svg --exclude-drawing-sheet --page-size-mode 2 -m -l B.Cu,B.SilkS,Edge.Cuts -o $O-back.svg $B >/dev/null
for s in front back; do python3 -c "import cairosvg,sys; cairosvg.svg2png(url='$O-$s.svg', write_to='$O-$s.png', output_width=1600, background_color='white')"; done
