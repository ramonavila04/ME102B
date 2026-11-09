#!/usr/bin/env python3
"""V3: reciprocating shuttle (scotch-yoke slide) single-pill dispenser.

    python cad/variants/v3_shuttle/build.py [pill ...]      # default: all pills

Writes cad/variants/v3_shuttle/<pill>/ with one STEP + STL per printed part in
assembled position (mm, +z up) and manifest.json for cad/check_printability.py.

Frame (the slide is drawn at mid-stroke, crank angle 0):
  z = 0          slide top
  z = +GAP       underside of the hopper's cover plate (and top of the guide rails)
  z = -D         floor top (the pocket's bottom); D = pocket depth
  x = 0          pocket centre at mid-stroke; fill at x = -R, drop at x = +R
  slide x = R*sin(theta); theta = -90 deg is the fill position.

Pill path: hopper -> throat (x = -R) -> pocket in the slide -> drop hole in the
floor plate (x = +R) -> chute. Everything else is closed off by 0.4 mm running gaps.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from sim.pills import PILLS  # noqa: E402

# ------------------------------------------------------------------ constants
GAP = 0.4            # running clearance slide <-> cover / floor / rails (per side)
CL = 0.4             # pocket clearance per side beyond the largest pill
DEPTH_MARGIN = 0.35  # seated (largest) pill top sits this far below the slide top
R = 14.0             # crank radius = half stroke
X_CRANK = -52.0      # crank axis (and yoke slot) x
SLIDE_W = 44.0       # slide width (y)
SLIDE_X = (-72.0, 24.0)
BASE_X = (-88.0, 40.0)
RAIL_W = 7.0
FLOOR_T = 3.0
COVER_T = 3.0
HOPPER_WALL = 2.0
WALL_ANG_X = 60.0    # hopper walls (deg from horizontal) on the +-x sides (stroke direction)
WALL_ANG_Y = 70.0    # hopper walls on the +-y sides
HOPPER_H = 40.0      # sloped part, above the cover underside
HOPPER_EXT = 20.0    # vertical extension above the slope
DROP_E = 1.5         # drop hole = pocket outline grown by this
CHUTE_E = 1.0        # chute bore = drop hole grown by this (no ledge to catch a pill)
CHUTE_L = 25.0
THROAT_G_ENTRY = 0.8  # throat margin behind the pocket's chamfered trailing edge at fill
THROAT_G_EXIT = 0.8   # throat margin ahead of the pocket's leading edge at fill
PIN_D = 5.0
PIN_CL = 0.35
DISC_R = R + PIN_D / 2 + 2.0
DISC_T = 3.0
HUB_R = 4.5
SHAFT_D, SHAFT_FLAT, SHAFT_LEN = 3.0, 2.5, 10.0   # Pololu micro metal gearmotor D-shaft
GEARBOX_X, GEARBOX_Y = 12.0, 10.0                  # gearbox cross-section (12 x 10 mm)
M3_PILOT, M3_CLEAR, M2_PILOT, M2_CLEAR = 2.5, 3.4, 1.7, 2.4
CLAMP_SCREW_Y = GEARBOX_Y / 2 + 3.0   # M2 screw line, 3 mm outboard of the gearbox face
RAIL_Y = SLIDE_W / 2 + GAP + RAIL_W / 2            # screw line along the rails
COVER_SCREW_X = (-84.0, -40.0, 36.0)
MOUNT_SCREW_DX = 24.0
CHUTE_SCREW_X = R
PLA_DENSITY = 1.24e-3  # g/mm^3


@dataclass
class Params:
    pill: str
    shape: str          # "round" | "slot"
    pocket_x: float     # pocket size along the stroke (x)
    pocket_y: float     # pocket size across the stroke (y)
    depth: float        # D: slide top to floor top
    chamfer: float      # 45 deg trailing-edge chamfer depth (lifts a protruding pill out)
    slide_t: float
    throat_x0: float
    throat_x1: float
    throat_y: float
    drop_x: float
    drop_y: float
    z_floor_bot: float


def params(pill_id: str) -> Params:
    p = PILLS[pill_id]
    tmax = p.thickness + p.tol
    tmin = p.thickness - p.tol
    if p.kind == "tablet":
        shape = "round"
        px = py = p.length + p.tol + 2 * CL
        depth = tmax + DEPTH_MARGIN
    else:
        # long axis across the stroke; deep enough that a caplet on its side also sits below the top
        shape = "slot"
        px = p.width + p.tol + 2 * CL
        py = p.length + p.tol_length + 2 * CL
        depth = max(tmax, p.width + p.tol) + DEPTH_MARGIN
    # a second pill resting on the seated one (or nested beside it) dips at most depth - tmin
    # below the slide top; the chamfer must reach deeper so the trailing wall can only touch
    # it on the 45 deg face.
    chamfer = max(1.2, depth - tmin + 0.6)
    if p.kind == "capsule":
        chamfer = max(chamfer, 2.5)
    x_fill = -R
    throat_x0 = x_fill - px / 2 - chamfer - THROAT_G_ENTRY
    throat_x1 = x_fill + px / 2 + THROAT_G_EXIT
    throat_y = py + (6.0 if shape == "round" else 2.0)
    # the pocket must never connect throat and drop hole
    hole_x0 = R - px / 2 - DROP_E
    assert hole_x0 - px - chamfer > throat_x1 + 2.0, "stroke too short for this pocket"
    return Params(pill_id, shape, px, py, depth, chamfer, depth - GAP, throat_x0, throat_x1,
                  throat_y, px + 2 * DROP_E, py + 2 * DROP_E, -depth - FLOOR_T)


# ------------------------------------------------------------------ helpers
def box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def outline(wp: cq.Workplane, shape: str, sx: float, sy: float) -> cq.Workplane:
    if shape == "round":
        return wp.circle(sx / 2)
    return wp.slot2D(max(sx, sy), min(sx, sy), 90 if sy >= sx else 0)


def prism(shape, sx, sy, cx, cy, z0, z1, taper=0.0) -> cq.Workplane:
    wp = cq.Workplane("XY").workplane(offset=z0).center(cx, cy)
    return outline(wp, shape, sx, sy).extrude(z1 - z0, taper=taper)


def teardrop_z(x, y, d, z0, z1, point=(0, 1)) -> cq.Workplane:
    """Vertical hole that prints support-free when the part is laid with +y up."""
    r = d / 2
    tip = r * math.sqrt(2)
    c = cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)
    tri = (cq.Workplane("XY").workplane(offset=z0)
           .polyline([(x - r / math.sqrt(2), y + r / math.sqrt(2)), (x, y + tip),
                      (x + r / math.sqrt(2), y + r / math.sqrt(2))]).close().extrude(z1 - z0))
    return c.union(tri)


def frustum(xc, z0, w0, l0, z1, ax, ay) -> cq.Workplane:
    """Rectangular frustum: w0 x l0 at z0, walls at ax (x sides) / ay (y sides) deg from horizontal."""
    h = z1 - z0
    w1 = w0 + 2 * h / math.tan(math.radians(ax))
    l1 = l0 + 2 * h / math.tan(math.radians(ay))
    return (cq.Workplane("XY").workplane(offset=z0).center(xc, 0).rect(w0, l0)
            .workplane(offset=h).rect(w1, l1).loft(combine=True))


# ------------------------------------------------------------------ parts
def slide(P: Params) -> cq.Workplane:
    s = box(*SLIDE_X, -SLIDE_W / 2, SLIDE_W / 2, -P.slide_t, 0.0)
    s = s.cut(prism(P.shape, P.pocket_x, P.pocket_y, 0, 0, -P.slide_t - 1, 1))
    # 45 deg chamfer on the trailing (-x) half of the pocket rim only
    cham = prism(P.shape, P.pocket_x, P.pocket_y, 0, 0, -P.chamfer, 0.0, taper=-45)
    cham = cham.intersect(box(-40, 0, -40, 40, -P.chamfer - 1, 1))
    s = s.cut(cham)
    # yoke slot across the stroke for the crank pin
    slot_len = 2 * R + PIN_D + 2 * PIN_CL
    s = s.cut(cq.Workplane("XY").workplane(offset=-P.slide_t - 1).center(X_CRANK, 0)
              .slot2D(slot_len, PIN_D + 2 * PIN_CL, 90).extrude(P.slide_t + 2))
    return s


def guide_base(P: Params) -> cq.Workplane:
    y_in = SLIDE_W / 2 + GAP
    y_out = y_in + RAIL_W
    b = box(*BASE_X, -y_out, y_out, P.z_floor_bot, -P.depth)
    for sgn in (-1, 1):
        y0, y1 = sorted((sgn * y_in, sgn * y_out))
        b = b.union(box(*BASE_X, y0, y1, -P.depth - 0.01, GAP))
    # drop hole: the pocket outline grown by DROP_E all round
    b = b.cut(prism(P.shape, P.drop_x, P.drop_y, R, 0, P.z_floor_bot - 1, 1))
    # crank pin / hub sweep
    b = b.cut(cq.Workplane("XY").workplane(offset=P.z_floor_bot - 1).center(X_CRANK, 0)
              .circle(R + PIN_D / 2 + 1.0).extrude(FLOOR_T + 2))
    for x in COVER_SCREW_X + (X_CRANK - MOUNT_SCREW_DX, X_CRANK + MOUNT_SCREW_DX, CHUTE_SCREW_X):
        for y in (-RAIL_Y, RAIL_Y):
            b = b.cut(cq.Workplane("XY").workplane(offset=P.z_floor_bot - 1).center(x, y)
                      .circle(M3_PILOT / 2).extrude(P.depth + FLOOR_T + 3))
    return b


def hopper(P: Params) -> cq.Workplane:
    y_out = SLIDE_W / 2 + GAP + RAIL_W
    xc = (P.throat_x0 + P.throat_x1) / 2
    wt = P.throat_x1 - P.throat_x0
    lt = P.throat_y
    z0, z1 = GAP, GAP + HOPPER_H
    plate = box(*BASE_X, -y_out, y_out, GAP, GAP + COVER_T)
    dx = HOPPER_WALL / math.sin(math.radians(WALL_ANG_X))
    dy = HOPPER_WALL / math.sin(math.radians(WALL_ANG_Y))
    outer = frustum(xc, GAP + COVER_T - 0.5, wt + 2 * dx + 2 * (COVER_T - 0.5) / math.tan(math.radians(WALL_ANG_X)),
                    lt + 2 * dy + 2 * (COVER_T - 0.5) / math.tan(math.radians(WALL_ANG_Y)), z1, WALL_ANG_X, WALL_ANG_Y)
    w1 = wt + 2 * HOPPER_H / math.tan(math.radians(WALL_ANG_X))
    l1 = lt + 2 * HOPPER_H / math.tan(math.radians(WALL_ANG_Y))
    ext_o = box(xc - w1 / 2 - dx, xc + w1 / 2 + dx, -l1 / 2 - dy, l1 / 2 + dy, z1 - 0.01, z1 + HOPPER_EXT)
    ext_i = box(xc - w1 / 2, xc + w1 / 2, -l1 / 2, l1 / 2, z1 - 0.02, z1 + HOPPER_EXT + 1)
    # inner cavity: starts 1 mm below the cover underside so the throat edge is cut cleanly
    inner = frustum(xc, z0 - 1.0, wt - 2 / math.tan(math.radians(WALL_ANG_X)),
                    lt - 2 / math.tan(math.radians(WALL_ANG_Y)), z1 + 0.01, WALL_ANG_X, WALL_ANG_Y)
    h = plate.union(outer).union(ext_o).cut(inner).cut(ext_i)
    for x in COVER_SCREW_X:
        for y in (-RAIL_Y, RAIL_Y):
            h = h.cut(cq.Workplane("XY").workplane(offset=GAP - 1).center(x, y)
                      .circle(M3_CLEAR / 2).extrude(COVER_T + 2))
    return h


def chute(P: Params) -> cq.Workplane:
    y_out = SLIDE_W / 2 + GAP + RAIL_W
    bx, by = P.drop_x + 2 * CHUTE_E, P.drop_y + 2 * CHUTE_E
    zt = P.z_floor_bot
    fl = box(R - bx / 2 - HOPPER_WALL - 4, R + bx / 2 + HOPPER_WALL + 4, -y_out, y_out, zt - 3, zt)
    tube = prism(P.shape, bx + 2 * HOPPER_WALL, by + 2 * HOPPER_WALL, R, 0, zt - 3 - CHUTE_L, zt - 2.9)
    c = fl.union(tube).cut(prism(P.shape, bx, by, R, 0, zt - 4 - CHUTE_L, zt + 1))
    for y in (-RAIL_Y, RAIL_Y):
        c = c.cut(cq.Workplane("XY").workplane(offset=zt - 4).center(CHUTE_SCREW_X, y)
                  .circle(M3_CLEAR / 2).extrude(5))
    return c


def crank_z(P: Params):
    disc_top = P.z_floor_bot - 0.6
    return disc_top - DISC_T, disc_top


def crank(P: Params) -> cq.Workplane:
    """Disc on the gearmotor D-shaft with the yoke pin at radius R (drawn at theta = 0)."""
    z0, z1 = crank_z(P)
    hub_top = -P.depth           # 0.4 below the slide's underside
    c = cq.Workplane("XY").workplane(offset=z0).center(X_CRANK, 0).circle(DISC_R).extrude(DISC_T)
    c = c.union(cq.Workplane("XY").workplane(offset=z1 - 0.01).center(X_CRANK, 0)
                .circle(HUB_R).extrude(hub_top - z1 + 0.01))
    # pin at theta = 0: x = X_CRANK + R sin(0), y = +R cos(0)
    c = c.union(cq.Workplane("XY").workplane(offset=z1 - 0.01).center(X_CRANK, R)
                .circle(PIN_D / 2).extrude(-GAP - z1 + 0.01))
    # D bore (0.1 mm interference-free fit), through
    bore = (cq.Workplane("XY").workplane(offset=z0 - 1).center(X_CRANK, 0)
            .circle(SHAFT_D / 2 + 0.05).extrude(hub_top - z0 + 2))
    flat = box(X_CRANK - 5, X_CRANK + 5, -5 + SHAFT_FLAT - SHAFT_D / 2 + 0.05, 5, z0 - 2, hub_top + 2)
    c = c.cut(bore.cut(flat))
    return c


def motor_z(P: Params):
    """Gearbox face height: the shaft tip ends 0.3 mm inside the top of the hub."""
    return -P.depth - 0.3 - SHAFT_LEN


def motor_mount(P: Params) -> cq.Workplane:
    """C-frame hanging under the base: top plate on the rails (2x M3), back wall at -y, a bottom
    plate with a U slot the gearbox slides into from +y; the clamp bar closes it (2x M2)."""
    zt = P.z_floor_bot
    zg = motor_z(P)
    y_out = SLIDE_W / 2 + GAP + RAIL_W
    xa, xb = X_CRANK - 28, X_CRANK + 28
    zb0, zb1 = zg - 12, zg - 6          # bottom plate
    top = box(xa, xb, -y_out, y_out, zt - 3, zt)
    # disc clearance: circle + slot open to +y
    top = top.cut(cq.Workplane("XY").workplane(offset=zt - 4).center(X_CRANK, 0)
                  .circle(DISC_R + 1.5).extrude(5))
    top = top.cut(box(X_CRANK - DISC_R - 1.5, X_CRANK + DISC_R + 1.5, 0, y_out + 1, zt - 4, zt + 1))
    back = box(xa, xb, -y_out, -y_out + 3, zb0, zt)
    sides = box(xa, xa + 3, -y_out, 14, zb0, zt).union(box(xb - 3, xb, -y_out, 14, zb0, zt))
    bottom = box(xa, xb, -y_out, 14, zb0, zb1)
    m = top.union(back).union(sides).union(bottom)
    # gearbox U slot (open to +y); the gearbox's -y face seats on the slot end
    m = m.cut(box(X_CRANK - GEARBOX_X / 2 - 0.15, X_CRANK + GEARBOX_X / 2 + 0.15, -GEARBOX_Y / 2 - 0.15, 15, zb0 - 1, zb1 + 1))
    for sx in (-1, 1):
        m = m.cut(teardrop_z(X_CRANK + sx * MOUNT_SCREW_DX, -RAIL_Y, M3_CLEAR, zt - 4, zt + 1))
        m = m.cut(teardrop_z(X_CRANK + sx * MOUNT_SCREW_DX, RAIL_Y, M3_CLEAR, zt - 4, zt + 1))
        m = m.cut(teardrop_z(X_CRANK + sx * 10.0, CLAMP_SCREW_Y, M2_PILOT, zb0 - 1, zb1 + 1))
    return m


def motor_clamp(P: Params) -> cq.Workplane:
    """Bar across the U slot pressing the gearbox's +y face; 2x M2 into the bottom plate."""
    zg = motor_z(P)
    z0, z1 = zg - 6, zg - 2
    y0 = GEARBOX_Y / 2 + 0.05     # 0.1 mm pre-load gap closed by the screws
    c = box(X_CRANK - 14, X_CRANK + 14, y0, y0 + 6.0, z0, z1)
    # bar sits on the bottom plate top (z = zg - 6)
    for sx in (-1, 1):
        c = c.cut(cq.Workplane("XY").workplane(offset=z0 - 1).center(X_CRANK + sx * 10.0, CLAMP_SCREW_Y)
                  .circle(M2_CLEAR / 2).extrude(z1 - z0 + 2))
    return c


