#!/usr/bin/python3
"""Generate the custom footprints and place the MIDI card PCB (KiCad 7 pcbnew API).

Run with the system Python that ships KiCad's `pcbnew` module:
    /usr/bin/python3 scripts/gen_pcb.py place     # footprints, outline, art -> midicard_unrouted.kicad_pcb
    /usr/bin/python3 scripts/gen_pcb.py finish    # after routing: zones, fill, DRC
Coordinates below are card coordinates in mm: x from the USB tip (0) to the
right edge (85), y from the top edge (0) down to 55.
"""
import math
import os
import shutil
import sys
import uuid

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import design  # noqa: E402

HW = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hardware"))
LIB = os.path.join(HW, "lib", "midicard.pretty")
KFP = "/usr/share/kicad/footprints"
OX, OY = 100.0, 60.0          # where card (0,0) sits on the KiCad page

# ---------------------------------------------------------------- card geometry
CARD_W, CARD_H = 85.0, 55.0
BODY_X = 12.0                  # card body starts here; the USB tongue is x 0..12
PLUG_Y0, PLUG_Y1 = 5.0, 17.0   # 12 mm wide tongue
PLUG_C = (PLUG_Y0 + PLUG_Y1) / 2
CORNER_R = 3.0

# keys
KX0, KW, KGAP = 14.5, 8.5, 0.7   # first white key left edge, white pitch, gap
BW = 4.6                         # black key width
KY0, KYB, KY1 = 23.0, 39.0, 52.5  # key top, black key bottom, white key bottom
BLACK_AT = {1, 2, 4, 5, 6}       # boundary index (between white k-1 and k) with a black key
R_ROW_Y = 20.7                   # 1M resistor row


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def uid(*key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "midicard/" + "/".join(map(str, key))))


# ---------------------------------------------------------------- footprints
def key_geometry():
    """Return list of (net name, centre x, polygon in card coords) left to right."""
    out = []
    whites = [k for k in design.KEYS if not k[2]]
    blacks = [k for k in design.KEYS if k[2]]
    wi = bi = 0
    order = []
    for k in design.KEYS:
        order.append(k)
    w_index = {}
    for i, k in enumerate(whites):
        w_index[k[0]] = i
    b_bounds = sorted(BLACK_AT)
    for k in design.KEYS:
        name = k[0]
        if not k[2]:
            i = w_index[name]
            xl, xr = KX0 + i * KW + KGAP / 2, KX0 + (i + 1) * KW - KGAP / 2
            xl2 = KX0 + i * KW + BW / 2 + KGAP if i in BLACK_AT else xl
            xr2 = KX0 + (i + 1) * KW - BW / 2 - KGAP if (i + 1) in BLACK_AT else xr
            yn = KYB + KGAP
            poly = [(xl2, KY0), (xr2, KY0), (xr2, yn), (xr, yn), (xr, KY1), (xl, KY1), (xl, yn), (xl2, yn)]
            # drop duplicate points where there is no notch
            clean = []
            for p in poly:
                if not clean or (abs(clean[-1][0] - p[0]) > 1e-6 or abs(clean[-1][1] - p[1]) > 1e-6):
                    clean.append(p)
            out.append((design.key_net(name), (xl2 + xr2) / 2, clean))
        else:
            b = b_bounds[bi]
            bi += 1
            xc = KX0 + b * KW
            poly = [(xc - BW / 2, KY0), (xc + BW / 2, KY0), (xc + BW / 2, KYB), (xc - BW / 2, KYB)]
            out.append((design.key_net(name), xc, poly))
    return out


