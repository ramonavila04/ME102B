#!/usr/bin/env python3
"""V2 — inclined pocket disc (rim-notch singulator).

A disc inclined BETA from horizontal turns over a fixed back plate. Notches cut
into its rim are pockets for exactly one pill; the fixed hopper wall around the
disc closes each notch's outer side. Pills pool at the bottom of the hopper
against that wall, drop into a notch as it passes, ride up, and fall out through
an exit hole in the back plate at the 3 o'clock position while the disc is
stopped. Unseated pills slide off because tan(BETA) is twice the worst-case
friction. The only fixed edges a pocket meets are the concentric hopper wall
(it never crosses a pocket) and the exit hole (larger than the pocket by EXIT_MARGIN).

Local frame: disc front face at z=0, axis +z, "uphill" +y. Assembled (world)
frame = rotation about x by BETA. All exports are in world position.

    python cad/variants/v2_inclined_disc/build.py            # all pills
    python cad/variants/v2_inclined_disc/build.py iron small
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sim.pills import PILLS  # noqa: E402

OUT = Path(__file__).resolve().parent

# ----------------------------------------------------------------- parameters
BETA = 50.0            # disc incline from horizontal, deg. tan(50°)=1.19 ≥ 2×μmax(0.6)
FDM = 0.35             # clearance per side between a pill (at max size) and a pocket wall
RUN = 0.4              # running clearance between moving and fixed printed faces
R_DISC = 30.0          # disc radius
R_WALL = R_DISC + RUN  # hopper bore
WALL = 2.4             # hopper wall thickness (≥1.2 mm; 6 perimeters at 0.4 mm)
HOPPER_DEPTH = 40.0    # hopper wall height in front of the disc (along the axis)
BP_T = 3.0             # back plate thickness
EXIT_MARGIN = 1.2      # exit hole larger than the pocket on every side
DUCT_LEN = 14.0        # exit duct length behind the back plate
WEB_MIN = 4.0          # minimum solid between neighbouring notches at their inner end
EXIT_ANGLE = 0.0       # local angle of the exit (0 = 3 o'clock); fill pool is at 270°
SHAFT_D, SHAFT_FLAT = 3.0, 2.5  # Pololu micro-gearmotor D shaft (Ø3, 2.5 across flat)
GEARBOX = (12.0, 10.0)          # micro-gearmotor gearbox cross-section (w × h)
FLANGE_R = 40.0        # back plate / hopper flange radius
BOLT_R = 36.0          # M3 bolt circle for hopper → back plate
DEPTH_BELOW_T = 0.3    # pocket depth = min pill thickness − this (2nd pill can't nest)


def pocket_params(pill_id: str) -> dict:
    p = PILLS[pill_id]
    if p.kind == "tablet":
        d_max = p.length + p.tol
        t_min = p.thickness - p.tol
        w = d_max + 2 * FDM                     # notch width (tangential)
        r_c = R_WALL - w / 2                    # centre of the pill when against the wall
        r_in = r_c - w / 2
        half_ang = math.asin((w / 2) / r_c)
        shape = "round"
        length = w
    else:
        L = p.length + p.tol_length
        W = p.width + p.tol
        t_min = (p.thickness - p.tol) if p.kind == "caplet" else (p.width - p.tol)
        length = L + 2 * FDM
        w = W + 2 * FDM
        # pill lying tangentially against the curved wall: end-cap centres touch R_WALL
        d_c = math.sqrt((R_WALL - W / 2) ** 2 - ((L - W) / 2) ** 2)
        r_c = d_c
        r_in = d_c - W / 2 - FDM
        half_ang = math.atan((length / 2) / r_in)
        shape = "oblong"
    depth = round(t_min - DEPTH_BELOW_T, 2)
    # number of notches: largest even N leaving WEB_MIN of solid at r_in, multiple of 4
    n = 4
    for cand in range(4, 40, 4):
        web = r_in * (2 * math.pi / cand - 2 * half_ang)
        if web >= WEB_MIN + 2 * EXIT_MARGIN:
            n = cand
    return dict(pill=pill_id, shape=shape, width=round(w, 3), length=round(length, 3),
                r_center=round(r_c, 3), r_inner=round(r_in, 3), depth=depth, n=n,
                pitch_deg=360.0 / n)


# --------------------------------------------------------------- 2-D outlines
def _rot_world(shape: cq.Workplane) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (1, 0, 0), BETA)


# ----------------------------------------------------------------------- parts
def make_disc(pp: dict) -> cq.Workplane:
    t = pp["depth"]
    disc = cq.Workplane("XY").circle(R_DISC).extrude(-t)          # z ∈ [-t, 0]
    # hub boss on the front: cone so pills slide off; carries the D-bore
    boss_h = max(0.0, 8.0 - t)
    if boss_h > 0:
        boss = cq.Workplane("XY").circle(7.0).workplane(offset=boss_h).circle(3.5).loft()
        disc = disc.union(boss)
    for k in range(pp["n"]):
        disc = disc.cut(_extruded_notch(pp, -t - 1, t + 2).rotate((0, 0, 0), (0, 0, 1),
                                                                  k * pp["pitch_deg"]))
    # D-bore through boss and disc
    h_tot = t + boss_h
    bore = (cq.Workplane("XY").workplane(offset=-t - 1).circle(SHAFT_D / 2 + 0.05)
            .extrude(h_tot + 2))
    flat_cut = (cq.Workplane("XY").workplane(offset=-t - 1)
                .center(SHAFT_FLAT - SHAFT_D / 2 + 0.05 + 2, 0).rect(4, 6).extrude(h_tot + 2))
    disc = disc.cut(bore.cut(flat_cut))
    return disc


def _extruded_notch(pp: dict, z0: float, h: float, grow: float = 0.0,
                    outer: float | None = None) -> cq.Workplane:
    """Notch prism from z0 to z0+h."""
    outer = outer if outer is not None else R_WALL + 3
    if pp["shape"] == "round":
        w = pp["width"] + 2 * grow
        rc = pp["r_center"]
        circ = cq.Workplane("XY").workplane(offset=z0).center(rc, 0).circle(w / 2).extrude(h)
        rect = (cq.Workplane("XY").workplane(offset=z0).center((rc + outer) / 2, 0)
                .rect(outer - rc, w).extrude(h))
        return circ.union(rect)
    L = pp["length"] + 2 * grow
    r_in = pp["r_inner"] - grow
    return (cq.Workplane("XY").workplane(offset=z0).center((r_in + outer) / 2, 0)
            .rect(outer - r_in, L).extrude(h)
            .edges("|Z").edges("<X").fillet(min(2.0, pp["width"] / 2 - 0.1)))


def _teardrop_x(x0: float, x1: float, y: float, z: float, r: float) -> cq.Workplane:
    """Horizontal hole along local x that prints without support when the part lies
    front-face (local +z) down on the bed: circle plus a 45° roof toward local −z."""
    prof = (cq.Workplane("YZ").workplane(offset=x0).center(y, z).circle(r).extrude(x1 - x0))
    roof = (cq.Workplane("YZ").workplane(offset=x0)
            .polyline([(y - r * 0.7071, z - r * 0.7071), (y, z - r * 1.6),
                       (y + r * 0.7071, z - r * 0.7071), (y, z)]).close().extrude(x1 - x0))
    return prof.union(roof)


TAB_Y = (-14.0, 14.0)      # local y of the two stand tabs on each side
TAB_W = 8.0                # tab length along x
TAB_DEPTH = 10.0           # tab depth behind the back plate


def backplate_z(pp: dict) -> tuple[float, float]:
    z_front = -pp["depth"] - RUN
    return z_front - BP_T, z_front


def tab_holes_local(pp: dict):
    zb, _ = backplate_z(pp)
    zc = zb - TAB_DEPTH / 2
    return [(sx * (FLANGE_R + TAB_W / 2 - 3), y, zc) for sx in (-1, 1) for y in TAB_Y]


def make_backplate(pp: dict) -> cq.Workplane:
    zb, z_front = backplate_z(pp)
    plate = cq.Workplane("XY").workplane(offset=zb).circle(FLANGE_R).extrude(BP_T)
    plate = plate.cut(cq.Workplane("XY").workplane(offset=zb - 1).circle(2.2).extrude(BP_T + 2))
    # exit hole = notch grown by EXIT_MARGIN, bounded by the hopper bore, continued as a
    # duct straight back (perpendicular to the plate: vertical walls when printed)
    hole = _extruded_notch(pp, zb - DUCT_LEN - 1, BP_T + DUCT_LEN + 2, grow=EXIT_MARGIN,
                           outer=R_WALL).rotate((0, 0, 0), (0, 0, 1), EXIT_ANGLE)
    duct = _extruded_notch(pp, zb - DUCT_LEN, DUCT_LEN, grow=EXIT_MARGIN + 1.6,
                           outer=R_WALL + 1.6).rotate((0, 0, 0), (0, 0, 1), EXIT_ANGLE)
    plate = plate.union(duct).cut(hole)
    # gearbox socket behind the plate + clamp ears (2× M2)
    gw, gh = GEARBOX
    sock_d = 8.0
    outer_w, outer_h = gw + 2 * RUN + 4.8, gh + 2 * RUN + 4.8
    sock = (cq.Workplane("XY").workplane(offset=zb - sock_d).rect(outer_w, outer_h).extrude(sock_d)
            .cut(cq.Workplane("XY").workplane(offset=zb - sock_d - 1)
                 .rect(gw + 2 * RUN, gh + 2 * RUN).extrude(sock_d + 1)))
    ear_x = outer_w / 2 + 3
    ears = (cq.Workplane("XY").workplane(offset=zb - sock_d)
            .pushPoints([(-ear_x, 0), (ear_x, 0)]).rect(6, 6).extrude(sock_d)
            .cut(cq.Workplane("XY").workplane(offset=zb - sock_d - 1)
                 .pushPoints([(-ear_x, 0), (ear_x, 0)]).circle(1.1).extrude(sock_d + 2)))
    plate = plate.union(sock).union(ears)
    # stand tabs: blocks at ±x with M3 teardrop holes along x
    for sx in (-1, 1):
        for y in TAB_Y:
            x0 = sx * (FLANGE_R - 3)
            blk = (cq.Workplane("XY").workplane(offset=zb - TAB_DEPTH)
                   .center(x0 + sx * TAB_W / 2, y).rect(TAB_W, 10).extrude(TAB_DEPTH + BP_T))
            plate = plate.union(blk)
    for (x, y, z) in tab_holes_local(pp):
        plate = plate.cut(_teardrop_x(x - TAB_W, x + TAB_W, y, z, 1.7))
    # M3 holes for the hopper flange: Ø4.0 for heat-set inserts from the back
    holes = (cq.Workplane("XY").workplane(offset=zb - 1)
             .polarArray(BOLT_R, 45, 360, 4).circle(2.0).extrude(BP_T + 2))
    return plate.cut(holes)


def make_hopper(pp: dict) -> cq.Workplane:
    """Bore + flange; printed flange-down. The upper-half cover is a separate part."""
    z0 = -pp["depth"] - RUN
    wall = (cq.Workplane("XY").workplane(offset=z0).circle(R_WALL + WALL).circle(R_WALL)
            .extrude(HOPPER_DEPTH - z0))
    flange = (cq.Workplane("XY").workplane(offset=z0).circle(FLANGE_R).circle(R_WALL)
              .extrude(3.0)
              .cut(cq.Workplane("XY").workplane(offset=z0 - 1)
                   .polarArray(BOLT_R, 45, 360, 4).circle(1.7).extrude(5)))
    return wall.union(flange)


def make_cover() -> cq.Workplane:
    """Half-lid over the upper half of the hopper (y > −2): pills can only be poured into
    the lower half, so nothing lands on the exit side. A 3 mm lip locates it in the bore."""
    plate = (cq.Workplane("XY").workplane(offset=HOPPER_DEPTH).circle(R_WALL + WALL).extrude(2.4))
    lip = (cq.Workplane("XY").workplane(offset=HOPPER_DEPTH - 3).circle(R_WALL - 0.15)
           .circle(R_WALL - 1.75).extrude(3))
    half = (cq.Workplane("XY").workplane(offset=HOPPER_DEPTH - 4)
            .center(0, (R_WALL + WALL + 2) / 2 - 2).rect(2 * (R_WALL + WALL) + 2, R_WALL + WALL + 2)
            .extrude(8))
    return plate.union(lip).intersect(half)


def make_clamp() -> cq.Workplane:
    """Strap that holds the gearbox in its socket (2× M2 × 12 + nuts)."""
    gw, gh = GEARBOX
    outer_w = gw + 2 * RUN + 4.8
    ear_x = outer_w / 2 + 3
    return (cq.Workplane("XY").rect(2 * ear_x + 6, 6).extrude(3.0)
            .cut(cq.Workplane("XY").pushPoints([(-ear_x, 0), (ear_x, 0)]).circle(1.1).extrude(4)))


BASE_Z = -46.0       # world z of the table / base plate top
SIDE_T = 5.0         # side plate thickness


def _world(p_local):
    x, y, z = p_local
    b = math.radians(BETA)
    return (x, math.cos(b) * y - math.sin(b) * z, math.sin(b) * y + math.cos(b) * z)


def make_side(pp_ref: dict) -> cq.Workplane:
    """Side plate (world YZ plane), printed flat. Bolts to two back-plate tabs (M3)
    and slots into the base plate. Built for the thickest disc so every pill fits."""
    pts = [_world(h)[1:] for h in tab_holes_local(pp_ref) if h[0] > 0]
    ys, zs = [p[0] for p in pts], [p[1] for p in pts]
    outline = [(min(ys) - 12, BASE_Z - 3), (max(ys) + 18, BASE_Z - 3),
               (max(ys) + 18, max(zs) + 8), (min(ys) - 2, max(zs) + 14), (min(ys) - 12, min(zs) - 6)]
    x_in = FLANGE_R - 3 + TAB_W + 0.2
    side = (cq.Workplane("YZ").workplane(offset=x_in).polyline(outline).close().extrude(SIDE_T))
    for (y, z) in pts:
        side = side.cut(cq.Workplane("YZ").workplane(offset=x_in - 1).center(y, z).circle(1.7)
                        .extrude(SIDE_T + 2))
    return side


def make_base(pp_ref: dict) -> cq.Workplane:
    """Base plate with two slots for the side plates and a seat for the pill cup."""
    side = make_side(pp_ref)
    bb = side.val().BoundingBox()
    x_in = FLANGE_R - 3 + TAB_W + 0.2
    base = (cq.Workplane("XY").workplane(offset=BASE_Z - 6)
            .center(0, (bb.ymin + bb.ymax) / 2).rect(2 * (x_in + SIDE_T + 8), bb.ylen + 10).extrude(6))
    for sx in (-1, 1):
        x_c = sx * (x_in + SIDE_T / 2)
        base = base.cut(cq.Workplane("XY").workplane(offset=BASE_Z - 3)
                        .center(x_c, (bb.ymin + bb.ymax) / 2).rect(SIDE_T + 0.4, bb.ylen + 0.4)
                        .extrude(4))
    return base


def make_cup(pp_ref: dict) -> cq.Workplane:
    """Pill cup under the exit duct (world). Ø36 × 22 mm, 1.6 mm walls."""
    zb, _ = backplate_z(pp_ref)
    duct_end = _world((pp_ref["r_center"], 0, zb - DUCT_LEN))
    cup = (cq.Workplane("XY").workplane(offset=BASE_Z).center(duct_end[0], duct_end[1] + 4)
           .circle(18).extrude(22)
           .cut(cq.Workplane("XY").workplane(offset=BASE_Z + 1.6).center(duct_end[0], duct_end[1] + 4)
                .circle(16.4).extrude(22)))
    return cup


# ------------------------------------------------------------------ export
def build(pill_id: str) -> dict:
    pp = pocket_params(pill_id)
    out = OUT / pill_id
    out.mkdir(parents=True, exist_ok=True)
    # print_rotation is applied to the world-frame STL to lay the part on the bed
    parts = {
        "disc": (make_disc(pp), [-BETA, 0, 0]),                  # back face on the bed
        "backplate": (make_backplate(pp), [-BETA + 180, 0, 0]),  # front face on the bed
        "hopper": (make_hopper(pp), [-BETA, 0, 0]),              # flange on the bed
    }
    manifest = dict(variant="v2_inclined_disc", pill=pill_id,
                    params=dict(pp, beta=BETA, fdm=FDM, run=RUN, r_disc=R_DISC, r_wall=R_WALL,
                                exit_margin=EXIT_MARGIN, exit_angle=EXIT_ANGLE),
                    parts=[], clearances=[
                        dict(a="disc", b="backplate", min=0.3, what="disc back face over back plate"),
                        dict(a="disc", b="hopper", min=0.3, what="disc rim inside hopper bore")])
    for name, (shape, rot) in parts.items():
        w = _rot_world(shape)
        cq.exporters.export(w, str(out / f"{name}.step"))
        cq.exporters.export(w, str(out / f"{name}.stl"), tolerance=0.02, angularTolerance=0.08)
        manifest["parts"].append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                                      print_rotation=rot))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def build_common():
    """Parts shared by every pill: cover, motor clamp, stand (2 sides + base), cup.
    Sized from the thickest disc (cap0) so they fit every pill's assembly."""
    ref = pocket_params("cap0")
    common = OUT / "common"
    common.mkdir(parents=True, exist_ok=True)
    side = make_side(ref)
    parts = [
        ("cover", _rot_world(make_cover()), [-BETA + 180, 0, 0], 4.0),
        ("clamp", make_clamp(), [0, 0, 0], 4.0),
        ("side_right", side, [0, -90, 0], 4.0),
        ("side_left", side.mirror("YZ"), [0, 90, 0], 4.0),
        ("base", make_base(ref), [0, 0, 0], 4.0),
        ("cup", make_cup(ref), [0, 0, 0], 4.0),
    ]
    man = dict(variant="v2_inclined_disc", pill="common", parts=[], clearances=[])
    for name, shape, rot, ov in parts:
        cq.exporters.export(shape, str(common / f"{name}.step"))
        cq.exporters.export(shape, str(common / f"{name}.stl"), tolerance=0.03)
        man["parts"].append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                                 print_rotation=rot, max_overhang_mm2=ov))
    (common / "manifest.json").write_text(json.dumps(man, indent=2))


if __name__ == "__main__":
    ids = sys.argv[1:] or list(PILLS)
    for pid in ids:
        m = build(pid)
        print(pid, json.dumps(m["params"]))
    if not sys.argv[1:]:
        build_common()
