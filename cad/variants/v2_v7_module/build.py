#!/usr/bin/env python3
"""V2 inclined pocket disc, packaged as a dispensing module for the V7 enclosure.

    python cad/variants/v2_v7_module/build.py            # iron and small kits + common parts
    python cad/variants/v2_v7_module/build.py iron

The pill-handling parts are the V2 parts unchanged (disc, hopper, cover, spacer, and the
front of the back plate), so the V2 simulation results carry over; only what is behind
the back plate is new:

- a short exit duct that ends over the V7 deck's central opening (pills fall into the
  V7 funnel and on to the weighing station);
- a geared drive: the disc's 1/4" shaft turns in two R4-ZZ bearings and carries a printed
  spur gear, driven 1:1 by a second gear on the gearmotor, which lies beside the bearing
  tube. Shafts, bearings and gears are the transmission;
- a stand (base plate and two cheeks) that bolts to the V7 deck exactly where a V7 module
  does: two M3 screws from under the deck into heat-set inserts in the base plate.

Frames. "Local" is the V2 disc frame (disc face z=0, exit +y, hopper +z). "Module" has its
origin on the deck top at the module centre, +y radially outward, +z up. Module 1 of the
V7 sits at enclosure (0, 72); the others are rotated by 60° steps.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v2_build", HERE.parent / "v2_inclined_disc" / "build.py")
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)

KITS = ["iron", "small"]          # the two kits that pass the V2 campaign

# ----------------------------------------------------------------- V7 interface
MOD_R = 72.0                      # module centre radius on the V7 deck (enclosure frame)
MOD_ANGLES = [90, 150, 210, 270, 330, 30]   # module 1..6 positions, degrees
INSERTS = [(-24.0, 0.0), (22.0, 0.0)]       # M3 heat-set inserts, module frame (from V7 deck holes)
INSERT_HOLE = 4.0                 # M3 × 6 OD5 heat-set insert, pressed in from below
DECK_OPEN_R = 48.0                # the deck's central opening reaches this radius between lobes
FUNNEL_TOP_Z = -36.0              # top of the V7 funnel below the deck

# ----------------------------------------------------------------- placement
Y0, Z0 = 6.0, 64.0                # disc centre in the module frame
RELIEF_DUCT = 12.0                # length of duct that keeps the exit-relief section
DUCT_LEN = 38.0                   # exit duct behind the plate (V2 stand-alone: 96). Long
                                  # enough that a pill leaving it falls past the end of the
                                  # drive, not onto the gears or the motor

# ----------------------------------------------------------------- drive
TUBE = 18.0                       # bearing tube length from the plate's front face
GEAR_M, GEAR_Z, GEAR_W = 1.5, 14, 6.0   # module 1.5, 14 teeth each: 1:1, 21 mm pitch circle
GEAR_PA = 20.0                    # pressure angle
GEAR_BACKLASH = 0.10              # tooth thinning per gear at the pitch circle
CD = GEAR_M * GEAR_Z + 0.15       # centre distance (0.15 mm running allowance)
GEAR_GAP = 1.5                    # rear bearing face to shaft gear (printed rear spacer)
HUB_L, HUB_R = 7.0, 9.0           # set-screw hub behind the shaft gear
MOTOR_GAP = 1.0                   # motor gear to the motor mount's front wall
MOUNT_WALL = 1.5                  # motor mount front wall (the gearbox face rests on it)
MOUNT_L = 12.0                    # motor mount length along the motor
POST_XY = (17.0, None)            # motor-mount posts at local (±17, −CD)
POST_R = 4.0                      # 2 mm of wall round the Ø4 insert hole (was 3.5: 1.5 mm)
HOPPER_BOSS_R = 3.75              # bosses behind the plate for the hopper M3 × 6 inserts (1.75 mm wall;
HOPPER_BOSS_H = 3.5               # R4 would touch the R40 plate edge). 3 + 3.5 mm holds the 6 mm insert
LABEL_H, LABEL_DEPTH = 3.6, 0.6   # kit name debossed on the back plate and hopper flange
MOTOR_LEN = 35.0                  # gearbox + motor + encoder
SLEEVE_L = 24.0                   # motor channel length (grips gearbox and can)
SLEEVE_WALL = 2.0
EAR = 5.0                         # strap ear width
PLATE_TRIM = 34.0                 # back plate and hopper flange trimmed to |x| ≤ this
TAB_X = (24.0, 29.0)              # stand tabs behind the plate, local |x|
TAB_Y = (-16.0, -3.0)             # on the low side, clear of the hopper bolt inserts
WEDGE_MARGIN = 1.5                # clearance to the 60° slice of deck each module owns
TAB_DEPTH = 10.0
CHEEK_T = 4.0
CHEEK_X = 29.2                    # inner face of each cheek, module |x|
BASE_T = 5.0
BOSS_H = 9.0


def frames(pp):
    zf = -pp["depth"] - b.RUN                     # plate front face (local z)
    zb = zf - b.BP_T
    L = dict(z_front=zf, zb=zb, tube_rear=zf - TUBE)
    L["gear_front"] = L["tube_rear"] - GEAR_GAP
    L["gear_rear"] = L["gear_front"] - GEAR_W
    L["hub_rear"] = L["gear_rear"] - HUB_L
    # the motor lies behind the gear plane, below the shaft, its output shaft toward the plate
    L["mount_front"] = L["gear_rear"] - MOTOR_GAP
    L["gearbox_face"] = L["mount_front"] - MOUNT_WALL
    L["motor_end"] = L["gearbox_face"] - MOTOR_LEN
    L["shaft_front"] = zf + b.RUN + 8.0                         # top of the disc boss
    L["shaft_rear"] = L["hub_rear"] + 1.0
    return L


def to_module(shape: cq.Workplane) -> cq.Workplane:
    """Local disc frame → module frame."""
    w = b._rot_world(shape)                                     # tilt by BETA about x
    return w.rotate((0, 0, 0), (0, 0, 1), 180).translate((0, Y0, Z0))


def pt_module(p):
    x, y, z = b._world(p)
    return (-x, -y + Y0, z + Z0)


def from_module(shape: cq.Workplane) -> cq.Workplane:
    """Module frame → local disc frame (inverse of to_module)."""
    return (shape.translate((0, -Y0, -Z0)).rotate((0, 0, 0), (0, 0, 1), 180)
            .rotate((0, 0, 0), (1, 0, 0), -b.BETA))


def wedge_module(margin: float = WEDGE_MARGIN) -> cq.Workplane:
    """The 60° slice of the deck that belongs to this module, shrunk by `margin` on each
    side, as a tall prism in the module frame. Everything a module has must fit inside it,
    or it would touch a neighbour."""
    t = math.tan(math.radians(30))
    apex = -MOD_R + margin / math.sin(math.radians(30))
    far = 400.0
    return (cq.Workplane("XY").workplane(offset=-100)
            .polyline([(0, apex), (far * t, apex + far), (-far * t, apex + far)]).close().extrude(400))


def wedge_half_width(y: float, margin: float = WEDGE_MARGIN) -> float:
    return (y + MOD_R) * math.tan(math.radians(30)) - margin / math.cos(math.radians(30))


# ----------------------------------------------------------------- gears
def _involute_gear(z: int, m: float, width: float, bore: cq.Workplane | None = None) -> cq.Workplane:
    """Involute spur gear in the XY plane, z ∈ [0, width]."""
    pa = math.radians(GEAR_PA)
    rp = m * z / 2
    rb = rp * math.cos(pa)
    ra = rp + m
    rf = rp - 1.25 * m
    inv = lambda a: math.tan(a) - a
    # half tooth angle at the pitch circle, thinned for backlash
    half = (math.pi / (2 * z)) - (GEAR_BACKLASH / 2) / rp
    pts = []
    n = 8
    for k in range(z):
        c = 2 * math.pi * k / z
        flank = []
        for i in range(n + 1):
            r = max(rb, rf) + (ra - max(rb, rf)) * i / n
            a = math.acos(min(1.0, rb / r))
            th = half + inv(pa) - inv(a)
            flank.append((r, th))
        left = [(r * math.cos(c - th), r * math.sin(c - th)) for r, th in flank]
        right = [(r * math.cos(c + th), r * math.sin(c + th)) for r, th in reversed(flank)]
        # root arc to the start of this tooth
        th0 = flank[0][1]
        root_a = c - th0 - (2 * math.pi / z - 2 * th0) / 2
        pts.append((rf * math.cos(root_a), rf * math.sin(root_a)))
        pts += [(rf * math.cos(c - th0), rf * math.sin(c - th0))] + left + right
        pts.append((rf * math.cos(c + th0), rf * math.sin(c + th0)))
    g = cq.Workplane("XY").polyline(pts).close().extrude(width)
    return g


def make_shaft_gear() -> cq.Workplane:
    """Gear on the 1/4" shaft, behind the rear bearing. Its hub carries an M3 set screw
    (captured nut) on the shaft's rear flat and holds the shaft axially (it replaces the
    V2 collar). Modelled with the gear face at z=0 and the hub toward −z."""
    g = _involute_gear(GEAR_Z, GEAR_M, GEAR_W).translate((0, 0, -GEAR_W))
    g = g.union(cq.Workplane("XY").workplane(offset=-GEAR_W - HUB_L).circle(HUB_R).extrude(HUB_L))
    g = g.cut(cq.Workplane("XY").workplane(offset=-GEAR_W - HUB_L - 1).circle(b.DRIVE_D / 2 + 0.1)
              .extrude(GEAR_W + HUB_L + 2))
    zc, r = -GEAR_W - HUB_L / 2, 1.65
    g = g.cut(cq.Workplane("XY").workplane(offset=-GEAR_W - HUB_L - 1).center(5.9, 0).rect(2.7, 5.8)
              .extrude(HUB_L / 2 + 1 + 2.9))                               # nut slot from the hub end
    # set-screw hole along +x; printed gear face down, so its teardrop roof points to −z
    g = g.cut(cq.Workplane("YZ").center(0, zc).circle(r).extrude(HUB_R + 1))
    g = g.cut(cq.Workplane("YZ").polyline([(-r * 0.7071, zc - r * 0.7071), (0, zc - r * 1.5),
                                           (r * 0.7071, zc - r * 0.7071)]).close().extrude(HUB_R + 1))
    return g


def make_rear_spacer() -> cq.Workplane:
    """Ring between the rear bearing's inner race and the shaft gear."""
    return cq.Workplane("XY").circle(4.5).circle(b.DRIVE_D / 2 + 0.1).extrude(GEAR_GAP)


