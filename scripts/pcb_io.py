#!/usr/bin/python3
"""Bridge between KiCad's pcbnew (system Python) and the grid router (any Python 3 + numpy/shapely).

    /usr/bin/python3 pcb_io.py export board.kicad_pcb geometry.json
    /usr/bin/python3 pcb_io.py import board.kicad_pcb routes.json out.kicad_pcb
"""
import json
import sys

import pcbnew

OX, OY = 100.0, 60.0


def mm(v):
    return pcbnew.ToMM(v)


def export(board_path, out):
    b = pcbnew.LoadBoard(board_path)
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            layers = []
            if p.IsOnLayer(pcbnew.F_Cu):
                layers.append("F")
            if p.IsOnLayer(pcbnew.B_Cu):
                layers.append("B")
            for L in layers:
                lid = pcbnew.F_Cu if L == "F" else pcbnew.B_Cu
                ps = p.GetEffectivePolygon()
                polys = []
                for i in range(ps.OutlineCount()):
                    o = ps.Outline(i)
                    polys.append([(mm(o.CPoint(j).x) - OX, mm(o.CPoint(j).y) - OY) for j in range(o.PointCount())])
                pads.append(dict(ref=fp.GetReference(), num=p.GetNumber(), net=p.GetNetname(), layer=L,
                                 x=mm(p.GetPosition().x) - OX, y=mm(p.GetPosition().y) - OY, polys=polys))
    keepouts = []
    for z in b.Zones():
        if z.GetIsRuleArea():
            o = z.Outline().Outline(0)
            pts = [(mm(o.CPoint(j).x) - OX, mm(o.CPoint(j).y) - OY) for j in range(o.PointCount())]
            layers = [L for L, lid in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)) if z.IsOnLayer(lid)]
            keepouts.append(dict(name=z.GetZoneName(), layers=layers, poly=pts))
    edges = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(edges)
    o = edges.Outline(0)
    outline = [(mm(o.CPoint(j).x) - OX, mm(o.CPoint(j).y) - OY) for j in range(o.PointCount())]
    json.dump(dict(pads=pads, keepouts=keepouts, outline=outline), open(out, "w"), indent=1)
    print("exported", len(pads), "pads")


def do_import(board_path, routes, out):
    b = pcbnew.LoadBoard(board_path)
    r = json.load(open(routes))
    nets = {n: b.FindNet(n) for n in {s["net"] for s in r["segments"]} | {v["net"] for v in r["vias"]}}
    for s in r["segments"]:
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(s["x1"] + OX), pcbnew.FromMM(s["y1"] + OY)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(s["x2"] + OX), pcbnew.FromMM(s["y2"] + OY)))
        t.SetWidth(pcbnew.FromMM(s["w"]))
        t.SetLayer(pcbnew.F_Cu if s["layer"] == "F" else pcbnew.B_Cu)
        t.SetNet(nets[s["net"]])
        b.Add(t)
    for v in r["vias"]:
        t = pcbnew.PCB_VIA(b)
        t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(v["x"] + OX), pcbnew.FromMM(v["y"] + OY)))
        t.SetWidth(pcbnew.FromMM(v["d"]))
        t.SetDrill(pcbnew.FromMM(v["drill"]))
        t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        t.SetNet(nets[v["net"]])
        b.Add(t)
    b.Save(out)
    print("imported", len(r["segments"]), "segments,", len(r["vias"]), "vias")


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export(sys.argv[2], sys.argv[3])
    else:
        do_import(sys.argv[2], sys.argv[3], sys.argv[4])
