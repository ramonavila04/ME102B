#!/usr/bin/env python3
"""The V2 inclined-disc module with a VERTICAL canister, on the V7 housing.

    python cad/variants/v2_v7_vertical/concept.py [iron|small]
        writes <kit>/stub.stl, <kit>/canister.stl, <kit>/manifest.json (printable parts),
        <kit>/sim_*.stl (simulator) and concept/*.stl, and prints the module's size
    python cad/check_printability.py cad/variants/v2_v7_vertical/<kit>/manifest.json

The V7-fit module (cad/variants/v2_v7_module) keeps the V2 hopper, a cylinder coaxial with
the disc, so it leans 40 deg outward and the hopper tops reach 148 mm from the axis. Here
only the part of the hopper next to the disc is kept (the bore that the disc's pockets fill
from, STUB_L along the axis, with the exit relief); above it a throat turns into an upright
canister standing over the module, as the V7 canisters do. Everything behind the disc
(back plate, duct, bearings, 1:1 gears, gearmotor, stand) is the v2_v7_module's, unchanged.

The throat opens into the bore through a D-shaped mouth whose straight edge is where the V2
half-cover's edge was, and the throat's solid closes the upper half of the bore: tablets
falling down the canister slide down its flat wall into the lower half of the bore, away from
the exit at the top of the disc, as in the V2. No separate cover.

Printed as two parts per module in place of the V2 hopper and cover: the stub (flange down,
bolted to the back plate as the hopper was) and the canister (throat + cap + upright rim, one
piece, open top on the bed), glued onto the stub's top face and located by the cap slab.
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
THROAT_Z = 144.0     # where the throat becomes the vertical canister (module z). The throat's
                     # inner (flat) wall must rise from the bore's top rim to the tube steeper
                     # than the stub's 50 deg top face, or the wall and the outside meet in a
                     # knife edge; at 144 every throat wall is 61 deg or steeper. That leaves a
                     # 2.5 mm upright rim at the top.


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


def _rings(pp, z_l, inset, lift, wall, chord=None):
    """Matching polygon rings: the stub's actual bore opening at local height z_l (the V2
    bore narrows on the pool side, so it is not a circle), and the upright tube at
    THROAT_Z + lift. Point k of both rings points the same way in plan, so the ruled throat
    between them cannot twist."""
    n = 360
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
    """Ruled throat from the stub's top opening (in the disc's tilted plane) up to the
    canister top. The inner loft runs 1 mm past both ends, so the cut opens them cleanly."""
    z0 = -pp["depth"] - b.RUN
    z_l = z0 + STUB_L - 1.0          # 1 mm inside the stub: the solids overlap
    # The throat's outside follows the whole bore, but its opening is D-shaped: the straight
    # edge is the V2 half-cover's edge (local y = COVER_Y). The solid between them caps the
    # upper half of the stub, so the throat does the cover's job and there is no separate
    # cover: with one, its top face and the throat's flat wall made a level V-groove that
    # held tablets. Now the flat wall runs straight down into the bore.
    # One ruled loft through three matching rings (the bore opening, THROAT_Z, the canister
    # top) for the outside, and one for the opening: throat and upright tube are one solid
    # with no joint, so no ledge or sliver where they meet.
    def loft(z, lift, wall, chord, top_extra, inset=0.0):
        lo, hi = _rings(pp, z, inset, lift, wall, chord=chord)
        top = hi.translate(cq.Vector(0, 0, CAN_TOP_Z + top_extra - (THROAT_Z + lift)))
        return cq.Solid.makeLoft([lo, hi, top], True)
    outer = loft(z_l, 0.0, b.WALL, None, 0.0)
    # closed-pocket kits line the stub's bore with a RIB_DEPTH rib: the opening starts at the
    # lined bore, so the rib's cut end is not left as a shelf at the joint
    liner = b.RIB_DEPTH if pp.get("closed") else 0.0
    inner = loft(z_l - 1.0, 0.0, 0.0, b.COVER_Y, 1.0, inset=liner)
    throat = cq.Workplane(obj=outer).cut(cq.Workplane(obj=inner))
    return throat


CAP_T = 2.4          # slab under the throat's cap (local z, into the stub's bore)
CAP_CLEAR = 0.15     # radial clearance to the bore, as the V2 cover's lip


def cap_slab(pp):
    """The flat wall leaves the D's straight edge almost along the stub's top plane, so the
    solid closing the upper half of the bore is a knife-edge wedge there. This slab, CAP_T
    thick, fills the bore's upper half (local y > COVER_Y) just below the stub's top, as the V2
    cover's lip did: it makes the cap solid, and it locates the throat in the stub. Its
    straight edge faces down (local -y is 40 deg below level in the module), so tablets
    sliding off the flat wall fall past it into the lower half of the bore."""
    z0 = -pp["depth"] - b.RUN
    z_top = z0 + STUB_L
    liner = b.RIB_DEPTH if pp.get("closed") else 0.0   # closed-pocket kits line the bore with a rib

    def rad(th):
        return min(b.bore_r(th, z_top), b.bore_r(th, z_top - CAP_T - 0.5)) - liner - CAP_CLEAR

    def ends(lo, hi):                    # where the bore outline crosses y = COVER_Y
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if (rad(mid) * math.sin(mid) > b.COVER_Y) == (rad(lo) * math.sin(lo) > b.COVER_Y):
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    t0, t1 = ends(0.0, math.pi / 2), ends(math.pi, math.pi / 2)
    n = 180
    ts = [t0 + (t1 - t0) * k / n for k in range(n + 1)]
    # 8 deg draft on the curved edge (narrower at the bottom): printed with the tube end on the
    # bed, the top of that edge would otherwise overhang at 40 deg.
    d = (CAP_T + 0.5) * math.tan(math.radians(8.0))

    def ring(z, dr):
        return cq.Wire.makePolygon([cq.Vector((rad(t) - dr) * math.cos(t), (rad(t) - dr) * math.sin(t), z)
                                    for t in ts], close=True)
    slab = cq.Workplane(obj=cq.Solid.makeLoft([ring(z_top - CAP_T, d), ring(z_top + 0.5, 0.0)], True))
    return m.to_module(slab)


def module_bodies(kit: str):
    """(name, solid in the module frame) for one vertical-canister module."""
    sp = importlib.util.spec_from_file_location("v7asm", ROOT / "cad" / "variants" / "v2_v7_module" / "assemble.py")
    a = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(a)
    pp = b.pocket_params(kit)
    out = [(n, s) for n, c, s, bought in a.module_bodies(kit) if n not in ("hopper", "cover")]
    out.append(("stub", m.to_module(stub(pp))))
    out.append(("throat", throat_and_canister(pp)))
    out.append(("cap", cap_slab(pp)))
    return out


def module_to_world(shape):
    """Module frame -> the V2 world frame the simulator uses (to_module's inverse without
    the tilt: the module frame is the V2 world turned 180 deg about z and moved)."""
    return shape.translate((0, -m.Y0, -m.Z0)).rotate((0, 0, 0), (0, 0, 1), 180)


def export_sim(kit: str, out: Path):
    """Static parts in the V2 world, for the simulator: the bore stub, the throat + upright
    canister. Stub and throat overlap by 1 mm; the simulator collides each
    static part on its own, so they are not unioned (OpenCASCADE's boolean of the curved bore
    and the ruled throat fails for some disc depths)."""
    pp = b.pocket_params(kit)
    out.mkdir(parents=True, exist_ok=True)
    for name, shape in (("sim_hopper", m.to_module(stub(pp))), ("sim_throat", throat_and_canister(pp)),
                        ("sim_cap", cap_slab(pp))):
        cq.exporters.export(module_to_world(shape), str(out / f"{name}.stl"), tolerance=0.02, angularTolerance=0.08)


def _mesh(shape, tol=0.03):
    import tempfile
    import trimesh
    f = tempfile.NamedTemporaryFile(suffix=".stl", delete=False).name
    cq.exporters.export(shape, f, tolerance=tol, angularTolerance=0.08)
    return trimesh.load(f)


def export_print(kit: str, out: Path):
    """Printable parts: the stub (the V2 hopper cut down; flange down as saved) and the
    canister (throat + cap slab + upright tube as one part, printed with the tube's open top
    on the bed). The throat is trimmed at the stub's top face, where the two are glued; the
    cap slab sits inside the stub's bore with CAP_CLEAR all round and locates the canister,
    as the V2 cover's lip did. A mesh union (manifold3d), since OpenCASCADE's fuse of the
    ruled throat and the slab is not a valid solid."""
    import json
    import numpy as np
    import manifold3d as m3
    import trimesh
    pp = b.pocket_params(kit)
    out.mkdir(parents=True, exist_ok=True)
    M = lambda t: m3.Manifold(m3.Mesh(np.asarray(t.vertices, np.float32), np.asarray(t.faces, np.uint32)))
    z_top = -pp["depth"] - b.RUN + STUB_L
    o = np.array(m.pt_module((0.0, 0.0, 0.0)))
    nrm = np.array(m.pt_module((0.0, 0.0, 1.0))) - o           # local +z in the module frame
    off = float(np.dot(nrm, np.array(m.pt_module((0.0, 0.0, z_top)))))
    throat = M(_mesh(throat_and_canister(pp))).trim_by_plane(nrm.tolist(), off)
    can = throat + M(_mesh(cap_slab(pp)))
    mm = can.to_mesh()
    t = trimesh.Trimesh(mm.vert_properties[:, :3], mm.tri_verts)
    t.export(out / "canister.stl")
    cq.exporters.export(stub(pp), str(out / "stub.stl"), tolerance=0.03, angularTolerance=0.08)
    man = dict(variant="v2_v7_vertical", pill=kit, parts=[
        dict(name="stub", stl="stub.stl", print_rotation=[0, 0, 0], bed="flange down (as saved)"),
        dict(name="canister", stl="canister.stl", print_rotation=[180, 0, 0],
             bed="open top of the tube down"),
    ], clearances=[])
    (out / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    kit = sys.argv[1] if len(sys.argv) > 1 else "iron"
    (HERE / "concept").mkdir(exist_ok=True)
    export_print(kit, HERE / kit)
    export_sim(kit, HERE / kit)
    bodies = module_bodies(kit)
    for n, s in bodies:
        if n in ("stub", "throat", "cap"):
            cq.exporters.export(s, str(HERE / "concept" / f"{n}.stl"), tolerance=0.05)
    comp = cq.Compound.makeCompound([s.val() for _, s in bodies])
    bb = comp.BoundingBox()
    r = max(math.hypot(v.X, v.Y + m.MOD_R) for v in comp.Vertices())
    print(f"one module: x {bb.xmin:.0f}..{bb.xmax:.0f}, y {bb.ymin:.0f}..{bb.ymax:.0f}, z {bb.zmin:.0f}..{bb.zmax:.0f}; "
          f"furthest point {r:.0f} mm from the enclosure axis")