def make_motor_gear() -> cq.Workplane:
    """Gear on the gearmotor's 3 mm D-shaft: light press fit, one drop of CA on the flat."""
    g = _involute_gear(GEAR_Z, GEAR_M, GEAR_W).translate((0, 0, -GEAR_W))
    bore = cq.Workplane("XY").workplane(offset=-GEAR_W - 1).circle(b.SHAFT_D / 2 + 0.05).extrude(GEAR_W + 2)
    flat = (cq.Workplane("XY").workplane(offset=-GEAR_W - 1)
            .center(b.SHAFT_FLAT - b.SHAFT_D / 2 + 0.05 + 2, 0).rect(4, 6).extrude(GEAR_W + 2))
    return g.cut(bore.cut(flat))


# ----------------------------------------------------------------- back plate
def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, (y0 + y1) / 2)
            .rect(x1 - x0, y1 - y0).extrude(z1 - z0))


def tab_hole_z() -> float:
    """Tab holes sit at the same place for every kit (the thickest disc's back plate sets
    it), so the shared cheeks fit all kits; a thinner kit's tabs are simply longer."""
    zb_ref = min(frames(b.pocket_params(k))["zb"] for k in KITS)
    return zb_ref - TAB_DEPTH / 2


def tab_holes_local(pp=None):
    zc = tab_hole_z()
    return [(sx * (TAB_X[0] + TAB_X[1]) / 2, y, zc) for sx in (-1, 1) for y in TAB_Y]


