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
HOPPER_DEPTH = 70.0    # hopper wall height in front of the disc (along the axis). rev 9: was 40;
                       # +30 raises the low front lip ~19 mm so a 20-tablet fill can't spill
FILL_EXT = 0.0
ANTI_ARCH_Z0, ANTI_ARCH_Z1, ANTI_ARCH_DEG = 12.0, 45.0, 15.0
# rev 11: over the pool (lower) half the hopper wall leans inward going away from the disc,
# by ANTI_ARCH_DEG at the very bottom fading smoothly to 0 at the sides, between z0 and z1,
# then runs straight to the top. The whole shell leans (outer surface too), so the rim
# stays 2.4 mm wide with no ledge, and the bore only ever widens toward the disc: flow to
# the pool diverges and can't arch. History: rev 8 vertical wall, 2 arching misses / 100
# trials; rev 9 inner lining left a rim shelf pills slid off; rev 10 flare made a waist
# that arched all 20 tablets.
RIM_CHAMFER = WALL - 1.2   # inner rim chamfer (rev 10); leaves a 1.2 mm land
BP_T = 3.0             # back plate thickness
EXIT_MARGIN = 1.2      # exit hole larger than the pocket on every side
DUCT_LEN = 96.0        # exit duct behind the plate; runs parallel to the drive line, above it,
                       # and slopes 40° below horizontal (tan 40° = 0.84 > μmax 0.6). Was 50 mm
                       # with the disc on the motor shaft; the shaft drive puts the motor's rear
                       # end 100 mm behind the plate and a pill must fall clear of it
BEAM_Z = 8.0           # beam-break pair (Adafruit 2167, 3 mm LEDs) this far into the duct
WEB_MIN = 4.0          # minimum solid between neighbouring notches at their inner end
EXIT_ANGLE = 90.0      # exit at the top (12 o'clock), far above the pool at 270°; N is a
                       # multiple of 4 so the top is always a rest position
SHAFT_D, SHAFT_FLAT = 3.0, 2.5  # Pololu micro-gearmotor D shaft (Ø3, 2.5 across flat)
# Transmission: the disc sits on a 1/4" shaft carried by two ball bearings in a tube behind
# the back plate; a flexible coupler joins the shaft to the gearmotor.
DRIVE_D = 6.35         # 1/4" drive shaft
DRIVE_FLAT = 5.75      # across the flat filed on the shaft's front 10 mm (0.6 mm deep)
DRIVE_LEN = 57.15      # 2-1/4" shaft
BRG_OD, BRG_W = 15.875, 4.98   # R4-ZZ ball bearing, 1/4" × 5/8" × 0.196"
BRG_FIT = 0.10         # pocket diameter over the bearing (light press in PLA)
BRG_RECESS = 1.6       # front bearing sits this far below the plate's front face
BRG_TUBE = 28.0        # bearing tube length from the plate's front face
BRG_WALL = 2.4
COLLAR_LEN, COLLAR_BOSS = 9.0, 0.6   # printed set-screw collar behind the rear bearing
COUPLER = (19.0, 25.0)  # flexible coupler 3 mm to 6.35 mm, Ø19 × 25
MOTOR_SHAFT = 9.0      # gearmotor shaft length
MOTOR_LEN = 35.0       # gearbox + motor + encoder
SADDLE = (5.0, 15.0)   # the saddle grips the gearbox rear and motor can, this far behind the gearbox face
RAIL_X = (11.5, 15.5)  # the two rails that carry the motor socket behind the bearing tube
SPINE_Y = (10.5, 12.9)
GEARBOX = (12.0, 10.0)          # micro-gearmotor gearbox cross-section (w × h)
FLANGE_R = 40.0        # back plate / hopper flange radius
BOLT_R = 36.0          # M3 bolt circle for hopper → back plate
DEPTH_BELOW_T = 0.3    # pocket depth = min pill thickness − this (2nd pill can't nest)
RELIEF = 4.0           # hopper bore widened this much over the exit notch (rev 3): a pill
                       # standing on edge can't hang by friction between notch end and wall
RELIEF_RAMP = 20.0     # deg, ramp back to the bore on both sides (a cam, never a shear edge)
STANDING_T_OVER_D = 9.9  # rev 21: disabled, every tablet uses the flat notch. The standing slot
                         # (revs 8-20) was adopted because flat notches seemed to wedge tablets; that
                         # was an artefact of collision pieces protruding into the pockets (fixed in
                         # sim/convexify.py). Kept in the code for tablets that may need it later.
                         # against the hopper wall (iron) and get a standing slot
CONE_DEG, CONE_H, HUB_H = 60.0, 4.5, 0.0
# rev 18: only a 3 mm high ramp ring, then a flat raised face. Rev 16's full cone cradled a
# second tablet in the V above a seated one (1 double in 10 trials); rev 17's 12 mm hub made
# a channel that conveyed stacked tablets (doubles in 10 of 16). A 3 mm ramp still tilts a
# flat tablet at the wall so it slides into the slot, and stays below a seated tablet's top.
# rev 16 (standing-slot discs): inboard of the slots the disc rises as a 60° cone, so the
# pool is a V-channel between cone and wall. Nothing can lie flat: a tablet at the wall is
# tipped onto its edge and slides into the slot. (Rev 14: a lone flat tablet bridged the
# slot, 7 of 16 last-tablet misses; rev 15 flat notch: tilted tablets wedged in the notch.)
                         # against the hopper wall (iron) and get a standing slot




def lean_factor(theta: float) -> float:
    """0..1 lean weighting by angle around the disc (1 at the bottom, 0 on the upper half)."""
    return max(0.0, -math.sin(theta))


