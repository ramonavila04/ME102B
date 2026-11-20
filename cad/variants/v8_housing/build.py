#!/usr/bin/env python3
"""V8 housing: the V7 enclosure re-done around six unmodified V2 modules (coupler drive).

    python cad/variants/v8_housing/build.py        # writes parts/ (STEP, STL, manifest.json)

Kept from the V7 STEP, unchanged: the inner shell, the lower body (weighing-station bay and
front-panel bay), the front panel with the screen, the weighing station and its fasteners.
Kept from the V2 stand-alone, unchanged: every module part, side plates included.

New here:
  deck     the V7 deck with its old module holes filled, a Ø108 opening over the drop ring,
           and M3 × 4 heat-set inserts (flush in the 5 mm deck, from the top) for the pods;
           it prints top face up like the V7 deck
  pod      one per module (6 identical): the V2 base's job, cut down to the module and
           trimmed clear of the next pod; the V2 side plates glue into its slots as before;
           3 × M3 × 10 from above into the deck, reachable past the module
  chute    the V7 chute idea re-shaped for the drop ring: the same 37° floor plane and lip
           over the weighing tray, widened to catch pills from all six mouths
           (a 22–42 mm ring), and rising through the deck opening at the back
  brackets the chute hangs from the V7 funnel posts, as in v2_v7_module/chute.py
  pill_cup the same cup as the V7 module version (same tray)
  tray     optional electronics tray on the lower body's floor: two half-size breadboards
           (the floor between the V7 posts cannot take a full-size board square-on)
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout as Ly  # noqa: E402

b = Ly.b
OUT = HERE / "parts"

_cs = importlib.util.spec_from_file_location("v7_chute", Ly.ROOT / "cad" / "variants" / "v2_v7_module" / "chute.py")
ch = importlib.util.module_from_spec(_cs)
_cs.loader.exec_module(ch)

# ----------------------------------------------------------------- deck and drop ring
R_OPEN = 54.0          # deck opening: the drop ring (≤ 42 mm) plus the chute walls inside it
DECK_FILL_R = 95.0     # the old V7 module holes inside this radius are filled
INSERT_D = 4.0         # M3 × 4 heat-set insert (OD 5), flush with the deck top, from above

# ----------------------------------------------------------------- pod (V2 world, at the table)
POD_Y0 = None          # set from the side plates (front of their feet − 5)
POD_Y1 = 60.0          # pod reaches this far along the drive
POD_SCREWS = [(22.0, 34.0), (22.0, 55.0), (46.0, 46.0)]   # V2 world x, y: over the deck, reachable from above
WIRE_SLOT = (-26.0, 40.0, 16.0, 8.0)   # x, y centre, length (along y), width: beside the drive
TRIM_GAP = 1.5

# ----------------------------------------------------------------- chute outline
# inner half-width of the floor against y (enclosure), lip at the front. Covers the drop
# ring (r ≤ 42 mm + 3) and narrows to the V7 lip; at y −64..−84 it stays inside the front
# funnel post (x 34) so the V7 front bracket still fits.
# From the lip to y −64 it is the V7-module chute's taper exactly: that chute's install
# path passes the components on the back of the front panel (a wider wall here does not).
CHUTE_HW = [(-116.0, 13.0), (-64.0, 21.9), (-40.0, 30.0), (-20.0, 44.0),
            (0.0, 47.0), (20.0, 44.0), (32.0, 36.0), (44.0, 20.0)]
CHUTE_TOP_IN = 8.0     # chute trimmed at this height inside the deck opening
CHUTE_TOP_OUT = -6.5   # and 1.5 mm under the deck elsewhere


def _hw(y):
    pts = CHUTE_HW
    if y <= pts[0][0]:
        return pts[0][1]
    for (y0, w0), (y1, w1) in zip(pts, pts[1:]):
        if y <= y1:
            return w0 + (w1 - w0) * (y - y0) / (y1 - y0)
    return pts[-1][1]


def _y_of_s(s):
    return ch.LIP_Y + s * ch.C


def _s_of_y(y):
    return (y - ch.LIP_Y) / ch.C


S_BACK = _s_of_y(CHUTE_HW[-1][0])
# the V7 chute's bracket and rib code reads width(s) and L; point them at this outline
ch.width = lambda s: 2 * _hw(_y_of_s(s))
ch.L = S_BACK


def trough():
    pl = ch.plane_at(0)
    inner = [(-_hw(y), _s_of_y(y)) for y, _ in CHUTE_HW]
    inner = inner + [(_hw(y), _s_of_y(y)) for y, _ in reversed(CHUTE_HW)]
    inner_w = cq.Workplane(pl).polyline(inner).close()
    outer = inner_w.offset2D(ch.T, "intersection")
    body = outer.extrude(ch.H + ch.T).translate(ch.N * (-ch.T))
    cav = cq.Workplane(pl).polyline(inner).close().extrude(ch.H + 1)
    cav = cav.union(cq.Workplane(pl).center(0, -10).rect(2 * CHUTE_HW[0][1] + 0.01, 20).extrude(ch.H + 1))
    body = body.cut(cav)
    # nothing in front of the lip
    body = body.cut(cq.Workplane(pl).workplane(offset=-ch.T - 1).center(0, -50).rect(400, 100).extrude(ch.H + 10))
    return body


def chute_keepout():
    big = 1000
    k = (cq.Workplane("XY").workplane(offset=CHUTE_TOP_OUT).rect(big, big).extrude(300)
         .cut(cq.Workplane("XY").workplane(offset=CHUTE_TOP_OUT - 1).circle(R_OPEN - 1.5).extrude(CHUTE_TOP_IN - CHUTE_TOP_OUT + 1)))
    for y_max, z_min in ch.KEEPOUT:
        k = k.union(cq.Workplane("XY").workplane(offset=z_min).center(0, y_max - 100).rect(big, 200).extrude(300))
    return k


def make_chute():
    return ch.ribs_and_holes(trough()).cut(chute_keepout())


def make_brackets():
    keep = chute_keepout()
    return {p["name"]: (ch.bracket(p).cut(keep), [90, 0, 0] if p["kind"] == "arm" else [0, 90 * p["side"], 0])
            for p in ch.POSTS}


# ----------------------------------------------------------------- pod
def _ref():
    return max((b.pocket_params(p) for p in b.PILLS), key=lambda q: q["depth"])


def _side_bb():
    return b.make_side(_ref()).val().BoundingBox()


def pod_rect():
    bb = _side_bb()
    y0 = bb.ymin - 5
    hw = b.FLANGE_R - 3 + b.TAB_W + 0.2 + b.SIDE_T + 8
    return (cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T)
            .center(0, (y0 + POD_Y1) / 2).rect(2 * hw, POD_Y1 - y0).extrude(Ly.POD_T))


def make_pod_enc():
    """Module 0's pod in the enclosure frame (the others are copies rotated by 60°)."""
    rect = pod_rect()
    p0 = Ly.to_enc(rect, 0)
    bb0 = _side_bb()
    y0 = bb0.ymin - 5
    hw = b.FLANGE_R - 3 + b.TAB_W + 0.2 + b.SIDE_T + 8
    grown = (cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T - 1).center(0, (y0 + POD_Y1) / 2)
             .rect(2 * (hw + TRIM_GAP), POD_Y1 - y0 + 2 * TRIM_GAP).extrude(Ly.POD_T + 2))
    # the corner shared with the previous module's pod goes to that pod (its outer side
    # plate stands there)
    pod = p0.cut(Ly.to_enc(grown, Ly.N_MOD - 1))
    # and clear (by TRIM_GAP) of the next module's side plate foot on this side
    x_in0 = b.FLANGE_R - 3 + b.TAB_W + 0.2
    foot = (cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T - 1)
            .center(-(x_in0 + b.SIDE_T / 2), (bb0.ymin + bb0.ymax) / 2)
            .rect(b.SIDE_T + 2 * (TRIM_GAP + 3), bb0.ylen + 2 * (TRIM_GAP + 3)).extrude(Ly.POD_T + 2))
    pod = pod.cut(Ly.to_enc(foot, 1))
    try:
        pod = pod.edges("|Z").fillet(3.0)
    except Exception:
        pass
    # side-plate slots (the V2 base's), M3 holes, wire slot, all in the V2 world first
    bb = _side_bb()
    x_in = b.FLANGE_R - 3 + b.TAB_W + 0.2
    cuts = cq.Workplane("XY")
    feats = []
    for sx in (-1, 1):
        x_c = sx * (x_in + b.SIDE_T / 2)
        feats.append(cq.Workplane("XY").workplane(offset=b.BASE_Z - 3).center(x_c, (bb.ymin + bb.ymax) / 2)
                     .rect(b.SIDE_T + 0.4, bb.ylen + 0.4).extrude(4))
    for (x, y) in POD_SCREWS:
        feats.append(cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T - 1).center(x, y).circle(1.7)
                     .extrude(Ly.POD_T + 2))
    wx, wy, wl, ww = WIRE_SLOT
    feats.append(cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T - 1).center(wx, wy)
                 .slot2D(wl, ww, 90).extrude(Ly.POD_T + 2))
    for f in feats:
        pod = pod.cut(Ly.to_enc(f, 0))
    return pod