def make_backplate(pp: dict) -> cq.Workplane:
    L = frames(pp)
    zf, zb = L["z_front"], L["zb"]
    pp_open = dict(pp, closed=False)
    trim = _box(-PLATE_TRIM, PLATE_TRIM, -b.FLANGE_R - 1, b.FLANGE_R + 1, zb - 200, zf + 1)
    plate = cq.Workplane("XY").workplane(offset=zb).circle(b.FLANGE_R).extrude(b.BP_T).intersect(trim)
    # exit hole and short duct (same section as V2)
    em = b.EXIT_MARGIN + b.undercut_at_back(pp_open)
    hole = (b._extruded_notch(pp_open, zb - DUCT_LEN - 1, b.BP_T + DUCT_LEN + 2, grow=em, outer=b.R_WALL)
            .rotate((0, 0, 0), (0, 0, 1), b.EXIT_ANGLE)
            .union(b._relief_prism(pp_open, zb - RELIEF_DUCT, RELIEF_DUCT + b.BP_T + 1)))
    # 45° taper at the end of the relief section: a cone round the disc axis closes the
    # relief band outward-in, so the hole has no flat ceiling when the plate prints front
    # face down
    ze = zb - RELIEF_DUCT
    r_out = b.R_WALL + b.RELIEF + 1.0
    h_c = 1.25 * (r_out - 28.0)                 # 51° from horizontal
    cone = (cq.Workplane("XY").workplane(offset=ze - h_c).circle(28.0)
            .workplane(offset=h_c).circle(r_out).loft())
    hole = hole.union(b._relief_prism(pp_open, ze - h_c, h_c + 0.01).intersect(cone))
    duct = (b._extruded_notch(pp_open, zb - DUCT_LEN, DUCT_LEN, grow=em + 1.6, outer=b.R_WALL + 1.6)
            .rotate((0, 0, 0), (0, 0, 1), b.EXIT_ANGLE)
            .union(b._relief_prism(pp_open, zb - RELIEF_DUCT, RELIEF_DUCT + b.BP_T, grow=1.6)))
    plate = plate.union(duct).cut(hole)
    hw = (pp["length"] if pp["shape"] == "oblong" else pp["width"]) / 2 + b.EXIT_MARGIN + 1.6
    plate = plate.cut(b._teardrop_x(-hw - 2, hw + 2, pp["r_center"], zb - b.BEAM_Z, 1.6))
    # bearing tube
    r_p = (b.BRG_OD + b.BRG_FIT) / 2
    r_o = r_p + b.BRG_WALL
    plate = plate.union(cq.Workplane("XY").workplane(offset=L["tube_rear"]).circle(r_o).extrude(TUBE - b.BP_T))
    # two posts for the motor mount, either side of the motor gear; heat-set inserts in
    # their ends (blind holes open at the top when printed front face down)
    for sx in (-1, 1):
        px, py = sx * POST_XY[0], -CD
        plate = plate.union(cq.Workplane("XY").workplane(offset=L["mount_front"]).center(px, py)
                            .circle(POST_R).extrude(zb - L["mount_front"]))
        # 9 mm deep: the 6 mm insert sits flush with the post end and the M3 × 10 through the
        # 4 mm mount ear ends 6 mm in, so the hole runs 3 mm past the screw tip
        plate = plate.cut(cq.Workplane("XY").workplane(offset=L["mount_front"] - 1).center(px, py)
                          .circle(2.0).extrude(10.0))
    # stand tabs
    for sx in (-1, 1):
        for y in TAB_Y:
            x0, x1 = sorted((sx * TAB_X[0], sx * TAB_X[1]))
            plate = plate.union(_box(x0, x1, y - 5, y + 5, tab_hole_z() - TAB_DEPTH / 2, zb))
    for (x, y, z) in tab_holes_local(pp):
        plate = plate.cut(b._teardrop_x(x - 6, x + 6, y, z, 1.7))
    # bearing pockets, cone, shaft bore
    z_p = zf - b.BRG_RECESS - b.BRG_W
    plate = plate.cut(cq.Workplane("XY").workplane(offset=z_p).circle(r_p).extrude(b.BRG_RECESS + b.BRG_W + 1))
    plate = plate.cut(cq.Workplane("XY").workplane(offset=z_p - 3.0).circle(5.5)
                      .workplane(offset=3.0).circle(r_p).loft())
    plate = plate.cut(cq.Workplane("XY").workplane(offset=L["tube_rear"] - 1).circle(5.5).extrude(TUBE))
    plate = plate.cut(cq.Workplane("XY").workplane(offset=L["tube_rear"] - 1).circle(r_p).extrude(b.BRG_W + 1))
    # hopper bolt holes: heat-set inserts pressed in from the back, flush with the boss end.
    # The V2 plate is only 3 mm thick, shorter than the insert, so each hole gets a boss
    # (kept 0.5 mm inside the cheeks)
    bosses = (cq.Workplane("XY").workplane(offset=zb - HOPPER_BOSS_H)
              .polarArray(b.BOLT_R, 45, 360, 4).circle(HOPPER_BOSS_R).extrude(HOPPER_BOSS_H + 1.0))
    plate = plate.union(bosses.intersect(_box(-CHEEK_X + 0.5, CHEEK_X - 0.5, -60, 60, zb - 10, zb + 1)))
    holes = (cq.Workplane("XY").workplane(offset=zb - HOPPER_BOSS_H - 1)
             .polarArray(b.BOLT_R, 45, 360, 4).circle(2.0).extrude(HOPPER_BOSS_H + b.BP_T + 2))
    return plate.cut(holes).intersect(from_module(wedge_module()))