BASE_FLARE_Z, BASE_FLARE_DEG = 8.0, 0.0   # rev 14: flare removed (it wedged flat tablets)
# rev 12: over the pool half, the bottom BASE_FLARE_Z mm of the wall leans OUTWARD (bore
# still R_WALL at the disc face). A lone flat tablet pressed against a vertical wall was
# held up by wall friction while slots passed under it (miss); against an outward-leaning
# wall the push into the wall has a component toward the disc, so it tips into the slot.


LIP_H, LIP_DEG = 4.0, 40.0
# rev 13: the top LIP_H mm of the pool-side wall leans inward LIP_DEG (4 mm: a 10 mm lip left
# only 6 mm² of opening for a tablet centre) (in the assembled,
# tilted position that is within 10° of vertical). A pill poured just inside the lip then
# falls clear of the wall below it; before, a pill dropped at the rim clipped the rim's
# flat top, which slopes outward at the low side, and rolled out (4 lost in 125 trials).
HOPPER_TOP = HOPPER_DEPTH + LIP_H
COVER_Y = 12.0   # the cover closes local y > COVER_Y. Everything poured in falls onto the
                 # pool-side wall (straight down is 50° off the axis), so the opening can
                 # reach past the centre line; 12 mm makes it ~31 mm deep for long pills


def bore_r(theta: float, z: float, extra: float = 0.0) -> float:
    """Hopper bore radius at local angle theta (rad) and height z above the disc face."""
    f = lean_factor(theta)
    lip = max(0.0, min(z, HOPPER_TOP) - HOPPER_DEPTH) * math.tan(math.radians(LIP_DEG)) * f
    extra = extra - lip
    base = max(0.0, min(z, BASE_FLARE_Z)) * math.tan(math.radians(BASE_FLARE_DEG)) * f
    dz = max(0.0, min(z, ANTI_ARCH_Z1) - ANTI_ARCH_Z0)
    return R_WALL + extra + base - dz * math.tan(math.radians(ANTI_ARCH_DEG)) * f


def _bore_pts(z: float, extra: float, n: int = 96):
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        r = bore_r(t, z, extra)
        out.append((r * math.cos(t), r * math.sin(t)))
    return out


def _bore_solid(z_start: float, z_end: float, extra: float) -> cq.Workplane:
    """Volume inside bore_r(+extra) from z_start to z_end (ruled lofts between breakpoints)."""
    levels = [z_start] + [z for z in (0.0, BASE_FLARE_Z, ANTI_ARCH_Z0, ANTI_ARCH_Z1, HOPPER_DEPTH)
                          if z_start < z < z_end] + [z_end]
    solid = None
    for lo, hi in zip(levels[:-1], levels[1:]):
        seg = (cq.Workplane("XY").workplane(offset=lo).polyline(_bore_pts(lo, extra)).close()
               .workplane(offset=hi - lo).polyline(_bore_pts(hi, extra)).close().loft(ruled=True))
        solid = seg if solid is None else solid.union(seg)
    return solid


