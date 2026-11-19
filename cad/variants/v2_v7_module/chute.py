#!/usr/bin/env python3
"""Replacement pill chute for the V7 enclosure: from the six modules to the weighing station.

    python cad/variants/v2_v7_module/chute.py

Why: `python -m sim.v7_drop` dropped pills from the V2 modules into the V7 funnel
(cad/onshape/V7_Pill_Dispenser_Heat_Inserts.step, part "Funnel"). 17 of 200 iron and 21 of
200 small tablets stopped on its floor, all with part friction 0.35 or more. The funnel floor
falls about 23° (tan 0.42), so a pill whose friction is above ~0.4 stops on it, and the
simulation (like the campaign) draws friction from 0.2 to 0.6.

This chute:
  * a flat floor at FLOOR_DEG (37°, tan 0.75 > 0.6), from just under the deck at the back
    (s = L) to a lip over the weighing plate (y = LIP_Y), narrowing from W_BACK to W_LIP
    (the six duct ends land within 31 mm of the axis);
  * side walls perpendicular to the floor, trimmed below the deck and clear of the front
    panel bay; the front end is open, so pills slide off the lip onto the plate;
  * three brackets that bolt onto the enclosure's existing funnel posts (same M3 screws
    from above as the V7 funnel), each joined to a rib on the trough by a countersunk
    M3 screw that sits flush inside the trough.
Print: trough floor down (every wall is then vertical, no supports); brackets flat.

Frame: the V7 enclosure frame (mm): deck top z = 0, +y to the back, front panel at −y.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
OUT = HERE / "chute"

FLOOR_DEG = 37.0
LIP_Y, LIP_Z = -116.0, -119.0      # floor top at the lip (station plate below at about z −131)
DECK_UNDERSIDE = -5.0
TOP_Z = -6.5                       # trim every part 1.5 mm below the deck
W_BACK, W_LIP = 78.0, 26.0         # inside width at the back and at the lip
T = 2.4                            # wall and floor
H = 70.0                           # wall height (perpendicular to the floor) before trimming
# keep out (y below, z above): the front panel bay and its controls, and enclosure ribs
# under the deck near the front (found by the clash check against the V7 STEP)
KEEPOUT = [(-112.0, -102.0), (-100.0, -98.0), (-80.0, -40.0)]

# enclosure funnel posts (from the V7 STEP: insert tops), screws M3 from above
# kind "arm": a plate in the plane y = post y that reaches in to the end face of a rib.
# kind "face": a plate flat against the outer face of a shallow rib (the front post is
# almost under the trough wall), joined at y = joint_y.
# h: joint height above the floor (the side joints sit low: at y = 16 the floor is only
# 13 mm under the deck).
POSTS = [dict(name="bracket_right", kind="arm", x=72.0, y=16.0, z=-59.0, side=1, h=4.0, rib_out=8.0),
         dict(name="bracket_left", kind="arm", x=-72.0, y=16.0, z=-59.0, side=-1, h=4.0, rib_out=8.0),
         dict(name="bracket_front", kind="face", x=34.0, y=-74.0, z=-101.0, side=1, h=10.0, rib_out=3.6,
              joint_y=-64.0)]
FOOT = 8.0          # bracket foot height above the post top
BR_T = 10.0         # bracket plate thickness (y)
RIB_W = 14.0        # rib width along the slope
M3_CLEAR, INSERT_HOLE, CSK_D = 3.4, 4.2, 6.6

th = math.radians(FLOOR_DEG)
S, C = math.sin(th), math.cos(th)
E_B = cq.Vector(0, C, S)           # up the slope (toward the back)
N = cq.Vector(0, -S, C)            # floor normal, into the trough
O = cq.Vector(0, LIP_Y, LIP_Z)     # floor top surface, at the lip centre
L = (TOP_Z - LIP_Z) / S + 4.0      # floor length (runs past the deck trim; trimmed below)


def plane_at(s=0.0):
    """Chute-frame workplane: origin on the floor top at slope distance s, x across,
    y' up the slope, normal into the trough."""
    return cq.Plane(origin=O + E_B * s, xDir=cq.Vector(1, 0, 0), normal=N)