def _label(text: str, plane: cq.Plane) -> cq.Workplane:
    return cq.Workplane(plane).text(text, LABEL_H, -LABEL_DEPTH, combine=False, halign="center", valign="center")


def label_backplate(plate: cq.Workplane, pp: dict, kit: str) -> cq.Workplane:
    """Kit name debossed in the plate's rear face (up when printed), below the gears."""
    zb = frames(pp)["zb"]
    pl = cq.Plane(origin=(0, -34.0, zb), xDir=(-1, 0, 0), normal=(0, 0, -1))
    return plate.cut(_label(kit.upper(), pl))


def label_hopper(hop: cq.Workplane, pp: dict, kit: str) -> cq.Workplane:
    """Kit name debossed in the top of the hopper flange, on the low side."""
    z0 = -pp["depth"] - b.RUN
    pl = cq.Plane(origin=(0, -36.0, z0 + 3.0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return hop.cut(_label(kit.upper(), pl))


def make_hopper(pp: dict) -> cq.Workplane:
    """V2 hopper with its flange trimmed to the module width."""
    h = b.make_hopper(pp)
    return h.intersect(_box(-PLATE_TRIM, PLATE_TRIM, -200, 200, -200, 200)).intersect(from_module(wedge_module()))


def make_motor_mount() -> cq.Workplane:
    """Holds the gearmotor behind the gear plane. Modelled in the local frame with its
    front wall at z=0 and the body toward −z; printed front wall down. The gearbox face
    rests on the front wall; the U-channel is open toward −y for the strap; two ears
    screw to the posts on the back plate (M3 × 10 into heat-set inserts)."""
    gw, gh = b.GEARBOX
    xh, yh = gw / 2 + b.RUN, gh / 2 + b.RUN
    x_o, y_top = xh + SLEEVE_WALL, yh + SLEEVE_WALL
    blk = _box(-x_o, x_o, -yh, y_top, -MOUNT_L, 0)
    blk = blk.cut(_box(-xh, xh, -yh - 1, yh, -MOUNT_L - 1, -MOUNT_WALL))
    blk = blk.cut(cq.Workplane("XY").workplane(offset=-MOUNT_WALL - 1).circle(3.2).extrude(MOUNT_WALL + 2))
    # mounting ears to the posts
    for sx in (-1, 1):
        blk = blk.union(_box(sx * x_o if sx > 0 else -POST_XY[0] - 4, POST_XY[0] + 4 if sx > 0 else -x_o,
                             -4, 4, -4, 0))
        blk = blk.cut(cq.Workplane("XY").workplane(offset=-5).center(sx * POST_XY[0], 0).circle(1.7).extrude(6))
    # strap ears on the open side, M2 pilot holes along y (teardrop roof toward −z, which
    # is up when printed front wall down)
    ear_x = xh + SLEEVE_WALL + EAR / 2
    for sx in (-1, 1):
        blk = blk.union(_box(sx * ear_x - EAR / 2, sx * ear_x + EAR / 2, -yh, -yh + 6, -MOUNT_L, 0))
        xc, zc, r = sx * ear_x, -MOUNT_L / 2 - 1, 0.8
        blk = blk.cut(cq.Workplane("XZ").workplane(offset=yh + 1).center(xc, zc).circle(r).extrude(-8))
        blk = blk.cut(cq.Workplane("XZ").workplane(offset=yh + 1)
                      .polyline([(xc - r * 0.7071, zc - r * 0.7071), (xc, zc - r * 1.5),
                                 (xc + r * 0.7071, zc - r * 0.7071)]).close().extrude(-8))
    return blk


STRAP_SQUEEZE = 0.6               # clamp interference: the rib stops the strap this far off the ears


def make_strap() -> cq.Workplane:
    """Plate over the open side of the motor mount, modelled with the motor-side face at
    z=0. A rib on that face reaches RUN + STRAP_SQUEEZE below it, so it presses on the
    motor before the plate reaches the ears: tightening the two M2 screws clamps the motor
    against the channel floor and the friction holds it along its axis (the spur gears put
    no axial load on it; its own weight along the axis is about 0.1 N)."""
    gw, gh = b.GEARBOX
    xe = gw / 2 + b.RUN + SLEEVE_WALL + EAR / 2
    plate = (cq.Workplane("XY").rect(2 * xe + 6, 6).extrude(3.0)
             .cut(cq.Workplane("XY").workplane(offset=-1).pushPoints([(-xe, 0), (xe, 0)]).circle(1.1).extrude(5)))
    rib = cq.Workplane("XY").rect(gw - 2.0, 6).extrude(-(b.RUN + STRAP_SQUEEZE))
    return plate.union(rib)


# ----------------------------------------------------------------- stand
def _cheek_x():
    return CHEEK_X


def make_cheek(pp_ref: dict) -> cq.Workplane:
    """Right cheek (module +x side), printed flat. Bolts to two back-plate tabs and
    stands in a slot in the base plate. Its foot stays inside the module's deck slice."""
    pts = [pt_module(h) for h in tab_holes_local(pp_ref) if h[0] < 0]     # local −x → module +x
    ys, zs = [p[1] for p in pts], [p[2] for p in pts]
    x0 = _cheek_x()
    y_min_foot = max(min(ys) - 8, (x0 + CHEEK_T + 1.0) / math.tan(math.radians(30)) - MOD_R + 2.0)
    lo = min(pts, key=lambda p: p[1])
    hi = max(pts, key=lambda p: p[1])
    outline = [(y_min_foot, BASE_T - 3.0), (max(ys) + 9, BASE_T - 3.0), (hi[1] + 7, hi[2] + 6),
               (lo[1] - 6, lo[2] + 7), (lo[1] - 7, lo[2] - 3)]
    cheek = cq.Workplane("YZ").workplane(offset=x0).polyline(outline).close().extrude(CHEEK_T)
    for (y, z) in [(p[1], p[2]) for p in pts]:
        cheek = cheek.cut(cq.Workplane("YZ").workplane(offset=x0 - 1).center(y, z).circle(1.7).extrude(CHEEK_T + 2))
    # stay behind the back plate (0.5 mm) and inside this module's deck slice
    zb = frames(pp_ref)["zb"]
    behind = to_module(_box(-200, 200, -200, 200, -300, zb - 0.5))
    return cheek.intersect(behind).intersect(wedge_module())


def cheek_y_span(pp_ref):
    bb = make_cheek(pp_ref).val().BoundingBox()
    return bb.ymin, bb.ymax


def make_base(pp_ref: dict) -> cq.Workplane:
    """Base plate on the V7 deck. Two heat-set inserts where a V7 module's are, slots for
    the cheeks, and a hole over the deck's motor lobe for the wires."""
    cy0, cy1 = cheek_y_span(pp_ref)
    y0 = DECK_OPEN_R - MOD_R + 1.0                  # stay on the deck: y ≥ −23
    y1 = max(cy1 + 4, 30.0)
    xo = _cheek_x() + CHEEK_T + 3.0
    base = _box(-xo, xo, y0, y1, 0, BASE_T).intersect(wedge_module())
    base = base.edges("|Z").fillet(2.0)
    for (x, y) in INSERTS:
        base = base.union(cq.Workplane("XY").center(x, y).circle(5.0).extrude(BOSS_H))
        base = base.cut(cq.Workplane("XY").workplane(offset=-1).center(x, y).circle(INSERT_HOLE / 2)
                        .extrude(BOSS_H + 2))
    for sx in (-1, 1):
        xc = sx * (_cheek_x() + CHEEK_T / 2)
        base = base.cut(_box(xc - CHEEK_T / 2 - 0.2, xc + CHEEK_T / 2 + 0.2, cy0 - 0.2, cy1 + 0.2,
                             BASE_T - 3.0, BASE_T + 1))
    base = base.cut(cq.Workplane("XY").workplane(offset=-1).center(0, -6).slot2D(18, 10, 90).extrude(BASE_T + 2))
    return base


# ----------------------------------------------------------------- export
def module_parts(kit: str) -> list[tuple[str, cq.Workplane, list, float]]:
    """(name, solid in the module frame, print rotation, overhang allowance)."""
    pp = b.pocket_params(kit)
    return [
        ("disc", to_module(b.make_disc(pp)), None, 4.0),
        ("backplate", to_module(make_backplate(pp)), None, 4.0),
        ("hopper", to_module(make_hopper(pp)), None, 4.0),
    ]


def print_rot_local(front_down: bool):
    """Euler (deg) that lays a part saved in the module frame on its local face."""
    # module = Rz(180)·Rx(β)·local; lay local −z (front face) or +z down
    return None


def _export(shape, out: Path, name: str):
    cq.exporters.export(shape, str(out / f"{name}.step"))
    cq.exporters.export(shape, str(out / f"{name}.stl"), tolerance=0.02, angularTolerance=0.08)


def build(kit: str) -> dict:
    pp = b.pocket_params(kit)
    out = HERE / kit
    out.mkdir(parents=True, exist_ok=True)
    # parts are saved in their local (print) orientation, like V2's print rotation applied:
    # disc back face down, back plate front face down, hopper flange down
    parts = {
        "disc": (b.make_disc(pp), "back face down (as saved)"),
        "backplate": (label_backplate(make_backplate(pp), pp, kit).rotate((0, 0, 0), (1, 0, 0), 180),
                      "front face down (as saved)"),
        "hopper": (label_hopper(make_hopper(pp), pp, kit), "flange down (as saved)"),
    }
    man = dict(variant="v2_v7_module", pill=kit, params=dict(pp, y0=Y0, z0=Z0, duct_len=DUCT_LEN,
                                                             tube=TUBE, gear_cd=CD), parts=[],
               clearances=[])
    for name, (shape, how) in parts.items():
        _export(shape, out, name)
        man["parts"].append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                                 print_rotation=[0, 0, 0], bed=how))
    # the same back plate and hopper in the V2 world frame, for the simulator
    for name, shape in (("backplate", make_backplate(pp)), ("hopper", make_hopper(pp))):
        cq.exporters.export(b._rot_world(shape), str(out / f"sim_{name}.stl"), tolerance=0.02,
                            angularTolerance=0.08)
    (out / "manifest.json").write_text(json.dumps(man, indent=2))
    return man