def pod_points_enc(k=0):
    pts = [Ly.pt_enc((x, y, 0), k)[:2] for x, y in POD_SCREWS]
    wx, wy, wl, ww = WIRE_SLOT
    return pts, Ly.pt_enc((wx, wy, 0), k)[:2]


# ----------------------------------------------------------------- deck
def make_deck():
    deck, _, _, _ = Ly.v7_enclosure_pieces()
    d = cq.Workplane(obj=deck)
    d = d.union(cq.Workplane("XY").workplane(offset=-5.0).circle(DECK_FILL_R).extrude(5.0))
    d = d.cut(cq.Workplane("XY").workplane(offset=-10).circle(R_OPEN).extrude(20))
    for k in range(Ly.N_MOD):
        pts, wire = pod_points_enc(k)
        for (x, y) in pts:
            d = d.cut(cq.Workplane("XY").workplane(offset=-6.0).center(x, y).circle(INSERT_D / 2).extrude(7))
        wx, wy, wl, ww = WIRE_SLOT
        slot = (cq.Workplane("XY").workplane(offset=b.BASE_Z - Ly.POD_T - 12).center(wx, wy)
                .slot2D(wl + 2, ww + 2, 90).extrude(30))
        d = d.cut(Ly.to_enc(slot, k))
    return d