def width(s):
    return W_LIP + (W_BACK - W_LIP) * min(max(s / L, 0.0), 1.0)


def _keepout():
    big = 1000
    above_deck = cq.Workplane("XY").workplane(offset=TOP_Z).rect(big, big).extrude(200)
    for y_max, z_min in KEEPOUT:
        above_deck = above_deck.union(cq.Workplane("XY").workplane(offset=z_min).center(0, y_max - 100)
                                      .rect(big, 200).extrude(300))
    return above_deck


def wall_x(s):
    """Outer face of the +x wall at slope distance s."""
    return width(s) / 2 + T


def slope_of_y(y_target, h):
    """Slope distance s of the point at height h (along N) above the floor that has y."""
    # y = LIP_Y + s*C - h*S
    return (y_target - LIP_Y + h * S) / C


def trough():
    pl = plane_at(0)
    inner = [(-W_LIP / 2, 0), (W_LIP / 2, 0), (W_BACK / 2, L), (-W_BACK / 2, L)]
    outer = [(-W_LIP / 2 - T, 0), (W_LIP / 2 + T, 0), (W_BACK / 2 + T, L + T), (-W_BACK / 2 - T, L + T)]
    body = cq.Workplane(pl).workplane(offset=-T).polyline(outer).close().extrude(H + T)
    cav = cq.Workplane(pl).polyline(inner).close().extrude(H + 1)
    # open front: extend the cavity past the lip
    cav = cav.union(cq.Workplane(pl).center(0, -10).rect(W_LIP + 0.01, 20).extrude(H + 1))
    body = body.cut(cav)
    body = body.cut(cq.Workplane(pl).workplane(offset=-T - 1).center(0, -50).rect(400, 100).extrude(H + 10))
    return body


def _teardrop(origin, axis, roof, r, length):
    """Hole along `axis` from `origin`, with a 45° roof pointing `roof` (print up)."""
    axis, roof = axis.normalized(), roof.normalized()
    if axis.cross(roof).Length < 1e-6:        # hole points straight up when printed: no roof
        return cq.Workplane(cq.Plane(origin=origin, xDir=_any_perp(axis), normal=axis)).circle(r).extrude(length)
    side = axis.cross(roof).normalized()
    roof = side.cross(axis).normalized()     # roof ⟂ axis
    pl = cq.Plane(origin=origin, xDir=side, normal=axis)
    cyl = cq.Workplane(pl).circle(r).extrude(length)
    # roof from 42° up the circle to an apex, edges 50° from the bed (clear of the 45° rule)
    a = math.radians(42)
    bx, by = r * math.cos(a), r * math.sin(a)
    apex = by + bx * math.tan(math.radians(50))
    sg = _dot(roof, pl.yDir)
    tri = cq.Workplane(cq.Plane(origin=origin, xDir=side, normal=axis)).polyline(
        [(-bx, by * sg), (bx, by * sg), (0, apex * sg)]).close().extrude(length)
    return cyl.union(tri)


def _any_perp(a):
    t = cq.Vector(1, 0, 0) if abs(a.x) < 0.9 else cq.Vector(0, 1, 0)
    return a.cross(t).normalized()


def _dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def joint_point(post):
    """Bolt axis point on the trough wall's outer face, in the bracket's plane y = post y."""
    h = post["h"]                  # height above the floor along N
    s = slope_of_y(post.get("joint_y", post["y"]), h)
    x = post["side"] * wall_x(s)
    p = O + E_B * s + N * h
    return cq.Vector(x, p.y, p.z), s, h


def ribs_and_holes(body):
    for p in POSTS:
        q, s, h = joint_point(p)
        sd = p["side"]
        pl = cq.Plane(origin=O + E_B * (s - RIB_W / 2) + cq.Vector(sd * (wall_x(s) - T - 0.5), 0, 0) + N * (-T),
                      xDir=cq.Vector(sd, 0, 0), normal=N)
        ro = p["rib_out"]
        rib = cq.Workplane(pl).polyline([(0, 0), (T + 0.5 + ro, 0), (T + 0.5 + ro, RIB_W), (0, RIB_W)]
                                        ).close().extrude(h + 8 + T)
        body = body.union(rib)
        # countersunk screw from inside the trough: through wall and rib, flush inside
        x_in = sd * (wall_x(s) - T)
        start = cq.Vector(x_in - sd * 1.0, q.y, q.z)
        body = body.cut(_teardrop(start, cq.Vector(sd, 0, 0), N, M3_CLEAR / 2, T + ro + 3))
        csk = cq.Solid.makeCone(CSK_D / 2, M3_CLEAR / 2, (CSK_D - M3_CLEAR) / 2,
                                cq.Vector(x_in, q.y, q.z), cq.Vector(sd, 0, 0))
        body = body.cut(cq.Workplane(obj=csk))
    return body