def write_key_footprints():
    keys = key_geometry()
    for net, xc, poly in keys:
        name = "TouchKey_" + net
        pts = " ".join("(xy %.4f %.4f)" % (x - xc, y - KY0) for x, y in poly)
        xs = [p[0] - xc for p in poly]
        ys = [p[1] - KY0 for p in poly]
        txt = f'''(footprint "{name}" (version 20221018) (generator midicard_gen)
  (layer "F.Cu")
  (descr "Capacitive touch key {net}, bare ENIG copper, origin at the top centre")
  (attr smd exclude_from_pos_files exclude_from_bom allow_missing_courtyard)
  (fp_text reference "REF**" (at 0 -1.2) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (fp_text value "{name}" (at 0 {max(ys) + 1:.2f}) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (pad "1" smd custom (at 0 1) (size 0.8 0.8) (layers "F.Cu" "F.Mask")
    (options (clearance outline) (anchor rect))
    (primitives (gr_poly (pts {" ".join("(xy %.4f %.4f)" % (x - xc, y - KY0 - 1) for x, y in poly)}) (width 0) (fill yes)))
  )
)
'''
        open(os.path.join(LIB, name + ".kicad_mod"), "w").write(txt)
    return keys


def write_usb_footprint():
    # Dimensions per USB 2.0 spec standard-A plug (via qeda usb-a-plug):
    # pins 1/4 at +-3.5 mm, 2/3 at +-1.0 mm, all contacts end 8.65 mm from the tip,
    # VBUS/GND start 1.24 mm from the tip (mate first), data 2.24 mm.
    # Footprint origin = centre of the tip edge, +x points into the card.
    # Contacts on top, tip pointing away from you: VBUS, D-, D+, GND from left to right.
    # With the tip pointing to -x on the board, "left" is +y.
    pads = [("1", +3.5, 1.24, 1.4), ("2", +1.0, 2.24, 1.1), ("3", -1.0, 2.24, 1.1), ("4", -3.5, 1.24, 1.4)]
    lines = []
    for num, y, x0, w in pads:
        x1 = 8.65
        lines.append(f'  (pad "{num}" smd roundrect (at {(x0 + x1) / 2:.3f} {y:.3f}) (size {x1 - x0:.3f} {w:.3f}) '
                     f'(layers "F.Cu" "F.Mask") (roundrect_rratio 0.15))')
    txt = '''(footprint "USB_A_PCB_Plug" (version 20221018) (generator midicard_gen)
  (layer "F.Cu")
  (descr "USB 2.0 standard-A plug formed by a PCB edge, contacts on the top side. Total stack thickness must be 2.0-2.2 mm (shim under 0.8 mm board).")
  (tags "USB A plug PCB edge")
  (attr smd exclude_from_pos_files exclude_from_bom)
  (fp_text reference "REF**" (at 5 -7.2) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (fp_text value "USB_A_PCB_Plug" (at 5 7.2) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (fp_line (start 0 -6) (end 12 -6) (stroke (width 0.1) (type default)) (layer "F.Fab"))
  (fp_line (start 0 6) (end 12 6) (stroke (width 0.1) (type default)) (layer "F.Fab"))
  (fp_line (start 0 -6) (end 0 6) (stroke (width 0.1) (type default)) (layer "F.Fab"))
  (fp_text user "VBUS" (at 10.6 3.5) (layer "F.Fab") (effects (font (size 0.6 0.6) (thickness 0.1))))
  (fp_text user "GND" (at 10.6 -3.5) (layer "F.Fab") (effects (font (size 0.6 0.6) (thickness 0.1))))
''' + "\n".join(lines) + "\n)\n"
    open(os.path.join(LIB, "USB_A_PCB_Plug.kicad_mod"), "w").write(txt)