PARTS = {
    # name: (builder, print rotation (deg, xyz), note)
    "slide": (slide, [0, 0, 0], "flat, underside on the bed"),
    "guide_base": (guide_base, [0, 0, 0], "floor underside on the bed"),
    "hopper": (hopper, [0, 0, 0], "cover-plate underside on the bed"),
    "chute": (chute, [180, 0, 0], "flange on the bed"),
    "crank": (crank, [0, 0, 0], "disc on the bed, pin and hub up"),
    "motor_mount": (motor_mount, [90, 0, 0], "back wall (-y face) on the bed"),
    "motor_clamp": (motor_clamp, [0, 0, 0], "flat"),
}

CLEARANCES = [
    ("slide", "guide_base", 0.3, "slide in the guide channel (floor + rails), 0.4 mm modelled"),
    ("slide", "hopper", 0.3, "slide top under the cover plate / throat edges, 0.4 mm modelled"),
    ("slide", "crank", 0.3, "crank pin in the yoke slot; hub under the slide"),
    ("crank", "guide_base", 0.3, "crank disc under the floor; pin and hub in the floor opening"),
    ("crank", "motor_mount", 0.3, "crank disc inside the mount's top plate"),
    ("crank", "motor_clamp", 0.3, "crank disc above the clamp bar"),
]


