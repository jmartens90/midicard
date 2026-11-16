#!/usr/bin/env python3
"""Small two-layer grid router (A*) for the MIDI card.

Reads geometry.json (pcb_io.py export), routes every net in design.py,
writes routes.json for pcb_io.py import. Grid 0.05 mm, 45-degree moves.
"""
import heapq
import json
import math
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import design  # noqa: E402

G = 0.05                       # grid pitch, mm
TRACK = {"default": 0.2, "VBUS": 0.25, "GND": 0.3}
CLR = 0.16                     # clearance used by the router (DRC rule is 0.15)
VIA_D, VIA_DRILL = 0.6, 0.3
EDGE_CLR = 0.5
VIA_COST = 60.0                # in grid steps
LAYERS = ("F", "B")
W, H = 85.0, 55.0
NX, NY = int(W / G) + 1, int(H / G) + 1

XS = np.arange(NX) * G
YS = np.arange(NY) * G
GX, GY = np.meshgrid(XS, YS, indexing="xy")   # shape (NY, NX)


def tw(net):
    return TRACK.get(net, TRACK["default"])


class Grid:
    def __init__(self, geom):
        self.geom = geom
        self.netid = {}
        # owner[layer]: 0 free, >0 net id, -1 blocked
        self.owner = {L: np.zeros((NY, NX), np.int32) for L in LAYERS}
        self.items = {L: [] for L in LAYERS}   # (net, shapely geometry of real copper)
        outline = Polygon(geom["outline"])
        inside = shapely.contains_xy(outline.buffer(-EDGE_CLR), GX, GY)
        for L in LAYERS:
            self.owner[L][~inside] = -1
        for k in geom["keepouts"]:
            poly = Polygon(k["poly"])
            m = shapely.contains_xy(poly, GX, GY)
            for L in k["layers"]:
                self.owner[L][m] = -1
        for p in geom["pads"]:
            nid = self.nid(p["net"]) if p["net"] else -2
            for poly in p["polys"]:
                self.items[p["layer"]].append((nid, Polygon(poly)))

    def nid(self, net):
        if net not in self.netid:
            self.netid[net] = len(self.netid) + 1
        return self.netid[net]

    def blocked_for(self, net, L):
        """Boolean grid: True where a track centre of `net` may NOT go on layer L."""
        n = self.netid[net]
        half = tw(net) / 2
        blk = self.owner[L] == -1
        for nid, g in self.items[L]:
            if nid == n:
                continue
            gb = g.buffer(CLR + half, quad_segs=4)
            x0, y0, x1, y1 = gb.bounds
            i0, i1 = max(int(x0 / G) - 1, 0), min(int(x1 / G) + 2, NX)
            j0, j1 = max(int(y0 / G) - 1, 0), min(int(y1 / G) + 2, NY)
            sub = shapely.contains_xy(gb, GX[j0:j1, i0:i1], GY[j0:j1, i0:i1])
            blk[j0:j1, i0:i1] |= sub
        return blk

    def own_cells(self, net, L):
        n = self.netid[net]
        own = np.zeros((NY, NX), bool)
        for nid, g in self.items[L]:
            if nid != n:
                continue
            x0, y0, x1, y1 = g.bounds
            i0, i1 = max(int(x0 / G) - 1, 0), min(int(x1 / G) + 2, NX)
            j0, j1 = max(int(y0 / G) - 1, 0), min(int(y1 / G) + 2, NY)
            own[j0:j1, i0:i1] |= shapely.contains_xy(g, GX[j0:j1, i0:i1], GY[j0:j1, i0:i1])
        return own