def pocket_params(pill_id: str) -> dict:
    p = PILLS[pill_id]
    # Notch spans are sized to the pill's TILTED diagonal (+ clearance), so a pill that
    # tips while dropping out can never wedge across the notch (rev 2: a 9.5×5 tablet
    # tilted ~28° spans 10.7 mm and wedged between the notch end and the hopper wall).
    if p.kind == "tablet" and p.thickness / p.length >= STANDING_T_OVER_D:
        # rev 8 (iron): the sim shows thick tablets settle STANDING on edge against the
        # hopper wall, plane tangential. The slot is built for that pose: open to the wall,
        # radially one thickness + clearance (two standing tablets would need 2T = 9.7 mm),
        # tangentially longer than the tilted diagonal so it can't wedge between the slot
        # walls (rev 5/6 failures). A flat tablet can't seat and slides back out.
        d_max, t_max, t_min = p.length + p.tol, p.thickness + p.tol, p.thickness - p.tol
        length = math.hypot(d_max, t_max) + 2 * FDM           # tangential
        w = round(min(2 * t_min - 2.0, t_max + 2 * FDM + 1.6), 2)  # radial: 7.5 for iron
        r_in = R_WALL - w
        r_c = R_WALL - t_max / 2 - FDM
        half_ang = math.atan((length / 2) / r_in)
        shape = "oblong"
        pocket = "standing slot"
        inner_chamfer = 0.0   # rev 14: removed (rev 13's chamfer let a 2nd tablet sit half-in and jam)
    elif p.kind == "tablet":
        inner_chamfer = 0.0
        d_max = p.length + p.tol
        t_min = p.thickness - p.tol
        w = d_max + 2 * FDM                     # notch diameter
        closed = pair_prone(pill_id, w)
        # open notch: centre of a pill lying against the wall; closed: RIM_WEB inside the rim
        r_c = (min(rib_stop_r(pill_id), R_DISC - RIM_WEB) - w / 2) if closed else (R_WALL - w / 2)
        r_in = r_c - w / 2
        half_ang = math.asin((w / 2) / r_c)
        shape = "round"
        length = w
        pocket = "flat notch"
    else:
        L = p.length + p.tol_length
        W = p.width + p.tol
        T = p.thickness + p.tol
        t_min = (p.thickness - p.tol) if p.kind == "caplet" else (p.width - p.tol)
        # rev 31: snug pocket for caplets too (pill + FDM per side). Rev 2 had enlarged it to
        # the tilted diagonal (21.0 x 11.7 for a 19 x 8.5 caplet) against wedging that came
        # from the old collision shapes; the slack let a second caplet partly enter
        # (doubles, and a jam once the lead-in chamfer was removed).
        length = L + 2 * FDM
        w = W + 2 * FDM
        if p.kind == "caplet":
            # rev 33: width clears the diagonal of the caplet's cross-section. A caplet that
            # enters standing on end twists in the pocket; in a 9.4 mm wide pocket its
            # 8.5 x 6.5 section locked diagonally against the hopper wall (jams in 7 of 24
            # trials). The LENGTH stays snug so a second caplet's tail has nowhere to sit.
            w = math.hypot(W, T) + 2 * FDM
        pocket = "flat notch"
        if LONG_RADIAL and R_WALL - (L + 2 * FDM) >= RADIAL_MIN_R_IN:
            # rev 36: the pocket points along the radius. Left alone on the 50° disc a long
            # pill slides down lengthwise and stops end-on to the wall, so that is the pose
            # the pocket is cut for (rim-wise pockets missed the last few pills; a cone or a
            # hub to turn them caused doubles or strut jams). `length` stays the tangential
            # size and `width` the radial size, as everywhere else in this file.
            cross = (math.hypot(W, T) if p.kind == "caplet" else W) + 2 * FDM
            length, w = cross, L + 2 * FDM
            r_in = R_WALL - w
            r_c = R_WALL - w / 2
        else:
            # pill lying tangentially against the curved wall: end-cap centres touch R_WALL
            d_c = math.sqrt((R_WALL - W / 2) ** 2 - ((L - W) / 2) ** 2)
            r_c = d_c
            r_in = d_c - W / 2 - (w - W) + FDM
        half_ang = math.atan((length / 2) / r_in)
        shape = "oblong"
    t_min = p.thickness - p.tol if p.kind != "capsule" else p.width - p.tol
    depth = round(t_min - DEPTH_BELOW_T, 2)
    if p.kind in ("caplet", "capsule"):
        # rev 34: long-pill pockets are only LONG_DEPTH_FRAC of the pill's thickness deep.
        # A pocket long enough for one pill lying flat also takes two standing on end
        # (2 doubles in 24 caplet trials, both pills tipped ~50° in one pocket). A flat pill
        # is held by a half-depth wall; a pill standing on its tip in a shallow pocket is
        # top-heavy and topples out on the way up.
        depth = round(LONG_DEPTH_FRAC * t_min, 2)
    # number of notches: largest even N leaving WEB_MIN of solid at r_in, multiple of 4
    n = 4
    for cand in range(4, 40, 4):
        web = r_in * (2 * math.pi / cand - 2 * half_ang)
        if web >= WEB_MIN + 2 * EXIT_MARGIN:
            n = cand
    # rev 30: no lead-in chamfer. It widened a long-pill pocket at the face by ~4 mm, and a
    # second pill rode with its tail dipped into that space, then fell in behind the first
    # at the exit (1 double in 100 caplet trials). It was added in rev 4 against a wedging
    # problem that came from the old collision shapes.
    chamfer = 0.0
    return dict(pill=pill_id, shape=shape, width=round(w, 3), length=round(length, 3),
                r_center=round(r_c, 3), r_inner=round(r_in, 3), depth=depth, n=n,
                pitch_deg=360.0 / n, chamfer=chamfer, pocket=pocket,
                trail_chamfer=round(min(2.5, 0.35 * depth), 2)
                if (LONG_TRAIL_CHAMFER and p.kind in ("caplet", "capsule")) else 0.0,
                hub_r=round(r_in - HUB_GAP, 2) if (LONG_HUB and p.kind in ("caplet", "capsule")) else 0.0,
                hub_h=HUB_HEIGHT if (LONG_HUB and p.kind in ("caplet", "capsule")) else 0.0,
                ribs=n if (LONG_RIBS and p.kind in ("caplet", "capsule")) else 0,
                inner_chamfer=inner_chamfer if pocket == "standing slot" else 0.0,
                closed=bool(p.kind == "tablet" and pocket == "flat notch" and pair_prone(pill_id, w)),
                cone_h=round(min(20.0, (r_in - CONE_LEDGE - 7.0) * math.tan(math.radians(LONG_CONE_DEG))), 2)
                if (LONG_CONE and p.kind in ("caplet", "capsule")) else 0.0)


# --------------------------------------------------------------- 2-D outlines
def relief_outline(pp: dict, grow: float = 0.0, pts: int = 48):
    """Closed local-XY outline of the exit relief region (bore + RELIEF over the exit
    notch, ramped back to the bore), from radius R_DISC−1 outward."""
    half = math.degrees((pp["length"] / 2 + EXIT_MARGIN) / R_WALL) + 1.0
    ramp = math.degrees((RELIEF / math.tan(math.radians(RELIEF_RAMP))) / R_WALL)
    a0, a1 = EXIT_ANGLE - half - ramp, EXIT_ANGLE + half + ramp
    outer = []
    for k in range(pts + 1):
        a = a0 + (a1 - a0) * k / pts
        d = abs(a - EXIT_ANGLE)
        r = R_WALL + RELIEF if d <= half else R_WALL + RELIEF * max(0.0, 1 - (d - half) / ramp)
        r += grow
        outer.append((r * math.cos(math.radians(a)), r * math.sin(math.radians(a))))
    r_i = R_DISC - 1.0
    inner = [(r_i * math.cos(math.radians(a)), r_i * math.sin(math.radians(a)))
             for a in (a1, (a0 + a1) / 2, a0)]
    return outer + inner


def _relief_prism(pp: dict, z0: float, h: float, grow: float = 0.0) -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=z0).polyline(relief_outline(pp, grow)).close()
            .extrude(h))


UNDERCUT_DEG = 12.0
# rev 19: every pocket wall is undercut (pocket wider at the back plate than at the face).
# At the exit the pill is pressed against the pocket's inner wall (0.77 g) while only 0.64 g
# pulls it out the back, so on a straight wall it sticks when friction exceeds ~0.84 or the
# wall has any ledge (seen: a seated last tablet parked at the exit). With 12° of undercut
# it slides out up to friction ~1.3. The entry size at the face is unchanged.