def build(pill_id: str) -> dict:
    P = params(pill_id)
    out = HERE / pill_id
    out.mkdir(parents=True, exist_ok=True)
    parts_meta = []
    volumes = {}
    for name, (fn, rot, note) in PARTS.items():
        wp = fn(P)
        solid = wp.val()
        if not solid.isValid():
            raise RuntimeError(f"{name}: invalid solid")
        volumes[name] = solid.Volume()
        cq.exporters.export(wp, str(out / f"{name}.step"))
        cq.exporters.export(wp, str(out / f"{name}.stl"), tolerance=0.01, angularTolerance=0.1)
        parts_meta.append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                               print_rotation=rot, print_note=note, min_wall=1.2))
    manifest = dict(
        variant="v3_shuttle", pill=pill_id, parts=parts_meta,
        clearances=[dict(a=a, b=b, min=m, what=w) for a, b, m, w in CLEARANCES],
        params=dict(asdict(P), crank_r=R, x_crank=X_CRANK, gap=GAP, pocket_clearance=CL,
                    slide_mass_g=round(volumes["slide"] * PLA_DENSITY, 2),
                    wall_angle_x=WALL_ANG_X, wall_angle_y=WALL_ANG_Y, hopper_h=HOPPER_H,
                    hopper_ext=HOPPER_EXT, hopper_wall=HOPPER_WALL,
                    z_crank=crank_z(P), z_gearbox_face=motor_z(P)),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    for pid in (sys.argv[1:] or list(PILLS)):
        m = build(pid)
        print(pid, json.dumps({k: (round(v, 3) if isinstance(v, float) else v)
                               for k, v in m["params"].items()}))
