#!/usr/bin/env python3
"""V8 housing: the V7 enclosure re-done around six unmodified V2 modules (coupler drive).

    python cad/variants/v8_housing/build.py        # writes parts/ (STEP, STL, manifest.json)

Kept from the V7 STEP, unchanged: the inner shell, the lower body (weighing-station bay and
front-panel bay), the front panel with the screen, the weighing station and its fasteners.
Kept from the V2 stand-alone, unchanged: every module part, side plates included.

New here:
  deck     the V7 deck with its old module holes filled, an opening over the drop ring that
           overlaps the chute walls by 1 mm, a 30 mm fence round it (notched round the modules),
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
DECK_FILL_R = 95.0     # the old V7 module holes inside this radius are filled
INSERT_D = 4.0         # M3 × 4 heat-set insert (OD 5), flush with the deck top, from above
OPEN_OVERLAP = 1.0     # the deck opening is this much inside the chute walls (no gap to fall through)
OPEN_FRONT_Y = -63.0   # the opening ends here (the drop ring reaches y −60)
FENCE_Z, FENCE_T = 30.0, 2.4   # fence round the opening on the deck, notched round the modules
FENCE_CLEAR = 1.5      # notch clearance to a module (swept straight up, so a module lifts off)

# ----------------------------------------------------------------- pod (V2 world, at the table)
POD_Y1 = 60.0          # pod reaches this far along the drive
POD_SCREWS = [(22.0, 34.0), (22.0, 49.0), (40.0, 40.0)]   # V2 world x, y: over the deck, reachable from above
WIRE_SLOT = (-20.0, 55.0, 16.0, 8.0)   # x, y centre, length (along y), width: inside r 88 of the axis (clear of the shell ledge)
TRIM_GAP = 1.5
POD_R_MIN = 61.0       # pods stop this far from the ring centre: clear of the deck fence on every side

# ----------------------------------------------------------------- chute outline
# Inner half-width of the floor against y (enclosure). The floor is the V7-module chute's
# plane (37°, lip over the weighing tray); the walls are vertical, so the chute's outline is
# the same at every height and the deck can overlap it. It covers the drop ring (mouths on
# r 32 round CENTRE, pills within 42 mm + 3) and stays wholly under the deck (the rear end is
# at y 30, 2.5 mm under the 1.5 mm deck clearance). From the lip to y −55 it is the
# V7-module chute's taper exactly: that chute's install path passes the components on the
# back of the front panel, and the V7 front bracket (y −81..−57) fits it. Behind that the walls
# open out at 25° to the flow, no more: where a converging wall meets the 37° floor the corner
# slopes at atan(tan 37° · cos 25°) = 34°, steeper than the 31° friction angle of μ 0.6 (the
# first revision opened out at 59° there; tablets stopped in that 21° corner).
CHUTE_HW = [(-116.0, 13.0), (-57.0, 23.1), (-5.0, 47.3), (5.0, 45.0), (15.0, 40.0),
            (22.0, 31.0), (30.0, 14.0)]
CHUTE_TOP = -6.5       # everything 1.5 mm under the deck


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


def _floor_z(y):
    return ch.LIP_Z + (y - ch.LIP_Y) * ch.S / ch.C


def inner_outline():
    return ([(-_hw(y), y) for y, _ in CHUTE_HW] + [(_hw(y), y) for y, _ in reversed(CHUTE_HW)])


def joint_point(post):
    """Bolt axis point on the (vertical) wall's outer face, h above the floor along N."""
    h = post["h"]
    s = ch.slope_of_y(post.get("joint_y", post["y"]), h)
    p = ch.O + ch.E_B * s + ch.N * h
    x = post["side"] * (_hw(p.y) + ch.T)
    return cq.Vector(x, p.y, p.z), s, h


ch.joint_point = joint_point      # the V7 chute's bracket() uses it
# the vertical walls reach 1.5 mm lower at the lip than the V7 chute's: the cup's low back
# wall (under the lip) is 1.5 mm lower here
ch.CUP = dict(ch.CUP, back_top=ch.CUP["back_top"] - 1.5)