# rev 41 (small tablets, closed pocket): 20° undercut. In the V7-module campaign one small
# tablet rode up the disc tilted ~30° in its closed pocket, wedged between the straight land
# at the face and the 12° wall at the back, and sat at the exit for 0.45 s with the disc
# stopped (friction 0.51); the next index then dropped it with the next tablet (a double).
# The steeper wall frees a tilted tablet as soon as it reaches the exit hole.
UNDERCUT_DEG_CLOSED = 20.0


def undercut_deg(pp: dict) -> float:
    return UNDERCUT_DEG_CLOSED if pp.get("closed") else UNDERCUT_DEG


UNDERCUT_LAND = 1.2   # top of each pocket wall stays straight (no feather edge at the face)


def undercut_land(pp: dict) -> float:
    """Straight part at the top of the pocket wall: below any lead-in chamfer."""
    return UNDERCUT_LAND + max(pp.get("chamfer", 0.0), pp.get("trail_chamfer", 0.0))


def undercut_at_back(pp: dict) -> float:
    return max(0.0, pp["depth"] - undercut_land(pp)) * math.tan(math.radians(undercut_deg(pp)))


RIM_WEB = 1.2
LONG_DEPTH_FRAC = 0.55
RIB_BUMP_H = 2.0        # height of the long-pill agitator ribs (see make_disc)
LONG_RADIAL = False     # rev 36 radial pockets: 7 of 24 low-fill trials clean, far worse
LONG_TRAIL_CHAMFER = False  # rev 37: off. It lifted a half-entered crosswise pill straight back
                            # out, in place, so it never got re-oriented (low-fill misses)
RADIAL_MIN_R_IN = 10.0   # a radial pocket must end at least this far from the centre, or its
                        # exit hole runs into the motor socket (size-0 capsules: 7.7 mm, so
                        # they keep rim-wise pockets on this 60 mm disc)
LONG_HUB = True
HUB_GAP, HUB_HEIGHT = 1.0, 6.0
# rev 40: straight-sided hub HUB_GAP inboard of the long-pill pockets, so the pool is a
# channel only ~1 mm wider than the pocket. A long pill can then skew ~10° at most: it
# cannot lie crosswise (the lock that stranded the last capsules) and cannot wedge as a
# strut (rev 35's hub was sized from the pill's length and left a 17 mm annulus, in which
# a 19 mm caplet did wedge). Straight walls, so no V to cradle a second pill (revs 26-28).
LONG_RIBS = False      # rev 39 speed-bump ribs did not break the capsule lock
LONG_CONE = False      # rev 29: the long-pill cone (revs 26-28) is switched off. It oriented the
                       # last few pills but cradled second pills (doubles) and pushed pills onto
                       # the pocket edge at the exit (jams): 21/24 clean at best, against 1 slow
                       # pickup in 90 campaign trials without it.
LONG_CONE_DEG = 60.0   # cone inboard of long-pill notches (see make_disc)
CONE_LEDGE = 2.5       # flat ledge between a long-pill notch and the cone. With the cone flush
                       # at the notch (rev 27) a second caplet was cradled in the V above a seated
                       # one: doubles in 8 of 24 trials. With a ledge (rev 26) there were none.
RIB_Z0, RIB_DEPTH, RIB_DEG = 0.3, 2.3, 50.0
# rev 24: the closed pocket works together with a rib ring on the hopper wall. The rib's
# underside starts RIB_Z0 above the disc at the wall and rises inward at RIB_DEG, so a
# tablet lying flat on the disc is stopped where the rib is as high as the top of its side
# band. The closed pocket's outer edge is put exactly there: a flat tablet drops straight
# in, and nothing can stand against the wall. (A closed pocket alone left tablets resting
# against the wall beyond it; the rib alone stopped them short of an open notch.)


def rib_stop_r(pill_id: str) -> float:
    """Radius of the outer edge of a flat tablet stopped by the rib."""
    p = PILLS[pill_id]
    band_top = (p.thickness + p.band) / 2
    return R_WALL - (band_top - RIB_Z0) / math.tan(math.radians(RIB_DEG))
# rev 23: closed pocket for pair-prone tablets. A tablet thinner than half the notch width
# can stand on edge beside a second one in an open notch (small tablets: 2 x 2.8 mm in
# 6.8 mm, 1 double in 10 trials). In a closed circular pocket one standing tablet only fits
# centred; a second has no room beside it and stays on the disc face, where it rolls away.
# (Rev 22's rib ring above the disc stopped pairs but stranded lone tablets: 2 of 24 clean.)


def pair_prone(pill_id: str, notch_w: float) -> bool:
    """True when a second tablet standing on edge beside a first (against the wall) would
    sink far enough into an open notch to be carried. The second tablet sinks until its
    chord fits the notch outline; it is carried when that sink exceeds about half of
    R(1 − cos 50°), the height a wheel of radius R needs to stay put on the 50° disc."""
    p = PILLS[pill_id]
    if p.kind != "tablet":
        return False
    rho, rad = notch_w / 2, (p.length - p.tol) / 2
    o = 2 * (p.thickness - p.tol) - rho          # inner face of the 2nd tablet, from notch centre
    if o >= rho:
        return False
    half_chord = min(rad, math.sqrt(rho * rho - o * o))
    sink = rad - math.sqrt(rad * rad - half_chord * half_chord)
    return sink > 0.5 * rad * (1 - math.cos(math.radians(BETA)))


def cone_base_r(pp: dict) -> float:
    """Long-pill cone starts CONE_LEDGE inboard of the notch's inner wall."""
    return pp["r_inner"] - CONE_LEDGE


def _rot_world(shape: cq.Workplane) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (1, 0, 0), BETA)