def astar(blk, via_ok, sources, targets, prefer=None):
    """blk/via_ok: dict layer->bool arrays. sources/targets: set of (L, j, i)."""
    tgt = targets
    tj = np.array([t[1] for t in tgt])
    ti = np.array([t[2] for t in tgt])

    def h(j, i):
        d = np.min(np.maximum(np.abs(tj - j), np.abs(ti - i)) + 0.414 * np.minimum(np.abs(tj - j), np.abs(ti - i)))
        return d

    # cheap admissible heuristic: precompute bounding box centre distance
    tset = set(tgt)
    openh = []
    best = {}
    for s in sources:
        best[s] = 0.0
        heapq.heappush(openh, (0.0, 0.0, s, None))
    came = {}
    dirs = [(0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
            (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    cj, ci = float(np.mean(tj)), float(np.mean(ti))
    spread = max(np.ptp(tj), np.ptp(ti)) if len(tj) > 1 else 0
    expanded = 0
    while openh:
        f, g, cur, prev = heapq.heappop(openh)
        if cur in came:
            continue
        came[cur] = prev
        if cur in tset:
            path = [cur]
            while came[path[-1]] is not None:
                path.append(came[path[-1]])
            return path[::-1]
        expanded += 1
        if expanded > 2_500_000:
            print("  search limit hit", file=sys.stderr)
            return None
        L, j, i = cur
        lb = blk[L]
        for dj, di, c in dirs:
            nj, ni = j + dj, i + di
            if nj < 0 or ni < 0 or nj >= NY or ni >= NX or lb[nj, ni]:
                continue
            if dj and di and (lb[j, ni] and lb[nj, i]):
                continue
            cost = c
            if prefer and prefer.get(L):
                cost *= prefer[L]
            nxt = (L, nj, ni)
            ng = g + cost
            if ng < best.get(nxt, 1e18):
                best[nxt] = ng
                hh = max(0.0, max(abs(nj - cj), abs(ni - ci)) - spread)
                heapq.heappush(openh, (ng + hh, ng, nxt, cur))
        if via_ok[j, i]:
            other = "B" if L == "F" else "F"
            nxt = (other, j, i)
            ng = g + VIA_COST
            if ng < best.get(nxt, 1e18):
                best[nxt] = ng
                hh = max(0.0, max(abs(j - cj), abs(i - ci)) - spread)
                heapq.heappush(openh, (ng + hh, ng, nxt, cur))
    return None


def simplify(path):
    """Turn a cell path into segments per layer + via positions."""
    segs, vias = [], []
    run = [path[0]]
    for p in path[1:]:
        if p[0] != run[-1][0]:
            vias.append((p[1], p[2]))
            segs.append(run)
            run = [p]
        else:
            run.append(p)
    segs.append(run)
    out = []
    for run in segs:
        L = run[0][0]
        pts = [(r[2] * G, r[1] * G) for r in run]
        # remove collinear points
        keep = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = keep[-1], pts[k], pts[k + 1]
            d1 = (round((b[0] - a[0]) / G), round((b[1] - a[1]) / G))
            d2 = (round((c[0] - b[0]) / G), round((c[1] - b[1]) / G))
            n1 = (np.sign(d1[0]), np.sign(d1[1]))
            n2 = (np.sign(d2[0]), np.sign(d2[1]))
            if n1 != n2:
                keep.append(b)
        if len(pts) > 1:
            keep.append(pts[-1])
        out.append((L, keep))
    return out, [(i * G, j * G) for j, i in vias]


# Hand routes for the USB pair: D+ has to cross D- once (plug order is
# GND, D+, D-, VBUS top to bottom, the MCU has D- above D+). D+ dives to the
# back right after the plug and comes up again just left of the MCU.
PREROUTES = {
    "USB_DM": dict(F=[[(5.445, 12.0), (16.4, 12.0), (17.0, 11.4), (19.062, 11.4)]], vias=[]),
    "USB_DP": dict(F=[[(5.445, 10.0), (11.6, 10.0)],
                      [(17.4, 12.9), (18.5, 11.8), (19.062, 11.8)],
                      [(12.9, 20.25), (14.1, 20.25)]],
                   B=[[(11.6, 10.0), (11.6, 12.9), (17.4, 12.9)],
                      [(12.6, 12.9), (12.6, 19.95), (12.9, 20.25)]],
                   vias=[(11.6, 10.0), (17.4, 12.9), (12.9, 20.25)]),
}


DROP_Y, SEND_Y = 22.2, 19.5
U1X, U1Y = 21.0, 11.0          # MCU centre (rotated 90 deg)
PAD_OUT = 1.9375               # pad centre distance from MCU centre


def line_y(pin):
    return 13.4 + (17 - pin) * 0.6


def key_bus(geom):
    """Fully hand-planned key wiring (nothing crosses, checked by DRC).

    Lines on the back, one per key, ordered by MCU pin: pin 17 (rightmost key)
    on top, pin 5 (leftmost key) at the bottom. Right-side pins 8-14 fan out on
    the front with nested L shapes, top-side pins 15-17 wrap around above them,
    bottom-side pins 5-7 drop straight down. Each line drops at its key's x to
    a via between the 1M resistor and the key. SEND runs on the front above the
    resistor row.
    """
    xc, rp = {}, {}
    for p in geom["pads"]:
        if p["ref"].startswith("K"):
            xc[int(p["ref"][1:])] = p["x"]
        if p["ref"].startswith("R") and p["ref"][1:].isdigit() and int(p["ref"][1:]) <= 13:
            rp[(int(p["ref"][1:]), p["num"])] = (p["x"], p["y"])
    pin_key = {k[3]: i for i, k in enumerate(design.KEYS)}
    right_x = U1X + PAD_OUT    # 22.94
    top_y = U1Y - PAD_OUT      # 9.06
    bot_y = U1Y + PAD_OUT      # 12.94
    for pin, i in pin_key.items():
        net = design.key_net(design.KEYS[i][0])
        x_key = xc[i + 1]
        ly = line_y(pin)
        F, B, vias = [], [], []
        if 8 <= pin <= 14:
            py = U1Y + 1.2 - (pin - 8) * 0.4
            vx = 23.8 + (pin - 8) * 0.6
            F.append([(right_x, py), (vx, py), (vx, ly)])
            v = (vx, ly)
        elif pin >= 15:
            px = U1X + 1.2 - (pin - 15) * 0.4
            hy = 8.2 - (pin - 15) * 0.6
            vx = 28.0 + (pin - 15) * 0.6
            F.append([(px, top_y), (px, hy), (vx, hy), (vx, ly)])
            v = (vx, ly)
        elif pin == 7:
            F.append([(22.2, bot_y), (22.2, 13.5), (22.7, 14.0)])
            v = (22.7, 14.0)
        elif pin == 6:
            F.append([(21.8, bot_y), (21.8, 14.8)])
            v = (21.8, 14.8)
        elif pin == 5:
            F.append([(21.4, bot_y), (21.4, 14.0), (21.0, 14.4), (21.0, 15.4)])
            v = (21.0, 15.4)
        vias.append(v)
        if pin >= 8:
            B.append([v, (x_key, ly), (x_key, DROP_Y)])
        else:
            B.append([v, (v[0], ly), (x_key, ly), (x_key, DROP_Y)])
        rx, ry = rp[(i + 1, "1")]
        F.append([(rx, ry), (x_key, DROP_Y), (x_key, KEY_TOP + 0.5)])
        vias.append((x_key, DROP_Y))
        PREROUTES[net] = dict(F=F, B=B, vias=vias)
    xs = sorted(rp[(k + 1, "2")] for k in range(len(design.KEYS)))
    send = [[(21.0, bot_y), (21.0, 13.6), (20.3, 14.3), (20.3, SEND_Y)],
            [(xs[0][0], SEND_Y), (xs[-1][0], SEND_Y)]]
    for x, y in xs:
        send.append([(x, SEND_Y), (x, y)])
    PREROUTES["SEND"] = dict(F=send, vias=[])
    # short MCU escapes on the crowded left and top sides
    PREROUTES["VBUS"] = dict(F=[[(20.2, bot_y), (20.2, 13.5), (19.38, 14.3)]], vias=[])
    PREROUTES["LED"] = dict(F=[[(19.062, 10.2), (18.6, 10.2), (18.0, 9.6), (18.0, 5.9), (17.11, 5.0)]], vias=[])
    PREROUTES["SWCLK"] = dict(F=[[(19.062, 10.6), (17.6, 10.6), (17.4, 10.4), (17.4, 6.5)]],
                              B=[[(17.4, 6.5), (31.08, 6.5), (31.08, 3.0)]], vias=[(17.4, 6.5)])
    PREROUTES["SWDIO"] = dict(F=[[(19.062, 11.0), (17.2, 11.0), (16.8, 10.6), (16.8, 7.3)]],
                              B=[[(16.8, 7.3), (16.8, 5.6), (28.54, 5.6), (28.54, 3.0)]], vias=[(16.8, 7.3)])
    PREROUTES["BUZ_A"] = dict(F=[[(20.2, top_y), (20.2, 3.3), (71.4, 3.3), (71.4, 9.6)]], vias=[])
    PREROUTES["BUZ_B"] = dict(F=[[(19.8, top_y), (19.8, 2.6), (82.6, 2.6), (82.6, 9.6)]], vias=[])
    # ground vias in the MCU exposed pad
    PREROUTES["GND"] = dict(vias=[(U1X - 0.55, U1Y - 0.55), (U1X + 0.55, U1Y - 0.55),
                                  (U1X - 0.55, U1Y + 0.55), (U1X + 0.55, U1Y + 0.55)])


KEY_TOP = 23.0


def add_preroutes(grid, result):
    for net, r in PREROUTES.items():
        w = tw(net)
        for L in LAYERS:
            for pts in r.get(L, []):
                for a, b in zip(pts, pts[1:]):
                    result["segments"].append(dict(net=net, layer=L, x1=a[0], y1=a[1], x2=b[0], y2=b[1], w=w))
                    grid.items[L].append((grid.netid[net], LineString([a, b]).buffer(w / 2, quad_segs=4)))
        for x, y in r["vias"]:
            result["vias"].append(dict(net=net, x=x, y=y, d=VIA_D, drill=VIA_DRILL))
            for L in LAYERS:
                grid.items[L].append((grid.netid[net], Point(x, y).buffer(VIA_D / 2, quad_segs=6)))


def route_all(geom, order, prefer_map=None):
    grid = Grid(geom)
    for p in geom["pads"]:
        if p["net"]:
            grid.nid(p["net"])
    result = dict(segments=[], vias=[])
    key_bus(geom)
    add_preroutes(grid, result)
    pads_by_net = {}
    for p in geom["pads"]:
        if p["net"]:
            pads_by_net.setdefault(p["net"], []).append(p)
    failed = []
    for net, pin_order, tree_pad in order:
        pads = pads_by_net[net]
        if pin_order and pin_order not in ("TREE", "VIAS"):
            pads = sorted(pads, key=lambda p: pin_order.index((p["ref"], p["num"])) if (p["ref"], p["num"]) in pin_order else 99)
        w = tw(net)
        blk = {L: grid.blocked_for(net, L) for L in LAYERS}
        # vias: need VIA_D/2 + CLR from foreign copper on both layers
        extra = VIA_D / 2 - w / 2
        via_ok = np.ones((NY, NX), bool)
        for L in LAYERS:
            b = blk[L]
            # dilate by `extra` using shifted ORs (square-ish approximation, conservative)
            r = int(math.ceil(extra / G))
            d = b.copy()
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    if dj * dj + di * di > r * r:
                        continue
                    d[max(dj, 0):NY + min(dj, 0), max(di, 0):NX + min(di, 0)] |= \
                        b[max(-dj, 0):NY - max(dj, 0), max(-di, 0):NX - max(di, 0)]
            via_ok &= ~d
        # no vias inside pads (keeps pads flat for assembly)
        for L in LAYERS:
            for nid, g in grid.items[L]:
                x0, y0, x1, y1 = g.buffer(VIA_D / 2).bounds
                i0, i1 = max(int(x0 / G), 0), min(int(x1 / G) + 2, NX)
                j0, j1 = max(int(y0 / G), 0), min(int(y1 / G) + 2, NY)
                via_ok[j0:j1, i0:i1] &= ~shapely.contains_xy(g.buffer(VIA_D / 2), GX[j0:j1, i0:i1], GY[j0:j1, i0:i1])

        def pad_cells(p):
            g = Polygon(p["polys"][0])
            m = shapely.contains_xy(g.buffer(-w / 2 + 0.01) if g.area > w * w * 1.5 else g, GX, GY)
            js, is_ = np.nonzero(m & ~blk[p["layer"]])
            return {(p["layer"], int(j), int(i)) for j, i in zip(js, is_)}

        if pin_order == "TREE":
            # existing prerouted copper of this net is the tree; connect one pad to it
            own = {L: np.zeros((NY, NX), bool) for L in LAYERS}
            for L in LAYERS:
                for pts in (PREROUTES[net].get("tree_" + L) or PREROUTES[net].get(L, [])):
                    g = LineString(pts).buffer(0.03)
                    x0, y0, x1, y1 = g.bounds
                    i0, i1 = max(int(x0 / G) - 1, 0), min(int(x1 / G) + 2, NX)
                    j0, j1 = max(int(y0 / G) - 1, 0), min(int(y1 / G) + 2, NY)
                    own[L][j0:j1, i0:i1] |= shapely.contains_xy(g, GX[j0:j1, i0:i1], GY[j0:j1, i0:i1])
            tree = set()
            for L in LAYERS:
                js, is_ = np.nonzero(own[L] & ~blk[L])
                tree |= {(L, int(j), int(i)) for j, i in zip(js, is_)}
            pads = [None] + [p for p in pads if (p["ref"], p["num"]) == tree_pad]
        elif pin_order == "VIAS":
            tree = set()
            for x, y in PREROUTES[net]["vias"]:
                for L in LAYERS:
                    tree.add((L, int(round(y / G)), int(round(x / G))))
            pads = [None] + [p for p in pads if (p["ref"], p["num"]) != tree_pad]
        else:
            tree = pad_cells(pads[0])
        if not tree:
            failed.append((net, pads[0]["ref"], "no start cells"))
            continue
        tree_pts = []
        for p in pads[1:]:
            if (p["ref"], p["num"]) in (("U1", "2"),):
                continue
            tc = pad_cells(p)
            if tc & tree:
                continue
            if not tc:
                failed.append((net, p["ref"] + "." + p["num"], "no cells"))
                continue
            print("  via_ok cells", int(via_ok.sum()), "start", len(tc), "tree", len(tree), file=sys.stderr)
            path = astar(blk, via_ok, tc, tree, (prefer_map or {}).get(net))
            if path is None:
                failed.append((net, p["ref"] + "." + p["num"], "no path"))
                continue
            runs, vias = simplify(path)
            # pad centre stubs so the track starts at the pad centre
            sL, sj, si = path[0]
            runs[0][1].insert(0, (p["x"], p["y"]))
            for L, pts in runs:
                for a, b in zip(pts, pts[1:]):
                    if a == b:
                        continue
                    result["segments"].append(dict(net=net, layer=L, x1=a[0], y1=a[1], x2=b[0], y2=b[1], w=w))
                    seg = LineString([a, b]).buffer(w / 2, quad_segs=4)
                    grid.items[L].append((grid.netid[net], seg))
                if len(pts) == 1:
                    pass
            for x, y in vias:
                result["vias"].append(dict(net=net, x=x, y=y, d=VIA_D, drill=VIA_DRILL))
                for L in LAYERS:
                    grid.items[L].append((grid.netid[net], Point(x, y).buffer(VIA_D / 2, quad_segs=6)))
            for c in path:
                tree.add(c)
            # also make the new track cells part of the tree (all cells on the path)
            blk_new = {L: grid.blocked_for(net, L) for L in LAYERS}
            blk = blk_new
        # end-of-net: connect the first pad centre too, if the tree began inside a pad
        print("routed", net, file=sys.stderr)
    return result, failed


if __name__ == "__main__":
    geom = json.load(open(sys.argv[1]))
    order = []
    # USB first, then the key nets from the far right inward, then the rest
    order.append(("VBUS", [("C1", "1"), ("C2", "1"), ("J1", "1"), ("R15", "2"), ("TP1", "1")], None))
    order.append(("GND", "VIAS", ("U1", "29")))
    for net in ("LED_A", "BOOT"):
        order.append((net, None, None))
    only = sys.argv[3:] if len(sys.argv) > 3 else None
    if only:
        order = [o for o in order if o[0] in only]
    res, failed = route_all(geom, order)
    json.dump(res, open(sys.argv[2], "w"), indent=1)
    print("segments", len(res["segments"]), "vias", len(res["vias"]))
    for f in failed:
        print("FAILED", f)