def trough():
    """Floor slab on the 37° plane plus vertical walls round the outline (open at the lip)."""
    inner = cq.Workplane("XY").workplane(offset=-200).polyline(inner_outline()).close()
    ring_outer = inner.offset2D(ch.T, "intersection").extrude(400)
    walls_and_floor = ring_outer
    # keep between the floor's underside and the top limit
    pl = ch.plane_at(0)
    below = cq.Workplane(pl).workplane(offset=-ch.T).rect(1000, 1000).extrude(-300)
    body = walls_and_floor.cut(below)
    cav = (cq.Workplane("XY").workplane(offset=-200).polyline(inner_outline()).close().extrude(400)
           .cut(cq.Workplane(pl).rect(1000, 1000).extrude(-300)))
    body = body.cut(cav)
    # open front: nothing in front of the lip
    body = body.cut(cq.Workplane("XY").workplane(offset=-300).center(0, ch.LIP_Y - 100).rect(1000, 200).extrude(600))
    return body


def ribs_and_holes(body):
    """As the V7 chute's, for vertical walls: a rib on the wall's outer face at each post and a
    countersunk M3 from inside the trough, flush with the wall."""
    for p in ch.POSTS:
        q, s, h = joint_point(p)
        sd = p["side"]
        wx = abs(q.x)
        pl = cq.Plane(origin=ch.O + ch.E_B * (s - ch.RIB_W / 2) + cq.Vector(sd * (wx - ch.T - 0.5), 0, 0) + ch.N * (-ch.T),
                      xDir=cq.Vector(sd, 0, 0), normal=ch.N)
        ro = p["rib_out"]
        rib = cq.Workplane(pl).polyline([(0, 0), (ch.T + 0.5 + ro, 0), (ch.T + 0.5 + ro, ch.RIB_W), (0, ch.RIB_W)]
                                        ).close().extrude(h + 8 + ch.T)
        body = body.union(rib)
        x_in = sd * (wx - ch.T)
        start = cq.Vector(x_in - sd * 1.0, q.y, q.z)
        body = body.cut(ch._teardrop(start, cq.Vector(sd, 0, 0), ch.N, ch.M3_CLEAR / 2, ch.T + ro + 3))
        csk = cq.Solid.makeCone(ch.CSK_D / 2, ch.M3_CLEAR / 2, (ch.CSK_D - ch.M3_CLEAR) / 2,
                                cq.Vector(x_in, q.y, q.z), cq.Vector(sd, 0, 0))
        body = body.cut(cq.Workplane(obj=csk))
    return body


def chute_keepout():
    big = 1000
    k = cq.Workplane("XY").workplane(offset=CHUTE_TOP).rect(big, big).extrude(300)
    for y_max, z_min in ch.KEEPOUT:
        k = k.union(cq.Workplane("XY").workplane(offset=z_min).center(0, y_max - 100).rect(big, 200).extrude(300))
    return k


def _cavity():
    """The trough's inside: the inner outline above the floor's top surface."""
    pl = ch.plane_at(0)
    return (cq.Workplane("XY").workplane(offset=-200).polyline(inner_outline()).close().extrude(400)
            .cut(cq.Workplane(pl).rect(1000, 1000).extrude(-300)))


# Gate across the chute in front of the V7 shell's front shelf (the panel bay's floor, z −92.7 at
# y −112..−108, 20 mm above the chute floor). In the drop simulation a small tablet that landed
# hard bounced forward above the low front walls and came to rest on that shelf (seed 5131). The
# gate's plate stops anything flying above the walls there; tablets sliding on the floor pass
# under it (≥ 10.7 mm headroom). Its underside rises 20° toward the front, so it prints without
# support with the chute floor down.
GATE_Y = (-99.5, -97.1)       # behind the panel's rear components (y ≤ −104), where the walls are tall
GATE_Z_TOP = -70.0
GATE_BOTTOM = -94.0        # underside height at its back face (10.8 mm over the floor)
GATE_BOTTOM_DEG = 20.0


def gate():
    y0, y1 = GATE_Y
    xo = max(_hw(y0), _hw(y1)) + ch.T
    slab = cq.Workplane("XY").workplane(offset=-100.0).center(0, (y0 + y1) / 2).rect(2 * xo, y1 - y0).extrude(GATE_Z_TOP + 100.0)
    # headroom under the plate, inside the trough: below a plane through (y1, GATE_BOTTOM)
    # rising toward −y at GATE_BOTTOM_DEG
    t = math.tan(math.radians(GATE_BOTTOM_DEG))
    pts = [(y1 + 5, GATE_BOTTOM - 5 * t), (y0 - 5, GATE_BOTTOM + (y1 - y0 + 5) * t), (y0 - 5, -200), (y1 + 5, -200)]
    under = cq.Workplane("YZ").workplane(offset=-_hw(y1)).polyline(pts).close().extrude(2 * _hw(y1))
    g = slab.cut(under)
    # and nothing below the chute floor's top surface (it sits on the walls and floor)
    return g.cut(cq.Workplane(ch.plane_at(0)).rect(1000, 1000).extrude(-300))


