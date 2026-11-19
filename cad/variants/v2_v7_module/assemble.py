#!/usr/bin/env python3
"""Assemble the V7 module and place six of them on the V7 enclosure.

    python cad/variants/v2_v7_module/assemble.py            # iron kit
    python cad/variants/v2_v7_module/assemble.py small --check

Writes
  <kit>/module_assembly.step   one module, every printed part plus the bought drive parts
                               (shaft, bearings, gearmotor) as reference solids
  <kit>/v7_assembly.step       the V7 enclosure (from cad/onshape) with its six original
                               modules replaced by six of these
With --check, it also reports overlaps between parts, with the enclosure and with the
neighbouring modules.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_spec = importlib.util.spec_from_file_location("v7_build", HERE / "build.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
b = m.b

V7_STEP = ROOT / "cad" / "onshape" / "V7_Pill_Dispenser_Heat_Inserts.step"
V7_KEEP = ["Enclosure", "Funnel <1>", "Funnel_mounts", "Weighing_station", "Front_panel_controls",
           "Station_fasteners"]


def cyl(r, z0, z1, r_in=0.0):
    w = cq.Workplane("XY").workplane(offset=z0).circle(r)
    if r_in:
        w = w.circle(r_in)
    return w.extrude(z1 - z0)


def module_bodies(kit: str):
    """[(name, colour, solid in the module frame, bought?)]"""
    pp = b.pocket_params(kit)
    L = m.frames(pp)
    zf = L["z_front"]
    brg_front = zf - b.BRG_RECESS
    gw, gh = b.GEARBOX
    gf = L["gear_front"]
    loc = [
        ("disc", "orange", b.make_disc(pp), False),
        ("backplate", "gray20", m.make_backplate(pp), False),
        ("hopper", "lightblue", m.make_hopper(pp), False),
        ("cover", "lightblue", b.make_cover(), False),
        ("spacer", "orange", b.make_spacer().translate((0, 0, brg_front)), False),
        ("rear_spacer", "orange", m.make_rear_spacer().translate((0, 0, L["tube_rear"] - m.GEAR_GAP)), False),
        ("shaft_gear", "orange", m.make_shaft_gear().translate((0, 0, gf)), False),
        ("motor_gear", "orange", m.make_motor_gear().rotate((0, 0, 0), (0, 0, 1), 360 / m.GEAR_Z / 2)
         .translate((0, -m.CD, gf)), False),
        ("motor_mount", "gray20", m.make_motor_mount().translate((0, -m.CD, L["mount_front"])), False),
        ("strap", "gray20", m.make_strap().translate((0, 0, -1.5)).rotate((0, 0, 0), (1, 0, 0), 90)
         .translate((0, -m.CD - gh / 2 - b.RUN - 1.5, L["mount_front"] - m.MOUNT_L / 2 - 1)), False),
        ("shaft_quarter_inch", "gray80", cyl(b.DRIVE_D / 2, L["shaft_rear"], L["shaft_front"]), True),
        ("bearing_front_R4ZZ", "blue", cyl(b.BRG_OD / 2, brg_front - b.BRG_W, brg_front, 4.7), True),
        ("bearing_rear_R4ZZ", "blue", cyl(b.BRG_OD / 2, L["tube_rear"], L["tube_rear"] + b.BRG_W, 4.7), True),
        ("gearmotor", "gold",
         cq.Workplane("XY").workplane(offset=L["motor_end"]).center(0, -m.CD).rect(gw, gh)
         .extrude(m.MOTOR_LEN)
         .union(cyl(b.SHAFT_D / 2, L["gearbox_face"], L["gearbox_face"] + 9.0).translate((0, -m.CD, 0))), True),
    ]
    out = [(n, c, m.to_module(s), bought) for n, c, s, bought in loc]
    ref = max((b.pocket_params(p) for p in m.KITS), key=lambda q: q["depth"])
    cheek = m.make_cheek(ref)
    out += [("cheek_right", "gray", cheek, False), ("cheek_left", "gray", cheek.mirror("YZ"), False),
            ("base", "gray", m.make_base(ref), False)]
    return out


def to_enclosure(shape, k: int):
    """Module frame → V7 enclosure frame for module k (0..5)."""
    return shape.translate((0, m.MOD_R, 0)).rotate((0, 0, 0), (0, 0, 1), m.MOD_ANGLES[k] - 90)


def v7_parts():
    sys.argv_backup = sys.argv
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence, TDF_Label
    from OCP.TDataStd import TDataStd_Name
    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.ReadFile(str(V7_STEP))
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name(l):
        a = TDataStd_Name()
        return a.Get().ToExtString() if l.FindAttribute(TDataStd_Name.GetID_s(), a) else "?"

    labs = TDF_LabelSequence()
    st.GetFreeShapes(labs)
    top = labs.Value(1)
    ch = TDF_LabelSequence()
    st.GetComponents_s(top, ch)
    out = []
    for i in range(1, ch.Length() + 1):
        n = name(ch.Value(i))
        if any(n.startswith(k) for k in V7_KEEP):
            out.append((n.split(" <")[0], cq.Workplane(obj=cq.Shape.cast(st.GetShape_s(ch.Value(i))))))
    return out


def _vol(a, c):
    try:
        return a.intersect(c).val().Volume()
    except Exception:
        return 0.0


def check(kit: str):
    bodies = module_bodies(kit)
    print(f"== {kit}: overlaps inside one module (shaft-in-bore and press fits expected)")
    for (n1, _, s1, _), (n2, _, s2, _) in itertools.combinations(bodies, 2):
        v = _vol(s1, s2)
        if v > 0.5:
            print(f"  {n1} / {n2}: {v:.1f} mm³")
    one = [to_enclosure(s, 0) for _, _, s, _ in bodies]
    nb = [to_enclosure(s, 1) for _, _, s, _ in bodies] + [to_enclosure(s, 5) for _, _, s, _ in bodies]
    print("== against the neighbouring modules (2 and 6)")
    hits = 0
    for (n1, _, _, _), s1 in zip(bodies, one):
        for s2 in nb:
            v = _vol(s1, s2)
            if v > 0.5:
                print(f"  {n1}: {v:.1f} mm³")
                hits += 1
    print("  none" if not hits else "")
    print("== against the V7 enclosure parts")
    hits = 0
    for vn, vs in v7_parts():
        for (n1, _, _, _), s1 in zip(bodies, one):
            v = _vol(s1, vs)
            if v > 0.5:
                print(f"  {n1} / {vn}: {v:.1f} mm³")
                hits += 1
    print("  none" if not hits else "")
    allc = cq.Workplane(obj=cq.Compound.makeCompound([s.val() for s in one]))
    bb = allc.val().BoundingBox()
    import math
    r_max = max(math.hypot(v.X, v.Y) for v in allc.val().Vertices())
    print(f"== module 1 extent: x {bb.xmin:.0f}..{bb.xmax:.0f}, y {bb.ymin:.0f}..{bb.ymax:.0f}, "
          f"z {bb.zmin:.0f}..{bb.zmax:.0f}; furthest point {r_max:.0f} mm from the enclosure axis")


def export(kit: str):
    bodies = module_bodies(kit)
    a = cq.Assembly(name=f"v2_v7_module_{kit}")
    for n, c, s, _ in bodies:
        a.add(s, name=n, color=cq.Color(c))
    a.save(str(HERE / kit / "module_assembly.step"))
    full = cq.Assembly(name=f"v7_with_v2_modules_{kit}")
    for vn, vs in v7_parts():
        full.add(vs, name=vn, color=cq.Color("gray70"))
    for k in range(6):
        for n, c, s, _ in bodies:
            full.add(to_enclosure(s, k), name=f"module_{k + 1}_{n}", color=cq.Color(c))
    full.save(str(HERE / kit / "v7_assembly.step"))
    cq.exporters.export(full.toCompound(), str(HERE / kit / "v7_assembly.stl"), tolerance=0.1)
    print(f"wrote {kit}/module_assembly.step, {kit}/v7_assembly.step")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for k in args or ["iron"]:
        if "--check" in sys.argv:
            check(k)
        else:
            export(k)