def write_qfn_footprint():
    src = os.path.join(KFP, "Package_DFN_QFN.pretty", "QFN-28-1EP_4x4mm_P0.4mm_EP2.6x2.6mm.kicad_mod")
    shutil.copy(src, os.path.join(LIB, "QFN-28-1EP_4x4mm_P0.4mm_EP2.6x2.6mm.kicad_mod"))


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = LIB if lib == "midicard" else os.path.join(KFP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    assert fp is not None, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


# ---------------------------------------------------------------- placement
def placements(keys):
    pos = {
        "J1": (0.0, PLUG_C, 0, "F"),
        "U1": (21.0, 11.0, 90, "F"),
        "C1": (18.9, 14.3, 180, "F"),
        "C2": (16.6, 15.6, 0, "F"),
        "R14": (16.6, 5.0, 180, "F"),
        "D1": (14.6, 2.2, 0, "F"),
        "R15": (16.2, 18.4, 90, "F"),
        "JP1": (14.1, 19.6, 90, "F"),
        "BZ1": (77.0, 9.6, 0, "F"),
        "TP1": (26.0, 3.0, 0, "B"),
        "TP2": (28.54, 3.0, 0, "B"),
        "TP3": (31.08, 3.0, 0, "B"),
        "TP4": (33.62, 3.0, 0, "B"),
    }
    for i, (net, xc, poly) in enumerate(keys):
        pos["R%d" % (i + 1)] = (xc, R_ROW_Y, 90, "F")
        pos["K%d" % (i + 1)] = (xc, KY0, 0, "F")
    return pos


def add_outline(board):
    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(*a))
        s.SetEnd(pt(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(pt(*start), pt(*mid), pt(*end))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    r, c = CORNER_R, CORNER_R * (1 - math.sqrt(0.5))
    ch = 0.5
    W, H, X = CARD_W, CARD_H, BODY_X
    seg((0, PLUG_Y0 + ch), (0, PLUG_Y1 - ch))
    seg((0, PLUG_Y1 - ch), (ch, PLUG_Y1))
    seg((ch, PLUG_Y1), (X, PLUG_Y1))
    seg((X, PLUG_Y1), (X, H - r))
    arc((X, H - r), (X + c, H - c), (X + r, H))
    seg((X + r, H), (W - r, H))
    arc((W - r, H), (W - c, H - c), (W, H - r))
    seg((W, H - r), (W, r))
    arc((W, r), (W - c, c), (W - r, 0))
    seg((W - r, 0), (X + r, 0))
    arc((X + r, 0), (X + c, c), (X, r))
    seg((X, r), (X, PLUG_Y0))
    seg((X, PLUG_Y0), (ch, PLUG_Y0))
    seg((ch, PLUG_Y0), (0, PLUG_Y0 + ch))


def add_text(board, s, x, y, size, layer, thick=None, bold=False, justify=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick if thick else size * 0.15))
    t.SetBold(bold)
    if layer in (pcbnew.B_SilkS, pcbnew.B_Cu, pcbnew.B_Mask):
        t.SetMirrored(True)
    if justify == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    board.Add(t)
    return t


def add_rule_area(board, layers, poly, tracks=True, vias=True, pour=False, name=""):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowCopperPour(pour)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetZoneName(name)
    o = z.Outline()
    o.NewOutline()
    for x, y in poly:
        o.Append(pt(x, y))
    board.Add(z)


def setup_rules(board):
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_ViasMinDrill = mm(0.3)
    ds.m_MinClearance = mm(0.15)
    ds.m_MinSilkTextHeight = mm(0.6)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.25)
    ds.SetBoardThickness(mm(0.8))
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(mm(0.15))
    nc.SetTrackWidth(mm(0.2))
    nc.SetViaDiameter(mm(0.6))
    nc.SetViaDrill(mm(0.3))


def place():
    os.makedirs(LIB, exist_ok=True)
    keys = write_key_footprints()
    write_usb_footprint()
    write_qfn_footprint()

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    setup_rules(board)

    nets = {}
    for n in sorted(design.nets()):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni

    pos = placements(keys)
    for p in design.PARTS:
        fp = load_fp(p["footprint"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", p["ref"])))
        if p["lcsc"]:
            fp.SetProperty("LCSC", p["lcsc"])
        board.Add(fp)
        x, y, rot, side = pos[p["ref"]]
        fp.SetPosition(pt(x, y))
        if side == "B":
            fp.Flip(pt(x, y), False)
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            net = p["pins"].get(pad.GetNumber())
            if net:
                pad.SetNet(nets[net])
        # keep reference text small and out of the way
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.7), mm(0.7)))
        fp.Reference().SetTextThickness(mm(0.12))
        fp.Value().SetVisible(False)
        if p["ref"].startswith("K") or p["ref"].startswith("R") and p["ref"] not in ("R14", "R15") or p["ref"] == "J1":
            fp.Reference().SetVisible(False)
        if p["ref"].startswith("TP") or p["ref"] in ("C1", "C2", "R14", "R15", "D1", "U1", "BZ1", "JP1"):
            fp.Reference().SetVisible(False)

    add_outline(board)

    # keep tracks and vias out of the key field (only the key pads live there)
    add_rule_area(board, [pcbnew.F_Cu, pcbnew.B_Cu],
                  [(13.0, KY0 + 0.8), (84.0, KY0 + 0.8), (84.0, 54.0), (13.0, 54.0)], name="keys")
    # nothing on the back of the USB tongue except the ground pour
    add_rule_area(board, [pcbnew.F_Cu], [(0, PLUG_Y0), (8.0, PLUG_Y0), (8.0, PLUG_Y1), (0, PLUG_Y1)],
                  tracks=True, vias=True, name="plug_front")
    add_rule_area(board, [pcbnew.B_Cu], [(0, PLUG_Y0), (11.0, PLUG_Y0), (11.0, PLUG_Y1), (0, PLUG_Y1)],
                  tracks=True, vias=True, name="plug_back")

    art(board)
    out = os.path.join(HW, "midicard_unrouted.kicad_pcb")
    board.Save(out)
    print("placed ->", out)


