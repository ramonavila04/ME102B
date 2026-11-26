#!/usr/bin/env python3
"""Concept: the V2 inclined-disc module with a VERTICAL canister, on the V7 housing.

    python cad/variants/v2_v7_vertical/concept.py        # writes concept/*.stl, prints checks

The V7-fit module (cad/variants/v2_v7_module) keeps the V2 hopper, a cylinder coaxial with
the disc, so it leans 40 deg outward and the hopper tops reach 148 mm from the axis. Here
only the part of the hopper next to the disc is kept (the bore that the disc's pockets fill
from, STUB_L along the axis, with the exit relief); above it a throat turns into an upright
canister standing over the module, as the V7 canisters do. Everything behind the disc
(back plate, duct, bearings, 1:1 gears, gearmotor, stand) is the v2_v7_module's, unchanged.

The V2 half-cover moves down to the top of the stub: tablets falling down the canister land
on it (it lies at the disc's 50 deg) and slide into the lower half of the bore, away from
the exit at the top of the disc, as in the V2.

CONCEPT ONLY: sized and clash-checked, not yet split for printing or simulated.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_s = importlib.util.spec_from_file_location("v7m", ROOT / "cad" / "variants" / "v2_v7_module" / "build.py")
m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m)
b = m.b

STUB_L = 20.0        # bore kept along the axis from the hopper flange: 15 mm in front of the disc
                     # face (V2: HOPPER_DEPTH 70); longer would push the bore wall past r 111
CAN_R = 30.0         # canister inner radius (V7 canister: 67.5 mm square outside)
CAN_WALL = 2.4
CAN_TOP_Z = 147.5    # canister top above the deck, as the V7 canisters
CAN_Y = 6.0          # canister axis, module y (+ = outward): 6 mm out of the V7 canister line,
                     # so the throat's inner side is steep enough (tube edge at r 110)
THROAT_Z = 128.0     # where the throat becomes the vertical canister (module z): high enough that
                     # every throat wall is 45 deg or steeper


R_ENVELOPE = 111.0   # everything stays inside the V7 body's 113 mm radius (2 mm margin)


def envelope_local():
    """The V7 body's cylinder (enclosure axis, r R_ENVELOPE) in the local disc frame."""
    cyl = cq.Workplane("XY").workplane(offset=-50).center(0, -m.MOD_R).circle(R_ENVELOPE).extrude(400)
    return m.from_module(cyl)


def stub(pp):
    """V2 hopper (flange, bore wall, exit-relief boss) cut off STUB_L above its flange, and
    its flange trimmed to the V7 body's radius."""
    h = m.make_hopper(pp)
    z0 = -pp["depth"] - b.RUN
    keep = cq.Workplane("XY").workplane(offset=z0 - 5).rect(400, 400).extrude(STUB_L + 5)
    return h.intersect(keep).intersect(envelope_local())


def cover_at_stub(pp):
    """The V2 half-cover, moved from the hopper top down to the top of the stub."""
    z0 = -pp["depth"] - b.RUN
    return b.make_cover().translate((0, 0, (z0 + STUB_L) - b.HOPPER_TOP))


def _rings(pp, z_l, inset, lift, wall, chord=None):
    """Matching polygon rings: the stub's actual bore opening at local height z_l (the V2
    bore narrows on the pool side, so it is not a circle), and the upright tube at
    THROAT_Z + lift. Point k of both rings points the same way in plan, so the ruled throat
    between them cannot twist."""
    n = 96
    lo, hi = [], []
    c0 = m.pt_module((0.0, 0.0, z_l))
    for k in range(n):
        th = 2 * math.pi * k / n
        r = b.bore_r(th, z_l) + wall - inset   # bore_r takes the height above the disc face
        x, y = r * math.cos(th), r * math.sin(th)
        if chord is not None and y > chord:
            y = chord                           # D-shaped opening: straight edge along the cover
        lo.append(cq.Vector(*m.pt_module((x, y, z_l))))
        d = m.pt_module((math.cos(th), math.sin(th), z_l))
        phi = math.atan2(d[1] - c0[1], d[0] - c0[0])
        R = CAN_R + wall
        hi.append(cq.Vector(R * math.cos(phi), CAN_Y + R * math.sin(phi), THROAT_Z + lift))
    return cq.Wire.makePolygon(lo, close=True), cq.Wire.makePolygon(hi, close=True)


