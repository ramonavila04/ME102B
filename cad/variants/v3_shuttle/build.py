#!/usr/bin/env python3
"""V3: reciprocating shuttle (scotch-yoke slide) single-pill dispenser.

    python cad/variants/v3_shuttle/build.py [pill ...]      # default: all pills

Writes cad/variants/v3_shuttle/<pill>/ with one STEP + STL per printed part in
assembled position (mm, +z up) and manifest.json for cad/check_printability.py.

Frame (the slide is drawn at mid-stroke, crank angle 0):
  z = 0          slide top
  z = +GAP       underside of the hopper's cover plate (and top of the guide rails)
  z = -D         floor top (the pocket's seat); D = pocket depth
  x = 0          seat centre at mid-stroke; fill at x = -R, drop at x = +R
  slide x = R*sin(theta); theta = -90 deg is the fill position, +x is the dispense stroke.

Pill path: hopper -> throat (x = -R) -> pocket in the slide -> drop hole in the
floor plate (x = +R) -> chute. Everything else is closed off by 0.4 mm running gaps.

Pocket = a seat one pill wide (vertical leading wall at +x) plus a shallow RAMP on the
trailing (-x) side that rises from the floor to the slide top at RAMP_ANG. A pill that
sticks out of the pocket when it reaches the throat's exit edge is squeezed between that
edge and the ramp; the two contact planes include >= 90 - RAMP_ANG = 70 deg, more than
2*atan(0.6) = 62 deg, so it is lifted out instead of wedging -- even a tablet standing on
edge, whose flat face meets the knife edge with a horizontal normal.
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
CL = 0.4             # seat clearance per side beyond the largest pill
DEPTH_MARGIN = 0.35  # seated (largest) pill top sits this far below the slide top
RAMP_ANG = 20.0      # trailing ramp, deg from horizontal
RAMP_FOOT_MARGIN = 0.3  # the knife edge meets a pill on the ramp this far below the pill's mid-height
RAMP_ON_STEP = False     # r3 (True): ramp starts on a step; r2 (False): ramp starts at the floor
RAIL_W = 7.0
FLOOR_T = 3.0
COVER_T = 3.0
HOPPER_WALL = 2.0
WALL_ANG_X = 60.0    # hopper walls (deg from horizontal) on the +-x sides (stroke direction)
WALL_ANG_Y = 70.0    # hopper walls on the +-y sides
HOPPER_H = 40.0      # sloped part, above the cover underside
HOPPER_EXT = 20.0    # vertical extension above the slope
DROP_E = 1.5         # drop hole = seat outline grown by this
CHUTE_E = 1.0        # chute bore = drop hole grown by this (no ledge to catch a pill)
CHUTE_L = 25.0
THROAT_G_ENTRY = 0.8  # throat margin behind the seat's trailing edge at fill (the ramp is under the cover)
THROAT_G_EXIT = 3.0   # throat margin ahead of the seat's leading wall at fill
SEAL_MARGIN = 3.0     # pocket never open to throat and drop hole together, by this much
PIN_D = 5.0
PIN_CL = 0.35
DISC_T = 3.0
HUB_R = 4.5
SHAFT_D, SHAFT_FLAT, SHAFT_LEN = 3.0, 2.5, 10.0   # Pololu micro metal gearmotor D-shaft
GEARBOX_X, GEARBOX_Y = 12.0, 10.0                  # gearbox cross-section (12 x 10 mm)
M3_PILOT, M3_CLEAR, M2_PILOT, M2_CLEAR = 2.5, 3.4, 1.7, 2.4
CLAMP_SCREW_Y = GEARBOX_Y / 2 + 3.0   # M2 screw line, 3 mm outboard of the gearbox face
PLA_DENSITY = 1.24e-3  # g/mm^3


@dataclass
class Params:
    pill: str
    shape: str          # "round" | "slot"
    seat_x: float       # seat size along the stroke (x)
    seat_y: float       # seat size across the stroke (y)
    depth: float        # D: slide top to floor top
    ramp_len: float     # horizontal length of the trailing ramp
    z_ramp_foot: float  # the ramp starts here, on top of a vertical step up from the floor
    slide_t: float
    crank_r: float
    throat_x0: float
    throat_x1: float
    throat_y: float
    z_floor_bot: float
    x_crank: float
    slide_x0: float
    slide_x1: float
    slide_w: float
    base_x0: float
    base_x1: float
    disc_r: float

    @property
    def y_rail_in(self):
        return self.slide_w / 2 + GAP

    @property
    def y_out(self):
        return self.slide_w / 2 + GAP + RAIL_W

    @property
    def rail_y(self):
        return self.slide_w / 2 + GAP + RAIL_W / 2


def params(pill_id: str) -> Params:
    p = PILLS[pill_id]
    tmax = p.thickness + p.tol
    if p.kind == "tablet":
        shape = "round"
        sx = sy = p.length + p.tol + 2 * CL
        depth = tmax + DEPTH_MARGIN
    else:
        # long axis across the stroke; deep enough that a caplet on its side also sits below the top
        shape = "slot"
        sx = p.width + p.tol + 2 * CL
        sy = p.length + p.tol_length + 2 * CL
        depth = max(tmax, p.width + p.tol) + DEPTH_MARGIN
    # r3: a pill lying on the ramp must meet the knife edge (z = GAP) below its own mid-height,
    # so the edge pushes it up; the ramp therefore starts on a step, not at the floor.
    tmin = p.thickness - p.tol
    z_foot = max(-depth, GAP - tmin / 2 + RAMP_FOOT_MARGIN) if RAMP_ON_STEP else -depth
    ramp = -z_foot / math.tan(math.radians(RAMP_ANG))
    # stroke: the pocket mouth (ramp + seat) must be closed by the cover before the seat
    # opens onto the drop hole:  2R >= 2*sx + ramp + g_exit + e + margin
    R = math.ceil((2 * sx + ramp + THROAT_G_EXIT + DROP_E + SEAL_MARGIN) / 2)
    # r2: the throat exposes only the seat; at fill the ramp lies under the entry-side cover, so
    # pills pushed against the entry wall on the return stroke drop straight into the seat.
    throat_x0 = -R - sx / 2 - THROAT_G_ENTRY
    throat_x1 = -R + sx / 2 + THROAT_G_EXIT
    throat_y = sy + (6.0 if shape == "round" else 2.0)
    disc_r = R + PIN_D / 2 + 2.0
    # yoke: clear of the pocket in the slide, and never under the throat
    x_crank = min(throat_x0 - R - PIN_D - 6.0, -sx / 2 - ramp - PIN_D - 8.0)
    slide_x0 = x_crank - PIN_D - 6.0
    slide_x1 = sx / 2 + 6.0
    slide_w = max(44.0, 2 * R + PIN_D + 2 * PIN_CL + 10.0, sy + 2 * DROP_E + 2 * CHUTE_E + 10.0)
    base_x0 = slide_x0 - R - 2.0
    base_x1 = slide_x1 + R + 2.0
    return Params(pill_id, shape, sx, sy, depth, ramp, z_foot, depth - GAP, R, throat_x0, throat_x1,
                  throat_y, -depth - FLOOR_T, x_crank, slide_x0, slide_x1, slide_w,
                  base_x0, base_x1, disc_r)


def cover_screw_x(P: Params):
    return (P.base_x0 + 4.0, P.x_crank + P.disc_r + 12.0, P.base_x1 - 4.0)


def mount_screw_x(P: Params):
    return (P.x_crank - P.disc_r - 5.5, P.x_crank + P.disc_r + 5.5)


# ------------------------------------------------------------------ helpers
def box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def outline(wp: cq.Workplane, shape: str, sx: float, sy: float) -> cq.Workplane:
    if shape == "round":
        return wp.circle(sx / 2)
    return wp.slot2D(max(sx, sy), min(sx, sy), 90 if sy >= sx else 0)


def prism(shape, sx, sy, cx, cy, z0, z1) -> cq.Workplane:
    wp = cq.Workplane("XY").workplane(offset=z0).center(cx, cy)
    return outline(wp, shape, sx, sy).extrude(z1 - z0)


def seat_prism(P: Params, grow: float, cx: float, z0: float, z1: float) -> cq.Workplane:
    """Seat footprint grown by `grow`: the pill outline with its trailing half squared off
    (the ramp starts along a straight line at x = cx - seat_x/2)."""
    sx, sy = P.seat_x + 2 * grow, P.seat_y + 2 * grow
    s = prism(P.shape, sx, sy, cx, 0, z0, z1)
    return s.union(box(cx - sx / 2, cx, -sy / 2, sy / 2, z0, z1))


def teardrop_z(x, y, d, z0, z1) -> cq.Workplane:
    """Vertical hole that prints support-free when the part is laid with +y up."""
    r = d / 2
    c = cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)
    a = math.radians(35.0)   # tangent point; the tip's flanks are 55 deg from horizontal
    tri = (cq.Workplane("XY").workplane(offset=z0)
           .polyline([(x - r * math.cos(a), y + r * math.sin(a)), (x, y + r / math.sin(a)),
                      (x + r * math.cos(a), y + r * math.sin(a))]).close().extrude(z1 - z0))
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
    t = P.slide_t
    s = box(P.slide_x0, P.slide_x1, -P.slide_w / 2, P.slide_w / 2, -t, 0.0)
    s = s.cut(seat_prism(P, 0.0, 0.0, -t - 1, 1))
    # ramp: everything above the plane through the seat's trailing floor line, rising to -x
    x_foot = -P.seat_x / 2
    y_half = P.seat_y / 2
    L = P.ramp_len + 2.0
    a = math.radians(RAMP_ANG)
    wedge = (cq.Workplane("XZ")
             .polyline([(x_foot, P.z_ramp_foot), (x_foot - L, P.z_ramp_foot + L * math.tan(a)),
                        (x_foot - L, 2.0), (x_foot + 0.01, 2.0), (x_foot + 0.01, P.z_ramp_foot)]).close()
             .extrude(y_half, both=True))
    s = s.cut(wedge)
    # yoke slot across the stroke for the crank pin
    slot_len = 2 * P.crank_r + PIN_D + 2 * PIN_CL
    s = s.cut(cq.Workplane("XY").workplane(offset=-t - 1).center(P.x_crank, 0)
              .slot2D(slot_len, PIN_D + 2 * PIN_CL, 90).extrude(t + 2))
    return s


def guide_base(P: Params) -> cq.Workplane:
    b = box(P.base_x0, P.base_x1, -P.y_out, P.y_out, P.z_floor_bot, -P.depth)
    for sgn in (-1, 1):
        y0, y1 = sorted((sgn * P.y_rail_in, sgn * P.y_out))
        b = b.union(box(P.base_x0, P.base_x1, y0, y1, -P.depth - 0.01, GAP))
    b = b.cut(seat_prism(P, DROP_E, P.crank_r, P.z_floor_bot - 1, 1))
    # crank pin / hub sweep
    b = b.cut(cq.Workplane("XY").workplane(offset=P.z_floor_bot - 1).center(P.x_crank, 0)
              .circle(P.crank_r + PIN_D / 2 + 1.0).extrude(FLOOR_T + 2))
    for x in cover_screw_x(P) + mount_screw_x(P) + (P.crank_r,):
        for y in (-P.rail_y, P.rail_y):
            b = b.cut(cq.Workplane("XY").workplane(offset=P.z_floor_bot - 1).center(x, y)
                      .circle(M3_PILOT / 2).extrude(P.depth + FLOOR_T + 3))
    return b


def hopper(P: Params) -> cq.Workplane:
    xc = (P.throat_x0 + P.throat_x1) / 2
    wt = P.throat_x1 - P.throat_x0
    lt = P.throat_y
    tx, ty = math.tan(math.radians(WALL_ANG_X)), math.tan(math.radians(WALL_ANG_Y))
    z1 = GAP + HOPPER_H
    plate = box(P.base_x0, P.base_x1, -P.y_out, P.y_out, GAP, GAP + COVER_T)
    dx = HOPPER_WALL / math.sin(math.radians(WALL_ANG_X))
    dy = HOPPER_WALL / math.sin(math.radians(WALL_ANG_Y))
    zo = GAP + COVER_T - 0.5
    outer = frustum(xc, zo, wt + 2 * dx + 2 * (zo - GAP) / tx, lt + 2 * dy + 2 * (zo - GAP) / ty,
                    z1, WALL_ANG_X, WALL_ANG_Y)
    w1 = wt + 2 * HOPPER_H / tx
    l1 = lt + 2 * HOPPER_H / ty
    ext_o = box(xc - w1 / 2 - dx, xc + w1 / 2 + dx, -l1 / 2 - dy, l1 / 2 + dy, z1 - 0.01, z1 + HOPPER_EXT)
    ext_i = box(xc - w1 / 2, xc + w1 / 2, -l1 / 2, l1 / 2, z1 - 0.02, z1 + HOPPER_EXT + 1)
    # inner cavity: starts 1 mm below the cover underside so the throat edge is cut cleanly
    inner = frustum(xc, GAP - 1.0, wt - 2 / tx, lt - 2 / ty, z1 + 0.01, WALL_ANG_X, WALL_ANG_Y)
    h = plate.union(outer).union(ext_o).cut(inner).cut(ext_i)
    for x in cover_screw_x(P):
        for y in (-P.rail_y, P.rail_y):
            h = h.cut(cq.Workplane("XY").workplane(offset=GAP - 1).center(x, y)
                      .circle(M3_CLEAR / 2).extrude(COVER_T + 2))
    return h


def chute(P: Params) -> cq.Workplane:
    zt = P.z_floor_bot
    R = P.crank_r
    g = DROP_E + CHUTE_E
    half_x = P.seat_x / 2 + g + HOPPER_WALL
    fl = box(R - half_x - 4, R + half_x + 4, -P.y_out, P.y_out, zt - 3, zt)
    tube = seat_prism(P, g + HOPPER_WALL, R, zt - 3 - CHUTE_L, zt - 2.9)
    c = fl.union(tube).cut(seat_prism(P, g, R, zt - 4 - CHUTE_L, zt + 1))
    for y in (-P.rail_y, P.rail_y):
        c = c.cut(cq.Workplane("XY").workplane(offset=zt - 4).center(R, y)
                  .circle(M3_CLEAR / 2).extrude(5))
    return c


def crank_z(P: Params):
    disc_top = P.z_floor_bot - 0.6
    return disc_top - DISC_T, disc_top


def crank(P: Params) -> cq.Workplane:
    """Disc on the gearmotor D-shaft with the yoke pin at radius R (drawn at theta = 0)."""
    z0, z1 = crank_z(P)
    xc, R = P.x_crank, P.crank_r
    hub_top = -P.depth           # 0.4 below the slide's underside
    c = cq.Workplane("XY").workplane(offset=z0).center(xc, 0).circle(P.disc_r).extrude(DISC_T)
    c = c.union(cq.Workplane("XY").workplane(offset=z1 - 0.01).center(xc, 0)
                .circle(HUB_R).extrude(hub_top - z1 + 0.01))
    # pin at theta = 0: x = x_crank + R sin(0), y = +R cos(0)
    c = c.union(cq.Workplane("XY").workplane(offset=z1 - 0.01).center(xc, R)
                .circle(PIN_D / 2).extrude(-GAP - z1 + 0.01))
    bore = (cq.Workplane("XY").workplane(offset=z0 - 1).center(xc, 0)
            .circle(SHAFT_D / 2 + 0.05).extrude(hub_top - z0 + 2))
    flat = box(xc - 5, xc + 5, -5 + SHAFT_FLAT - SHAFT_D / 2 + 0.05, 5, z0 - 2, hub_top + 2)
    return c.cut(bore.cut(flat))


def motor_z(P: Params):
    """Gearbox face height: the shaft tip ends 0.3 mm inside the top of the hub."""
    return -P.depth - 0.3 - SHAFT_LEN


def motor_mount(P: Params) -> cq.Workplane:
    """C-frame hanging under the base: top plate on the rails (2x M3), back wall at -y, a bottom
    plate with a U slot the gearbox slides into from +y; the clamp bar closes it (2x M2)."""
    zt = P.z_floor_bot
    zg = motor_z(P)
    xc = P.x_crank
    ext = P.disc_r + 9.5
    xa, xb = xc - ext, xc + ext
    zb0, zb1 = zg - 12, zg - 6          # bottom plate
    top = box(xa, xb, -P.y_out, P.y_out, zt - 3, zt)
    top = top.cut(cq.Workplane("XY").workplane(offset=zt - 4).center(xc, 0)
                  .circle(P.disc_r + 1.5).extrude(5))
    top = top.cut(box(xc - P.disc_r - 1.5, xc + P.disc_r + 1.5, 0, P.y_out + 1, zt - 4, zt + 1))
    back = box(xa, xb, -P.y_out, -P.y_out + 3, zb0, zt)
    sides = box(xa, xa + 3, -P.y_out, 14, zb0, zt).union(box(xb - 3, xb, -P.y_out, 14, zb0, zt))
    bottom = box(xa, xb, -P.y_out, 14, zb0, zb1)
    m = top.union(back).union(sides).union(bottom)
    m = m.cut(box(xc - GEARBOX_X / 2 - 0.15, xc + GEARBOX_X / 2 + 0.15, -GEARBOX_Y / 2 - 0.15, 15,
                  zb0 - 1, zb1 + 1))
    for x in mount_screw_x(P):
        for y in (-P.rail_y, P.rail_y):
            m = m.cut(teardrop_z(x, y, M3_CLEAR, zt - 4, zt + 1))
    for sx in (-1, 1):
        m = m.cut(teardrop_z(xc + sx * 10.0, CLAMP_SCREW_Y, M2_PILOT, zb0 - 1, zb1 + 1))
    return m


def motor_clamp(P: Params) -> cq.Workplane:
    """Bar across the U slot pressing the gearbox's +y face; 2x M2 into the bottom plate."""
    zg = motor_z(P)
    z0, z1 = zg - 6, zg - 2       # sits on the bottom plate
    y0 = GEARBOX_Y / 2 + 0.05     # 0.1 mm pre-load gap closed by the screws
    c = box(P.x_crank - 14, P.x_crank + 14, y0, y0 + 6.0, z0, z1)
    for sx in (-1, 1):
        c = c.cut(cq.Workplane("XY").workplane(offset=z0 - 1).center(P.x_crank + sx * 10.0, CLAMP_SCREW_Y)
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
        if not solid.isValid() or len(wp.solids().vals()) != 1:
            raise RuntimeError(f"{name}: invalid or multi-solid result")
        volumes[name] = solid.Volume()
        cq.exporters.export(wp, str(out / f"{name}.step"))
        cq.exporters.export(wp, str(out / f"{name}.stl"), tolerance=0.01, angularTolerance=0.1)
        parts_meta.append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                               print_rotation=rot, print_note=note, min_wall=1.2))
    manifest = dict(
        variant="v3_shuttle", pill=pill_id, parts=parts_meta,
        clearances=[dict(a=a, b=b, min=m, what=w) for a, b, m, w in CLEARANCES],
        params=dict(asdict(P), gap=GAP, seat_clearance=CL, ramp_angle=RAMP_ANG,
                    slide_mass_g=round(volumes["slide"] * PLA_DENSITY, 2),
                    wall_angle_x=WALL_ANG_X, wall_angle_y=WALL_ANG_Y, hopper_h=HOPPER_H,
                    hopper_ext=HOPPER_EXT, hopper_wall=HOPPER_WALL, drop_e=DROP_E, chute_e=CHUTE_E,
                    z_crank=crank_z(P), z_gearbox_face=motor_z(P)),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    for pid in (sys.argv[1:] or list(PILLS)):
        m = build(pid)
        print(pid, json.dumps({k: (round(v, 2) if isinstance(v, float) else v)
                               for k, v in m["params"].items()}))