def art(board):
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    # front: name strip between the MCU and the buzzer
    add_text(board, "YOUR NAME", 50.0, 6.6, 3.2, F, bold=True)
    add_text(board, "your title  |  your company", 50.0, 11.2, 1.4, F)
    add_text(board, "USB MIDI KEYBOARD  -  plug in, play, no drivers", 49.0, 15.6, 1.0, F)
    add_text(board, "BOOT", 14.1, 17.6, 0.6, F)
    # back: contact block + how-to
    add_text(board, "YOUR NAME", 48.5, 27.0, 3.0, B, bold=True)
    add_text(board, "you@example.com", 48.5, 32.2, 1.8, B)
    add_text(board, "+00 000 000 000", 48.5, 35.6, 1.8, B)
    add_text(board, "example.com", 48.5, 39.0, 1.8, B)
    add_text(board, "Plug me into a USB-A port. I show up as a MIDI keyboard", 48.5, 43.8, 1.1, B)
    add_text(board, "(class compliant: macOS, Windows, Linux, iPad, Android).", 48.5, 45.8, 1.1, B)
    add_text(board, "Touch the gold keys. Not connected to a computer? I beep.", 48.5, 47.8, 1.1, B)
    add_text(board, "Firmware + KiCad files: github.com/your-handle/midicard", 48.5, 51.2, 1.0, B)
    add_text(board, "5V   DIO  CLK  GND", 29.8, 5.2, 0.8, B)
    add_text(board, "SHIM HERE", 6.0, PLUG_C, 1.0, B)


def finish(path_in, path_out):
    board = pcbnew.LoadBoard(path_in)
    gnd = board.FindNet("GND")
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.4))
        z.SetZoneName("GND_" + ("F" if layer == pcbnew.F_Cu else "B"))
        o = z.Outline()
        o.NewOutline()
        # pour only in the electronics strip (and behind the plug on the back),
        # not under or around the keys
        top = 21.9
        if layer == pcbnew.B_Cu:
            poly = [(0, PLUG_Y0), (BODY_X, PLUG_Y0), (BODY_X, 0), (CARD_W, 0), (CARD_W, top),
                    (BODY_X, top), (BODY_X, PLUG_Y1), (0, PLUG_Y1)]
        else:
            poly = [(BODY_X, 0), (CARD_W, 0), (CARD_W, top), (BODY_X, top)]
        for x, y in poly:
            o.Append(pt(x, y))
        board.Add(z)
    # the plug keepouts only guided the router; the contact stubs start inside them
    for z in list(board.Zones()):
        if z.GetIsRuleArea() and z.GetZoneName().startswith("plug"):
            board.Remove(z)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(path_out)
    rpt = path_out.replace(".kicad_pcb", "-drc.rpt")
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    print("finished ->", path_out, "DRC ->", rpt)


if __name__ == "__main__":
    if sys.argv[1] == "place":
        place()
    elif sys.argv[1] == "finish":
        finish(sys.argv[2], sys.argv[3])