# ----------------------------------------------------------------------- parts
def make_disc(pp: dict) -> cq.Workplane:
    t = pp["depth"]
    disc = cq.Workplane("XY").circle(R_DISC).extrude(-t)          # z ∈ [-t, 0]
    # hub boss on the front: cone so pills slide off; carries the D-bore
    boss_h = max(0.0, 8.0 - t) + (CONE_H if pp.get("pocket") == "standing slot" else 0.0)
    if boss_h > 0:
        # r 8 → 5 (was 7 → 3.5 on the 3 mm motor shaft): leaves 1.8 mm round the 1/4" bore
        boss = cq.Workplane("XY").circle(8.0).workplane(offset=boss_h).circle(5.0).loft()
        disc = disc.union(boss)
    if pp.get("pocket") == "standing slot":
        r_top = pp["r_inner"] - CONE_H / math.tan(math.radians(CONE_DEG))
        ramp = (cq.Workplane("XY").circle(pp["r_inner"]).workplane(offset=CONE_H).circle(r_top).loft())
        disc = disc.union(ramp)
    if pp.get("cone_h", 0.0) > 0:
        # rev 26 (long pills): steep cone inboard of the notches. The pool becomes a channel
        # between cone and wall, as wide as the notch, so a caplet or capsule can only lie
        # along the rim (the notch direction). Without it, the last few pills lay pointing
        # down the slope, end-on to the wall, and never dropped in (1 miss in 80 trials).
        ch = pp["cone_h"]
        r_base = cone_base_r(pp)
        r_top = r_base - ch / math.tan(math.radians(LONG_CONE_DEG))
        disc = disc.union(cq.Workplane("XY").circle(r_base).workplane(offset=ch)
                          .circle(r_top).loft())
    if pp.get("hub_r", 0.0) > 0:
        # rev 35 (long pills): straight-sided central hub with a conical top. The annulus
        # between hub and wall is narrower than the pill is long, so the last few pills
        # cannot lie pointing down the slope (misses at 4 loaded). Unlike the rev 26-28
        # cone it stands well inboard of the pockets, so it forms no V beside a seated pill.
        hr, hh = pp["hub_r"], pp["hub_h"]
        hub = cq.Workplane("XY").circle(hr).extrude(hh)
        top = (cq.Workplane("XY").workplane(offset=hh).circle(hr)
               .workplane(offset=(hr - 4.0) * math.tan(math.radians(LONG_CONE_DEG))).circle(4.0).loft())
        disc = disc.union(hub).union(top)
    if pp.get("ribs", 0) > 0:
        # rev 39 (long pills): low speed-bump ribs on the face, inboard of the pocket track,
        # one per web. With a few pills left, two capsules locked each other (one lying
        # obliquely on the face, the other propped on it over the track) and nothing ever
        # moved them. The ribs pass under pills lying on the face once per pocket pitch and
        # nudge them; 45° flanks, so a pill rides over instead of being pushed.
        r0, r1 = 8.0, pp["r_inner"] - 1.0
        for k in range(pp["n"]):
            rib = (cq.Workplane("YZ").workplane(offset=r0)
                   .polyline([(-RIB_BUMP_H, 0), (0, RIB_BUMP_H), (RIB_BUMP_H, 0)]).close()
                   .extrude(r1 - r0))
            disc = disc.union(rib.rotate((0, 0, 0), (0, 0, 1), (k + 0.5) * pp["pitch_deg"]))
    chamfer = pp.get("chamfer", 0.0)
    for k in range(pp["n"]):
        tool = _extruded_notch(pp, -t - 1, t + 2)
        if t > undercut_land(pp) + 0.2:
            tool = tool.union(_tapered_notch(pp, -t, t - undercut_land(pp), undercut_at_back(pp), undercut_deg(pp)))
        # rev 4: 45° lead-in on the notch's top edges for long pills (stepped in 0.25 mm
        # layers so it prints as an upward-facing stair) — a misaligned pill is guided in
        # or lifted off instead of being shoved along the wall
        steps = int(round(chamfer / 0.25))
        for i in range(1, steps + 1):
            g = chamfer * i / steps
            tool = tool.union(_extruded_notch(pp, -g, g + 1, grow=g))
        # rev 32 (long pills): 45° lead-in on the TRAILING end wall only (the disc turns toward
        # +y in the notch frame, so the trailing end is at −y). A pill with one end dipped in
        # is lifted out by it instead of being pushed against the hopper wall (4 jams in 24
        # trials without it). The leading end stays square: a chamfer there gives a second
        # pill's tail a place to sit ahead of the seated pill (doubles).
        tc = pp.get("trail_chamfer", 0.0)
        tsteps = int(round(tc / 0.25))
        for i in range(1, tsteps + 1):
            g = tc * i / tsteps
            tool = tool.union(_extruded_notch(dict(pp, length=pp["length"] + g, y_shift=-g / 2),
                                              -g, g + 1))
        # rev 13 (standing slot): 45° chamfer on the INNER radial wall only, as a stair.
        # The top opening becomes wider than a flat tablet, so a tablet lying flat across
        # the slot slides down the chamfer and stands up in it (before, it bridged the
        # 7.45 mm gap like a manhole cover: 4 misses in 125 trials).
        ic = pp.get("inner_chamfer", 0.0)
        isteps = int(round(ic / 0.25))
        for i in range(1, isteps + 1):
            g = ic * i / isteps
            # step i: slot widened inward by g, from the top face down to depth (ic − g)
            tool = tool.union(_extruded_notch(dict(pp, r_inner=pp["r_inner"] - g),
                                              -(ic - g), (ic - g) + 1, grow=0))
        disc = disc.cut(tool.rotate((0, 0, 0), (0, 0, 1), k * pp["pitch_deg"]))
    # D-bore through boss and disc (through the cone too: no blind ceiling to bridge)
    hub_top = (pp["hub_h"] + (pp["hub_r"] - 4.0) * math.tan(math.radians(LONG_CONE_DEG))) if pp.get("hub_r", 0.0) > 0 else 0.0
    h_tot = t + max(boss_h, pp.get("cone_h", 0.0), hub_top)
    bore = (cq.Workplane("XY").workplane(offset=-t - 1).circle(DRIVE_D / 2 + 0.05)
            .extrude(h_tot + 2))
    flat_cut = (cq.Workplane("XY").workplane(offset=-t - 1)
                .center(DRIVE_FLAT - DRIVE_D / 2 + 0.05 + 2, 0).rect(4, 8).extrude(h_tot + 2))
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
        if pp.get("closed"):
            return circ
        rect = (cq.Workplane("XY").workplane(offset=z0).center((rc + outer) / 2, 0)
                .rect(outer - rc, w).extrude(h))
        return circ.union(rect)
    L = pp["length"] + 2 * grow
    r_in = pp["r_inner"] - grow
    return (cq.Workplane("XY").workplane(offset=z0).center((r_in + outer) / 2, pp.get("y_shift", 0.0))
            .rect(outer - r_in, L).extrude(h))


