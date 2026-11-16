#!/usr/bin/env python3
"""Generate hardware/lib/midicard.kicad_sym and hardware/midicard.kicad_sch (KiCad 7+).

The schematic is label based: every pin gets a short wire stub and a net label
(or a power symbol), so the connectivity comes straight from design.py.
"""
import math
import os
import re
import uuid

import design

HW = os.path.join(os.path.dirname(__file__), "..", "hardware")
KICAD_SYM = "/usr/share/kicad/symbols"
PROJECT = "midicard"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "midicard-root"))


def uid(*key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "midicard/" + "/".join(map(str, key))))


# ----------------------------------------------------------------- s-expr helpers
def extract_block(text, start):
    depth = 0
    i = start
    in_str = False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


def lib_symbol(lib_id, libfile=None):
    lib, name = lib_id.split(":")
    path = libfile or os.path.join(KICAD_SYM, lib + ".kicad_sym")
    text = open(path).read()
    i = text.find('(symbol "%s"' % name)
    assert i >= 0, lib_id
    block = extract_block(text, i)
    if "(extends" in block:
        raise ValueError("extends not supported: " + lib_id)
    return block.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)


def pins_of(block):
    """Return {number: (x, y, angle)} from a symbol block (lib coords, y up)."""
    out = {}
    for m in re.finditer(r'\(pin \w+ \w+ \(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number "([^"]+)"', block, re.S):
        out[m.group(4)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return out


# ----------------------------------------------------------------- custom symbols
def pin_line(num, name, x, y, ang, etype="bidirectional", length=2.54, hide=False):
    return ('      (pin %s line (at %.2f %.2f %d) (length %.2f)%s\n'
            '        (name "%s" (effects (font (size 1.27 1.27))))\n'
            '        (number "%s" (effects (font (size 1.27 1.27))))\n      )\n'
            % (etype, x, y, ang, length, " hide" if hide else "", name, num))


MCU_LEFT = [2, 26, 27, 25, 24, 23, 20, 21, 4, 3, 28, 1, 18, 19, 22]
MCU_RIGHT = [k[3] for k in design.KEYS]


def mcu_symbol():
    w = 30.48
    n = max(len(MCU_LEFT), len(MCU_RIGHT))
    top = (n // 2) * 2.54 + 2.54
    bot = top - (n + 1) * 2.54
    s = ['(symbol "CH32X035G8U6" (pin_names (offset 1.016)) (in_bom yes) (on_board yes)\n',
         '    (property "Reference" "U" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (justify left)))\n' % (-w / 2, top + 1.27),
         '    (property "Value" "CH32X035G8U6" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (justify left)))\n' % (-w / 2, bot - 3.81),
         '    (property "Footprint" "midicard:QFN-28-1EP_4x4mm_P0.4mm_EP2.6x2.6mm" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (property "Datasheet" "https://www.wch-ic.com/products/CH32X035.html" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (property "ki_description" "WCH CH32X035 RISC-V MCU, USB FS device/PD, 62K flash, QFN-28" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (symbol "CH32X035G8U6_0_1"\n',
         '      (rectangle (start %.2f %.2f) (end %.2f %.2f) (stroke (width 0.254) (type default)) (fill (type background)))\n' % (-w / 2, top, w / 2, bot),
         '    )\n    (symbol "CH32X035G8U6_1_1"\n']
    for i, p in enumerate(MCU_LEFT):
        name, net = design.MCU_PINS.get(p, ("?", None))
        et = "power_in" if p == 2 else "bidirectional"
        s.append(pin_line(p, name, -w / 2 - 2.54, top - 2.54 * (i + 1), 0, et))
    for i, p in enumerate(MCU_RIGHT):
        name, net = design.MCU_PINS[p]
        s.append(pin_line(p, name, w / 2 + 2.54, top - 2.54 * (i + 1), 180))
    s.append(pin_line(29, "GND", 0, bot - 2.54, 90, "power_in"))
    s.append('    )\n  )\n')
    return "".join(s)


def usb_symbol():
    s = ['(symbol "USB_A_Plug" (pin_names (offset 1.016)) (in_bom no) (on_board yes)\n',
         '    (property "Reference" "J" (at -5.08 7.62 0) (effects (font (size 1.27 1.27)) (justify left)))\n',
         '    (property "Value" "USB_A_PCB_Plug" (at -5.08 -7.62 0) (effects (font (size 1.27 1.27)) (justify left)))\n',
         '    (property "Footprint" "midicard:USB_A_PCB_Plug" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (property "ki_description" "USB 2.0 type A plug made from the PCB edge" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n',
         '    (symbol "USB_A_Plug_0_1"\n',
         '      (rectangle (start -5.08 6.35) (end 5.08 -6.35) (stroke (width 0.254) (type default)) (fill (type background)))\n',
         '    )\n    (symbol "USB_A_Plug_1_1"\n']
    for i, (n, name, et) in enumerate([(1, "VBUS", "power_out"), (2, "D-", "bidirectional"),
                                       (3, "D+", "bidirectional"), (4, "GND", "power_out")]):
        s.append(pin_line(n, name, 7.62, 3.81 - 2.54 * i, 180, et))
    s.append('    )\n  )\n')
    return "".join(s)


def write_symbol_lib():
    path = os.path.join(HW, "lib", "midicard.kicad_sym")
    with open(path, "w") as f:
        f.write('(kicad_symbol_lib (version 20220914) (generator midicard_gen)\n  ')
        f.write(mcu_symbol())
        f.write("  ")
        f.write(usb_symbol())
        f.write(")\n")
    return path


# ----------------------------------------------------------------- schematic
class Sch:
    def __init__(self):
        self.items = []
        self.libs = {}
        self.pwr_n = 0

    def need(self, lib_id):
        if lib_id not in self.libs:
            libfile = None
            if lib_id.startswith("midicard:"):
                libfile = os.path.join(HW, "lib", "midicard.kicad_sym")
            self.libs[lib_id] = lib_symbol(lib_id, libfile)
        return self.libs[lib_id]

    def symbol(self, lib_id, ref, value, x, y, rot=0, footprint="", props=None, unit_pins=None,
               in_bom=True, on_board=True, dnp=False, hide_ref=False, hide_val=False):
        block = self.need(lib_id)
        key = uid("sym", ref)
        props = props or {}
        out = ['  (symbol (lib_id "%s") (at %.2f %.2f %d) (unit 1)\n' % (lib_id, x, y, rot),
               '    (in_bom %s) (on_board %s) (dnp %s)\n' % ("yes" if in_bom else "no",
                                                           "yes" if on_board else "no",
                                                           "yes" if dnp else "no"),
               '    (uuid %s)\n' % key]
        fields = [("Reference", ref, hide_ref, 0), ("Value", value, hide_val, 1),
                  ("Footprint", footprint, True, 2), ("Datasheet", "~", True, 3)]
        for k, v in props.items():
            fields.append((k, v, True, len(fields)))
        a = math.radians(rot)
        for i, (k, v, hide, _) in enumerate(fields):
            m = re.search(r'\(property "%s" "[^"]*" \(at ([-\d.]+) ([-\d.]+) (\d+)\)' % k, block)
            if i < 2 and rot in (90, 270):
                fx, fy, pa = x + (2.0 if rot == 270 else 0), y + (-2.3 if i == 0 else 2.8), 90
            elif m and i < 2:
                px, py, pa = float(m.group(1)), float(m.group(2)), int(m.group(3))
                if rot in (90, 270) and "R" in lib_id.split(":")[1][:1] and pa == 90:
                    px, py = py, px
                px, py = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
                pa = (pa + rot) % 180
                fx, fy = x + px, y - py
            else:
                fx, fy, pa = x, y, 0
            out.append('    (property "%s" "%s" (at %.2f %.2f %d) (effects (font (size 1.27 1.27))%s))\n'
                       % (k, v, fx, fy, pa, " hide" if hide else ""))
        for num in pins_of(block):
            out.append('    (pin "%s" (uuid %s))\n' % (num, uid("pin", ref, num)))
        out.append('    (instances (project "%s" (path "/%s" (reference "%s") (unit 1))))\n'
                   % (PROJECT, ROOT_UUID, ref))
        out.append('  )\n')
        self.items.append("".join(out))
        return pins_of(block)

    def wire(self, x1, y1, x2, y2):
        self.items.append('  (wire (pts (xy %.2f %.2f) (xy %.2f %.2f)) (stroke (width 0) (type default)) (uuid %s))\n'
                          % (x1, y1, x2, y2, uid("w", x1, y1, x2, y2)))

    def label(self, net, x, y, ang):
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
        self.items.append('  (label "%s" (at %.2f %.2f %d) (fields_autoplaced) (effects (font (size 1.27 1.27)) (justify %s)) (uuid %s))\n'
                          % (net, x, y, ang, just, uid("l", net, x, y)))

    def power(self, net, x, y, out_ang):
        """Power symbol whose graphic points along out_ang (0=right,90=up,180=left,270=down)."""
        self.pwr_n += 1
        if net == "GND":
            rot = {270: 0, 90: 180, 180: 270, 0: 90}[out_ang]
        elif net == "PWR_FLAG":
            rot = {90: 0, 270: 180, 180: 90, 0: 270}[out_ang]
        else:
            rot = {90: 0, 270: 180, 180: 90, 0: 270}[out_ang]
        lib = "power:" + net
        ref = "#PWR%02d" % self.pwr_n if net != "PWR_FLAG" else "#FLG%02d" % self.pwr_n
        self.symbol(lib, ref, net, x, y, rot, in_bom=False, on_board=True, hide_ref=True)

    def flag(self, x, y, up=True):
        self.pwr_n += 1
        self.symbol("power:PWR_FLAG", "#FLG%02d" % self.pwr_n, "PWR_FLAG", x, y, 0 if up else 180,
                    in_bom=False, hide_ref=True)

    def text(self, s, x, y, size=1.27):
        self.items.append('  (text "%s" (at %.2f %.2f 0) (effects (font (size %.2f %.2f)) (justify left bottom)) (uuid %s))\n'
                          % (s.replace('"', '\\"'), x, y, size, size, uid("t", s)))

    def place(self, p, x, y, rot=0, stub=2.54, flags=()):
        """Place a design part and hang a label / power symbol on every pin."""
        props = {}
        if p["lcsc"]:
            props["LCSC"] = p["lcsc"]
        if p["desc"]:
            props["Description"] = p["desc"]
        pins = self.symbol(p["lib_id"], p["ref"], p["value"], x, y, rot, p["footprint"], props,
                           in_bom=bool(p["lcsc"]), dnp=p["dnp"])
        for num, (px, py, pang) in pins.items():
            net = p["pins"].get(num)
            a = math.radians(rot)
            rx = px * math.cos(a) - py * math.sin(a)
            ry = px * math.sin(a) + py * math.cos(a)
            sx, sy = x + rx, y - ry
            out = (pang + 180 + rot) % 360
            dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[out]
            ex, ey = sx + dx * stub, sy + dy * stub
            if net is None:
                self.items.append('  (no_connect (at %.2f %.2f) (uuid %s))\n' % (sx, sy, uid("nc", p["ref"], num)))
                continue
            self.wire(sx, sy, ex, ey)
            if net in ("GND", "VBUS"):
                self.power(net, ex, ey, out)
                if (p["ref"], num) in flags:
                    self.flag(ex, ey, up=(net == "VBUS"))
            else:
                self.label(net, ex, ey, out)

    def write(self, path):
        with open(path, "w") as f:
            f.write('(kicad_sch (version 20230121) (generator eeschema)\n\n')
            f.write('  (uuid %s)\n\n  (paper "A4")\n\n' % ROOT_UUID)
            f.write('  (title_block\n    (title "USB MIDI touch keyboard business card")\n'
                    '    (date "2026-11-16")\n    (rev "1.0")\n'
                    '    (comment 1 "CH32X035G8U6 bus powered from USB-A PCB plug, 13 RC touch keys")\n'
                    '    (comment 2 "Generated by scripts/gen_schematic.py from scripts/design.py")\n  )\n\n')
            f.write('  (lib_symbols\n')
            for b in self.libs.values():
                f.write('    ' + b.replace("\n", "\n  ") + '\n')
            f.write('  )\n\n')
            for it in self.items:
                f.write(it)
            f.write('\n  (sheet_instances (path "/" (page "1")))\n)\n')


def main():
    write_symbol_lib()
    parts = {p["ref"]: p for p in design.PARTS}
    s = Sch()
    G = 2.54

    s.text("USB plug (PCB edge). Pin order checked: contacts up, tip away = VBUS, D-, D+, GND left to right.", 20.32, 25.4)
    s.place(parts["J1"], 30.48, 45.72, stub=7.62, flags={("J1", "1"), ("J1", "4")})

    s.text("Supply: VDD runs straight from USB 5 V (CH32X035 allows 2.0-5.5 V, USB 3.0-5.3 V)", 20.32, 66.04)
    s.place(parts["C1"], 33.02, 78.74)
    s.place(parts["C2"], 45.72, 78.74)

    s.text("Status LED", 20.32, 99.06)
    s.place(parts["R14"], 33.02, 111.76)
    s.place(parts["D1"], 45.72, 111.76, rot=90)

    s.text("Piezo, driven in antiphase by TIM1 CH1/CH2 (10 Vpp)", 20.32, 132.08)
    s.place(parts["BZ1"], 33.02, 144.78)

    s.text("BOOT: bridge JP1 while plugging in -> PC17 high -> WCH USB bootloader", 20.32, 162.56)
    s.place(parts["JP1"], 33.02, 172.72)
    s.place(parts["R15"], 50.8, 172.72, rot=90)

    s.text("Programming pads on the back (WCH-LinkE, SWD)", 20.32, 185.42)
    for i, ref in enumerate(("TP1", "TP2", "TP3", "TP4")):
        s.place(parts[ref], 30.48 + i * 12.7, 195.58)

    s.place(parts["U1"], 129.54, 101.6)
    s.text("CH32X035G8U6: native USB FS, internal 48 MHz HSI, no crystal needed", 101.6, 60.96)

    s.text("Touch keys: SEND rises, each key charges through 1M; a finger adds capacitance and delays the edge.", 172.72, 30.48)
    s.text("All 13 keys are timed in parallel by reading GPIOA/GPIOB in a tight loop.", 172.72, 33.02)
    for i, (n, off, blk, pin, port) in enumerate(design.KEYS):
        y = 40.64 + i * 8.89
        s.place(parts["R%d" % (i + 1)], 200.66, y, rot=90)
        s.place(parts["K%d" % (i + 1)], 233.68, y, rot=270)
    s.write(os.path.join(HW, PROJECT + ".kicad_sch"))
    print("schematic written")


if __name__ == "__main__":
    main()