def build_common():
    ref = max((b.pocket_params(p) for p in KITS), key=lambda q: q["depth"])
    out = HERE / "common"
    out.mkdir(parents=True, exist_ok=True)
    cheek = make_cheek(ref)
    bb = cheek.val().BoundingBox()
    parts = [
        ("cover", b.make_cover(), [180, 0, 0], "outer face down"),
        ("spacer", b.make_spacer(), [0, 0, 0], "flat"),
        ("shaft_gear", make_shaft_gear(), [180, 0, 0], "gear face down, hub up", 12.0),
        ("rear_spacer", make_rear_spacer(), [0, 0, 0], "flat"),
        ("motor_gear", make_motor_gear(), [0, 0, 0], "flat"),
        ("strap", make_strap(), [180, 0, 0], "rib up"),
        ("motor_mount", make_motor_mount(), [180, 0, 0], "front wall down"),
        ("cheek_right", cheek, [0, -90, 0], "flat"),
        ("cheek_left", cheek.mirror("YZ"), [0, 90, 0], "flat"),
        ("base", make_base(ref), [0, 0, 0], "bottom face down"),
    ]
    man = dict(variant="v2_v7_module", pill="common", parts=[], clearances=[])
    for name, shape, rot, how, *ov in parts:
        _export(shape, out, name)
        man["parts"].append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step",
                                 print_rotation=rot, bed=how, max_overhang_mm2=(ov or [4.0])[0]))
    (out / "manifest.json").write_text(json.dumps(man, indent=2))


if __name__ == "__main__":
    kits = sys.argv[1:] or KITS
    for k in kits:
        build(k)
        print("built", k)
    if not sys.argv[1:]:
        build_common()
        print("built common")