def _tapered_notch(pp: dict, z0: float, h: float, grow: float, taper: float) -> cq.Workplane:
    """Pocket outline grown by `grow` at z0, tapering inward by `taper` degrees over height h
    (so it meets the nominal outline at z0 + h). Used for the wall undercut."""
    outer = R_WALL + 3
    if pp["shape"] == "round":
        w = pp["width"] + 2 * grow
        rc = pp["r_center"]
        circ = (cq.Workplane("XY").workplane(offset=z0).center(rc, 0).circle(w / 2)
                .extrude(h, taper=taper))
        if pp.get("closed"):
            return circ
        rect = (cq.Workplane("XY").workplane(offset=z0).center((rc + outer) / 2, 0)
                .rect(outer - rc, w).extrude(h, taper=taper))
        return circ.union(rect)
    L = pp["length"] + 2 * grow
    r_in = pp["r_inner"] - grow
    return (cq.Workplane("XY").workplane(offset=z0).center((r_in + outer) / 2, 0)
            .rect(outer - r_in, L).extrude(h, taper=taper))


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


def drive_layout(z_front: float) -> dict:
    """Positions along the drive line, as local z. s = distance behind the plate's front."""
    L = {}
    L["tube_rear"] = z_front - BRG_TUBE
    L["collar_rear"] = L["tube_rear"] - COLLAR_BOSS - COLLAR_LEN
    L["shaft_front"] = z_front + RUN + 8.0            # top of the disc boss
    L["shaft_rear"] = L["shaft_front"] - DRIVE_LEN
    L["coupler_front"] = L["collar_rear"] - 1.5
    L["coupler_rear"] = L["coupler_front"] - COUPLER[1]
    L["gearbox_front"] = L["coupler_rear"] - 1.0
    L["socket_rear"] = L["gearbox_front"] - SADDLE[1]
    L["motor_rear"] = L["gearbox_front"] - MOTOR_LEN
    return L


def _add_drive(plate: cq.Workplane, z_front: float) -> cq.Workplane:
    """Bearing tube, rails and motor saddle behind the back plate. Everything is an
    extrusion along the axis (vertical walls when printed front face down); the only
    roofs are the 50° cone above the front bearing and the 50° gearbox stops."""
    L = drive_layout(z_front)
    zb = z_front - BP_T
    gw, gh = GEARBOX
    r_p = (BRG_OD + BRG_FIT) / 2
    r_o = r_p + BRG_WALL

    def box(x0, x1, y0, y1, z0, z1):
        return (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, (y0 + y1) / 2)
                .rect(x1 - x0, y1 - y0).extrude(z1 - z0))

    add = cq.Workplane("XY").workplane(offset=L["tube_rear"]).circle(r_o).extrude(BRG_TUBE - BP_T)
    add = add.union(box(-RAIL_X[1], RAIL_X[1], -6, 6, L["tube_rear"], zb))        # tube-to-rail webs
    for sx in (-1, 1):
        x0, x1 = sorted((sx * RAIL_X[0], sx * RAIL_X[1]))
        add = add.union(box(x0, x1, -gh / 2 - RUN + 0.2, SPINE_Y[1], L["socket_rear"], zb))
    add = add.union(box(-RAIL_X[1], RAIL_X[1], SPINE_Y[0], SPINE_Y[1], L["socket_rear"], zb))
    # motor saddle: walls at ±x and +y round the gearbox, open toward −y for the clamp strap.
    # Its front is relieved by a 50° cone, so it widens to the rails without a flat roof and
    # stays clear of the coupler.
    y_top = gh / 2 + RUN
    gf = L["gearbox_front"]
    sad = box(-RAIL_X[1], RAIL_X[1], -gh / 2 - RUN + 0.2, SPINE_Y[1], L["socket_rear"], gf + 1)
    sad = sad.cut(box(-gw / 2 - RUN, gw / 2 + RUN, -20, y_top, L["socket_rear"] - 1, gf + 2))
    sad = sad.cut(cq.Workplane("XY").workplane(offset=gf - SADDLE[0] - 1).circle(5.2)
                  .workplane(offset=SADDLE[0] + 2).circle(5.2 + (SADDLE[0] + 2) / math.tan(math.radians(50))).loft())
    # nothing but the rails and spine outside r 11: no flat roof in the corners
    sad = sad.intersect(cq.Workplane("XY").workplane(offset=L["socket_rear"]).circle(11.0)
                        .extrude(gf + 1 - L["socket_rear"]))
    add = add.union(sad)
    plate = plate.union(add)
    # front bearing pocket (open to the front, bearing recessed), 50° cone, shaft bore,
    # rear bearing pocket (open to the rear)
    z_p = z_front - BRG_RECESS - BRG_W
    plate = plate.cut(cq.Workplane("XY").workplane(offset=z_p).circle(r_p).extrude(BRG_RECESS + BRG_W + 1))
    plate = plate.cut(cq.Workplane("XY").workplane(offset=z_p - 3.0).circle(5.5)
                      .workplane(offset=3.0).circle(r_p).loft())
    plate = plate.cut(cq.Workplane("XY").workplane(offset=L["tube_rear"] - 1).circle(5.5).extrude(BRG_TUBE))
    plate = plate.cut(cq.Workplane("XY").workplane(offset=L["tube_rear"] - 1).circle(r_p).extrude(BRG_W + 1))
    # M2 pilot holes for the clamp strap, along y from the open side
    zc = (L["socket_rear"] + L["gearbox_front"]) / 2
    for sx in (-1, 1):
        plate = plate.cut(cq.Workplane("XZ").workplane(offset=gh / 2 + RUN + 1)
                          .center(sx * CLAMP_X, zc).circle(0.9).extrude(9))
    return plate