# ----------------------------------------------------------------- electronics tray
BB_HALF = (82.6, 54.6)     # half-size breadboard (assumed: the team's boards are not listed)
TRAY_T, TRAY_WALL, TRAY_RIM = 2.0, 1.6, 5.0
FLOOR_Z = -157.0 + 0.3     # top of the lower body's floor (V7 STEP: flat at z −157)
POSTS_XY = [(72.0, 16.0), (-72.0, 16.0), (34.0, -74.0), (104.0, 0.0), (-104.0, 0.0), (0.0, 104.0)]


def make_tray():
    """Two half-size breadboard pockets, sitting loose on the floor between the posts."""
    boards = [(-31.5, -20.0, BB_HALF[1], BB_HALF[0]), (30.0, 30.0, BB_HALF[1], BB_HALF[0])]
    outer = None
    for (cx, cy, w, l) in boards:
        o = cq.Workplane("XY").workplane(offset=FLOOR_Z).center(cx, cy).rect(w + 2 * TRAY_WALL + 1, l + 2 * TRAY_WALL + 1).extrude(TRAY_T + TRAY_RIM)
        outer = o if outer is None else outer.union(o)
    # web between the pockets
    outer = outer.union(cq.Workplane("XY").workplane(offset=FLOOR_Z).center(-0.75, 5).rect(6, 30).extrude(TRAY_T))
    for (cx, cy, w, l) in boards:
        outer = outer.cut(cq.Workplane("XY").workplane(offset=FLOOR_Z + TRAY_T).center(cx, cy).rect(w + 1, l + 1).extrude(TRAY_RIM + 1))
    for (x, y) in POSTS_XY:
        outer = outer.cut(cq.Workplane("XY").workplane(offset=FLOOR_Z - 1).center(x, y).circle(10.0).extrude(30))
    return outer


# ----------------------------------------------------------------- export
def parts():
    out = {
        "deck": (make_deck(), [0, 0, 0], "top face up (as the V7 deck)", 4.0),
        "pod": (make_pod_enc(), [0, 0, 0], "flat", 4.0),
        "chute": (make_chute(), [-ch.FLOOR_DEG, 0, 0], "floor down", 4.0),
        "pill_cup": (ch.pill_cup(), [0, 0, 0], "floor down", 4.0),
        "tray": (make_tray(), [0, 0, 0], "flat", 4.0),
    }
    for n, (s, rot) in make_brackets().items():
        out[n] = (s, rot, "flat", 4.0)
    return out


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    man = dict(variant="v8_housing", pill="housing", parts=[], clearances=[])
    for n, (shape, rot, how, ov) in parts().items():
        cq.exporters.export(shape, str(OUT / f"{n}.step"))
        cq.exporters.export(shape, str(OUT / f"{n}.stl"), tolerance=0.02, angularTolerance=0.08)
        man["parts"].append(dict(name=n, stl=f"{n}.stl", step=f"{n}.step", print_rotation=rot, bed=how,
                                 max_overhang_mm2=ov))
        bb = shape.val().BoundingBox()
        print(f"{n}: {bb.xlen:.0f} x {bb.ylen:.0f} x {bb.zlen:.0f} mm, {shape.val().Volume() / 1000:.1f} cm³")
    (OUT / "manifest.json").write_text(json.dumps(man, indent=2))


if __name__ == "__main__":
    build()