def throat_and_canister(pp):
    """Ruled throat from the stub's top opening (in the disc's tilted plane) to the upright
    tube. The inner loft runs 1 mm past both ends, so the cut opens them cleanly."""
    z0 = -pp["depth"] - b.RUN
    z_l = z0 + STUB_L - 1.0          # 1 mm inside the stub: the solids overlap
    # The throat starts from the bore's lower part only: a D-shaped opening whose straight
    # edge is the half-cover's edge (local y = COVER_Y). Tablets then never reach the cover's
    # top, where its 50 deg face met the throat wall in a near-level crease that held them.
    outer = cq.Solid.makeLoft(list(_rings(pp, z_l, 0.0, 0.0, b.WALL, chord=b.COVER_Y + b.WALL)), True)
    inner = cq.Solid.makeLoft(list(_rings(pp, z_l - 1.0, 0.0, 1.0, 0.0, chord=b.COVER_Y)), True)
    return cq.Workplane(obj=outer).cut(cq.Workplane(obj=inner))


def tube():
    return (cq.Workplane("XY").workplane(offset=THROAT_Z - 1.0).center(0, CAN_Y)
            .circle(CAN_R + CAN_WALL).circle(CAN_R).extrude(CAN_TOP_Z - THROAT_Z + 1.0))


def module_bodies(kit: str):
    """(name, solid in the module frame) for one vertical-canister module."""
    sp = importlib.util.spec_from_file_location("v7asm", ROOT / "cad" / "variants" / "v2_v7_module" / "assemble.py")
    a = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(a)
    pp = b.pocket_params(kit)
    out = [(n, s) for n, c, s, bought in a.module_bodies(kit) if n not in ("hopper", "cover")]
    out.append(("stub", m.to_module(stub(pp))))
    out.append(("cover", m.to_module(cover_at_stub(pp))))
    out.append(("throat", throat_and_canister(pp)))
    out.append(("canister", tube()))
    return out


def module_to_world(shape):
    """Module frame -> the V2 world frame the simulator uses (to_module's inverse without
    the tilt: the module frame is the V2 world turned 180 deg about z and moved)."""
    return shape.translate((0, -m.Y0, -m.Z0)).rotate((0, 0, 0), (0, 0, 1), 180)


def export_sim(kit: str, out: Path):
    """Static parts in the V2 world, for the simulator: the bore stub, the throat + upright
    canister, and the cover. Stub and throat overlap by 1 mm; the simulator collides each
    static part on its own, so they are not unioned (OpenCASCADE's boolean of the curved bore
    and the ruled throat fails for some disc depths)."""
    pp = b.pocket_params(kit)
    out.mkdir(parents=True, exist_ok=True)
    for name, shape in (("sim_hopper", m.to_module(stub(pp))), ("sim_throat", throat_and_canister(pp)),
                        ("sim_canister", tube()),
                        ("sim_cover", m.to_module(cover_at_stub(pp)))):
        cq.exporters.export(module_to_world(shape), str(out / f"{name}.stl"), tolerance=0.02, angularTolerance=0.08)


if __name__ == "__main__":
    kit = sys.argv[1] if len(sys.argv) > 1 else "iron"
    (HERE / "concept").mkdir(exist_ok=True)
    bodies = module_bodies(kit)
    for n, s in bodies:
        if n in ("stub", "cover", "throat", "canister"):
            cq.exporters.export(s, str(HERE / "concept" / f"{n}.stl"), tolerance=0.05)
    allv = [v for _, s in bodies for v in s.vals()[0].Vertices()] if False else None
    comp = cq.Compound.makeCompound([s.val() for _, s in bodies])
    bb = comp.BoundingBox()
    r = max(math.hypot(v.X, v.Y + m.MOD_R) for v in comp.Vertices())
    print(f"one module: x {bb.xmin:.0f}..{bb.xmax:.0f}, y {bb.ymin:.0f}..{bb.ymax:.0f}, z {bb.zmin:.0f}..{bb.zmax:.0f}; "
          f"furthest point {r:.0f} mm from the enclosure axis")