CLAMP_X = 13.5


def make_spacer() -> cq.Workplane:
    """Thrust ring between the disc's back face and the front bearing's inner race. Its
    thickness sets the disc-to-plate running gap."""
    return cq.Workplane("XY").circle(4.5).circle(DRIVE_D / 2 + 0.1).extrude(BRG_RECESS + RUN)


def make_collar() -> cq.Workplane:
    """Set-screw collar behind the rear bearing: M3 × 6 screw into a captured M3 nut."""
    c = cq.Workplane("XY").circle(9.0).extrude(COLLAR_LEN)
    c = c.union(cq.Workplane("XY").workplane(offset=COLLAR_LEN).circle(4.5).extrude(COLLAR_BOSS))
    c = c.cut(cq.Workplane("XY").workplane(offset=-1).circle(DRIVE_D / 2 + 0.1).extrude(COLLAR_LEN + 3))
    # nut slot open to the flat end face, screw hole along +x at mid-length
    c = c.cut(cq.Workplane("XY").workplane(offset=-1).center(5.9, 0).rect(2.7, 5.8)
              .extrude(COLLAR_LEN + 2))
    zc, r = COLLAR_LEN / 2, 1.65          # teardrop hole: prints without support, axis upright
    c = c.cut(cq.Workplane("YZ").center(0, zc).circle(r).extrude(10))
    c = c.cut(cq.Workplane("YZ").polyline([(-r * 0.7071, zc + r * 0.7071), (0, zc + r * 1.5),
                                           (r * 0.7071, zc + r * 0.7071)]).close().extrude(10))
    return c


def make_backplate(pp: dict) -> cq.Workplane:
    zb, z_front = backplate_z(pp)
    pp = dict(pp, closed=False)   # the exit hole is open to the bore even for closed pockets
    plate = cq.Workplane("XY").workplane(offset=zb).circle(FLANGE_R).extrude(BP_T)
    # exit hole = notch grown by EXIT_MARGIN, bounded by the hopper bore, continued as a
    # duct straight back (perpendicular to the plate: vertical walls when printed)
    em = EXIT_MARGIN + undercut_at_back(pp)     # hole clears the undercut pocket's back outline
    hole = (_extruded_notch(pp, zb - DUCT_LEN - 1, BP_T + DUCT_LEN + 2, grow=em,
                            outer=R_WALL).rotate((0, 0, 0), (0, 0, 1), EXIT_ANGLE)
            .union(_relief_prism(pp, zb - DUCT_LEN - 1, BP_T + DUCT_LEN + 2)))
    duct = (_extruded_notch(pp, zb - DUCT_LEN, DUCT_LEN, grow=em + 1.6,
                            outer=R_WALL + 1.6).rotate((0, 0, 0), (0, 0, 1), EXIT_ANGLE)
            .union(_relief_prism(pp, zb - DUCT_LEN, DUCT_LEN + BP_T, grow=1.6)))
    plate = plate.union(duct).cut(hole)
    # beam-break LED holes across the duct (along local x), teardrop roof toward −z
    hw = (pp["length"] if pp["shape"] == "oblong" else pp["width"]) / 2 + EXIT_MARGIN + 1.6
    plate = plate.cut(_teardrop_x(-hw - 2, hw + 2, pp["r_center"], zb - BEAM_Z, 1.6))
    plate = _add_drive(plate, z_front)
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
    wall = _bore_solid(z0, HOPPER_TOP, WALL).cut(_bore_solid(z0 - 1, HOPPER_TOP + 1, 0.0))
    flange = (cq.Workplane("XY").workplane(offset=z0).circle(FLANGE_R).circle(R_WALL)
              .extrude(3.0)
              .cut(cq.Workplane("XY").workplane(offset=z0 - 1)
                   .polarArray(BOLT_R, 45, 360, 4).circle(1.7).extrude(5)))
    # exit relief (rev 3/6): a groove in the bore over the exit, the full height of the
    # hopper (it sits under the cover, where no pills go). A pill at the exit, flat or
    # standing, has no wall to lean on. Full height = vertical walls, nothing to support.
    relief = _relief_prism(pp, z0 - 1, HOPPER_TOP - z0 + 2)
    boss = (_relief_prism(pp, z0, HOPPER_TOP - z0, grow=WALL)
            .cut(_relief_prism(pp, z0 - 1, HOPPER_TOP - z0 + 2)))
    body = wall.union(flange).union(boss)
    if pp.get("closed"):
        k = math.tan(math.radians(RIB_DEG))
        # 50° underside, then a straight liner parallel to the wall up to the top: a short top
        # face is level in the tilted assembly (pills sat on it) and a long taper is a slope
        # shallower than the friction angle (a tablet stuck on it)
        rib = (cq.Workplane("XZ").polyline([(R_WALL + 0.5, RIB_Z0 - 0.5 * k),
                                            (R_WALL - RIB_DEPTH, RIB_Z0 + RIB_DEPTH * k),
                                            (R_WALL - RIB_DEPTH, HOPPER_TOP),
                                            (R_WALL + 0.5, HOPPER_TOP)]).close()
               .revolve(360, (0, 0, 0), (0, 1, 0)))
        rib = rib.intersect(_bore_solid(z0, HOPPER_TOP, WALL))   # keep it inside the leaning shell
        # no liner across the exit relief (it would be left as a thin free-standing skin)
        half = math.degrees((pp["length"] / 2 + EXIT_MARGIN) / R_WALL) + 1.0
        ramp = math.degrees((RELIEF / math.tan(math.radians(RELIEF_RAMP))) / R_WALL)
        a0, a1 = (math.radians(EXIT_ANGLE - half - ramp - 2), math.radians(EXIT_ANGLE + half + ramp + 2))
        far = 2 * FLANGE_R
        wedge = (cq.Workplane("XY").workplane(offset=z0 - 1)
                 .polyline([(0, 0), (far * math.cos(a0), far * math.sin(a0)),
                            (far * math.cos((a0 + a1) / 2), far * math.sin((a0 + a1) / 2)),
                            (far * math.cos(a1), far * math.sin(a1))]).close()
                 .extrude(HOPPER_TOP - z0 + 2))
        rib = rib.cut(wedge)
        # room for the cover's locating lip (the cover closes y > COVER_Y)
        rib = rib.cut(cq.Workplane("XY").workplane(offset=HOPPER_TOP - 3.3)
                      .center(0, COVER_Y - 1 + FLANGE_R).rect(4 * FLANGE_R, 2 * FLANGE_R).extrude(5))
        body = body.union(rib)
    return body.cut(relief)