def bracket(p):
    """Flat bracket from an enclosure post to a rib on the trough. "arm": plate in the
    plane y = post y, printed on its −y face. "face": plate in a plane x = const against
    the rib, printed on its outer (+x) face. Neither covers the post screw, so a driver reaches its
    head from above."""
    q, s, h = joint_point(p)
    sd = p["side"]
    x_face = q.x + sd * p["rib_out"]             # rib outer face
    xm, zm = p["x"], p["z"]
    if p["kind"] == "arm":
        pts = [(xm + 7 * sd, zm), (xm + 7 * sd, zm + FOOT), (xm - 4 * sd, zm + FOOT),
               (x_face + 12 * sd, q.z + 7), (x_face, q.z + 7), (x_face, q.z - 7), (xm - 7 * sd, zm)]
        plate = cq.Workplane("XZ", origin=(0, p["y"] + BR_T / 2, 0)).polyline(pts).close().extrude(BR_T)
        up = cq.Vector(0, 1, 0)
        ins_axis = cq.Vector(sd, 0, 0)
    else:
        ym, yj = p["y"], q.y
        pts = [(ym - 7, zm), (ym + 7, zm), (yj + 7, q.z - 7), (yj + 7, q.z + 7), (ym + 4.5, q.z + 7),
               (ym + 4.5, zm + FOOT), (ym - 7, zm + FOOT)]
        plate = cq.Workplane("YZ", origin=(x_face, 0, 0)).polyline(pts).close().extrude(BR_T * sd)
        up = cq.Vector(-sd, 0, 0)    # printed on its outer face, so the insert hole opens upward
        ins_axis = cq.Vector(sd, 0, 0)
    # post screw, vertical, through the foot (head on the foot top)
    plate = plate.cut(_teardrop(cq.Vector(xm, p["y"], zm - 1), cq.Vector(0, 0, 1), up, M3_CLEAR / 2, FOOT + 2))
    # heat-set insert for the countersunk screw from inside the trough
    plate = plate.cut(_teardrop(cq.Vector(x_face - sd * 0.01, q.y, q.z), ins_axis, up, INSERT_HOLE / 2, 6.5))
    return plate


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    keep = _keepout()
    body = ribs_and_holes(trough()).cut(keep)
    parts = {"chute": (body, [-FLOOR_DEG, 0, 0], "floor down")}
    for p in POSTS:
        rot = [90, 0, 0] if p["kind"] == "arm" else [0, 90 * p["side"], 0]
        parts[p["name"]] = (bracket(p).cut(keep), rot, "flat")
    man = dict(variant="v2_v7_module", pill="chute", parts=[], clearances=[])
    for n, (shape, rot, how) in parts.items():
        cq.exporters.export(shape, str(OUT / f"{n}.step"))
        cq.exporters.export(shape, str(OUT / f"{n}.stl"), tolerance=0.02, angularTolerance=0.08)
        man["parts"].append(dict(name=n, stl=f"{n}.stl", step=f"{n}.step", print_rotation=rot, bed=how,
                                 max_overhang_mm2=4.0))
    (OUT / "manifest.json").write_text(json.dumps(man, indent=2))
    return parts


if __name__ == "__main__":
    for n, (s, _, _) in build().items():
        bb = s.val().BoundingBox()
        print(f"{n}: x {bb.xmin:.1f}..{bb.xmax:.1f} y {bb.ymin:.1f}..{bb.ymax:.1f} z {bb.zmin:.1f}..{bb.zmax:.1f}"
              f" vol {s.val().Volume():.0f} mm³")