def make_chute():
    # the ribs follow the wall at their joint, but the wall opens out along a rib's 14 mm, so
    # cut the inside clean again: nothing may stand proud of the floor or walls inside
    return ribs_and_holes(trough()).cut(_cavity()).cut(chute_keepout()).union(gate())


def make_brackets():
    keep = chute_keepout()
    return {p["name"]: (ch.bracket(p).cut(keep), [90, 0, 0] if p["kind"] == "arm" else [0, 90 * p["side"], 0])
            for p in ch.POSTS}


def opening_polygon():
    """Deck opening: the chute's inner outline shrunk by OPEN_OVERLAP, from OPEN_FRONT_Y back."""
    from shapely.geometry import Polygon, box
    poly = Polygon(inner_outline()).buffer(-OPEN_OVERLAP, join_style=2)
    return poly.intersection(box(-200, OPEN_FRONT_Y, 200, 200))


def _module_notches():
    """Each module's parts near the fence, swept straight up (so the module lifts off), as
    (shapely polygon, bottom z) pieces binned by height."""
    import numpy as np
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    sp = importlib.util.spec_from_file_location("v8_assemble", HERE / "assemble.py")
    A = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(A)
    region = opening_polygon().buffer(FENCE_T + FENCE_CLEAR + 4)
    out = []
    bodies = Ly.v2_module_bodies("iron") + [(n, c, s) for n, c, s in Ly.v2_module_bodies("small") if n in ("disc", "backplate", "hopper")]
    for k in range(Ly.N_MOD):
        bins = {}
        for n, c, s in bodies:
            t = A.to_mesh(Ly.to_enc(s, k), 0.3)
            tri = t.triangles
            zmin = tri[:, :, 2].min(1)
            keep = zmin < FENCE_Z + 2
            for tr, zm in zip(tri[keep], zmin[keep]):
                pg = Polygon(tr[:, :2])
                if not pg.is_valid or pg.area < 1e-6:
                    pg = pg.buffer(0.05)
                if not pg.intersects(region):
                    continue
                key = int(max(zm - FENCE_CLEAR, 0.5) // 2)
                bins.setdefault(key, []).append(pg)
        for key, pgs in bins.items():
            out.append((unary_union(pgs).buffer(FENCE_CLEAR), key * 2.0))
    return out


def _poly_solid(poly, z0, z1):
    """Extrude a shapely (multi)polygon between z0 and z1."""
    from shapely.geometry import MultiPolygon
    poly = poly.simplify(0.15, preserve_topology=True)
    geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]

    def ring(coords):
        pts = []
        for p in list(coords)[:-1]:
            if not pts or (abs(p[0] - pts[-1][0]) + abs(p[1] - pts[-1][1])) > 0.05:
                pts.append((p[0], p[1]))
        return pts
    out = None
    for g in geoms:
        if g.area < 0.5:
            continue
        w = cq.Workplane("XY").workplane(offset=z0).polyline(ring(g.exterior.coords)).close().extrude(z1 - z0)
        for hole in g.interiors:
            if abs(hole.area if hasattr(hole, "area") else 1) < 0.5:
                continue
            w = w.cut(cq.Workplane("XY").workplane(offset=z0 - 1).polyline(ring(hole.coords)).close().extrude(z1 - z0 + 2))
        out = w if out is None else out.union(w)
    return out


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
    pod = pod.cut(cq.Workplane("XY").workplane(offset=-1).center(*Ly.CENTRE).circle(POD_R_MIN).extrude(Ly.POD_T + 2))
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
    op = opening_polygon()
    d = d.cut(_poly_solid(op, -10, 10))
    fence = _poly_solid(op.buffer(FENCE_T, join_style=2), -0.01, FENCE_Z).cut(_poly_solid(op, -1, FENCE_Z + 1))
    for poly, z0 in _module_notches():
        cut = _poly_solid(poly, max(z0, 0.5), 300)
        if cut is not None:
            fence = fence.cut(cut)
    d = d.union(fence)
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