def make_cover() -> cq.Workplane:
    """Half-lid over the upper half of the hopper (y > COVER_Y): pills can only be poured into
    the lower half, so nothing lands on the exit side. A 3 mm lip locates it in the bore."""
    plate = (cq.Workplane("XY").workplane(offset=HOPPER_TOP).circle(R_WALL + WALL).extrude(2.4))
    lip = (cq.Workplane("XY").workplane(offset=HOPPER_TOP - 3).circle(R_WALL - 0.15)
           .circle(R_WALL - 1.75).extrude(3))
    half = (cq.Workplane("XY").workplane(offset=HOPPER_TOP - 4)
            .center(0, (R_WALL + WALL + 2) / 2 + COVER_Y).rect(2 * (R_WALL + WALL) + 2, R_WALL + WALL + 2)
            .extrude(8))
    return plate.union(lip).intersect(half)


def make_clamp() -> cq.Workplane:
    """Strap across the open side of the motor saddle (2× M2 × 8 self-tapping into the rails)."""
    return (cq.Workplane("XY").rect(2 * CLAMP_X + 6, 6).extrude(3.0)
            .cut(cq.Workplane("XY").pushPoints([(-CLAMP_X, 0), (CLAMP_X, 0)]).circle(1.1).extrude(4)))


BASE_FRONT = 45.0    # extra base length under the hopper
BASE_Z = -78.0       # world z of the table / base plate top (was −46 before the shaft drive:
                     # the motor's rear end and the longer duct need 32 mm more height)
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
    # the plate reaches BASE_FRONT further forward than the side plates: the hopper leans
    # ~56 mm out over the front, and a wider footprint keeps it from tipping when pouring
    y0, y1 = bb.ymin - 5 - BASE_FRONT, max(bb.ymax + 5, cup_centre(pp_ref)[1] + 26)
    base = (cq.Workplane("XY").workplane(offset=BASE_Z - 6)
            .center(0, (y0 + y1) / 2).rect(2 * (x_in + SIDE_T + 8), y1 - y0).extrude(6))
    for sx in (-1, 1):
        x_c = sx * (x_in + SIDE_T / 2)
        base = base.cut(cq.Workplane("XY").workplane(offset=BASE_Z - 3)
                        .center(x_c, (bb.ymin + bb.ymax) / 2).rect(SIDE_T + 0.4, bb.ylen + 0.4)
                        .extrude(4))
    return base


def cup_centre(pp_ref: dict):
    """Under the duct mouth, and clear of the motor's rear end."""
    zb, zf = backplate_z(pp_ref)
    mouth = _world((0.0, pp_ref["r_center"], zb - DUCT_LEN))
    motor = _world((0.0, 0.0, drive_layout(zf)["motor_rear"]))
    return mouth[0], max(mouth[1] + 4, motor[1] + 4 + 22)


def make_cup(pp_ref: dict) -> cq.Workplane:
    """Pill cup under the end of the exit duct (world). Ø44 × 18 mm, 1.6 mm walls."""
    cx, cy = cup_centre(pp_ref)
    return (cq.Workplane("XY").workplane(offset=BASE_Z).center(cx, cy).circle(22).extrude(18)
            .cut(cq.Workplane("XY").workplane(offset=BASE_Z + 1.6).center(cx, cy).circle(20.4)
                 .extrude(18)))


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
    Sized from the thickest disc so they fit every pill's assembly."""
    ref = max((pocket_params(p) for p in PILLS), key=lambda q: q["depth"])
    common = OUT / "common"
    common.mkdir(parents=True, exist_ok=True)
    side = make_side(ref)
    parts = [
        ("cover", _rot_world(make_cover()), [-BETA + 180, 0, 0], 4.0),
        ("clamp", make_clamp(), [0, 0, 0], 4.0),
        ("spacer", make_spacer(), [0, 0, 0], 4.0),
        ("collar", make_collar(), [0, 0, 0], 4.0),
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
