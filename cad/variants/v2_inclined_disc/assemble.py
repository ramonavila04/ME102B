#!/usr/bin/env python3
"""Combine a kit's parts into one assembly file for viewing in CAD.

    python cad/variants/v2_inclined_disc/assemble.py iron

Writes <kit>/assembly.step (named, coloured bodies) and <kit>/assembly.stl. Printed parts
are placed as assembled. The bought drive parts (shaft, bearings, coupler, gearmotor) are
included as plain reference solids; screws and electronics are not modelled.
"""
import importlib.util
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v2_build", HERE / "build.py")
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)

PRINTED = [("disc", "orange"), ("backplate", "gray20"), ("hopper", "lightblue"),
           ("cover", "lightblue"), ("side_left", "gray"), ("side_right", "gray"),
           ("base", "gray"), ("cup", "white")]


def cyl(r, z0, z1, r_in=0.0):
    w = cq.Workplane("XY").workplane(offset=z0).circle(r)
    if r_in:
        w = w.circle(r_in)
    return w.extrude(z1 - z0)


def drive_bodies(kit):
    """(name, colour, solid in the local disc frame) for the drive line."""
    pp = b.pocket_params(kit)
    _, zf = b.backplate_z(pp)
    L = b.drive_layout(zf)
    gw, gh = b.GEARBOX
    brg_front = zf - b.BRG_RECESS
    out = [
        ("shaft_quarter_inch", "gray80", cyl(b.DRIVE_D / 2, L["shaft_rear"], L["shaft_front"])),
        ("bearing_front_R4ZZ", "blue", cyl(b.BRG_OD / 2, brg_front - b.BRG_W, brg_front, 4.7)),
        ("bearing_rear_R4ZZ", "blue", cyl(b.BRG_OD / 2, L["tube_rear"], L["tube_rear"] + b.BRG_W, 4.7)),
        ("spacer", "orange", b.make_spacer().translate((0, 0, brg_front))),
        ("collar", "orange", b.make_collar().rotate((0, 0, 0), (1, 0, 0), 180)
         .translate((0, 0, L["tube_rear"] - b.COLLAR_BOSS))),
        ("coupler_flexible", "red", cyl(b.COUPLER[0] / 2, L["coupler_rear"], L["coupler_front"], 1.5)),
        ("gearmotor", "gold",
         cq.Workplane("XY").workplane(offset=L["motor_rear"]).rect(gw, gh)
         .extrude(L["gearbox_front"] - L["motor_rear"])
         .union(cyl(b.SHAFT_D / 2, L["gearbox_front"], L["gearbox_front"] + b.MOTOR_SHAFT))),
        ("clamp", "gray20", b.make_clamp().rotate((0, 0, 0), (1, 0, 0), 90)
         .translate((0, -gh / 2 - b.RUN + 0.2, (L["socket_rear"] + L["gearbox_front"]) / 2))),
    ]
    return [(n, c, b._rot_world(s)) for n, c, s in out]


def bodies(kit):
    out = []
    for name, colour in PRINTED:
        f = HERE / kit / f"{name}.step"
        if not f.exists():
            f = HERE / "common" / f"{name}.step"
        out.append((name, colour, cq.importers.importStep(str(f))))
    return out + drive_bodies(kit)


def main(kit):
    assy = cq.Assembly(name=f"v2_inclined_disc_{kit}")
    for name, colour, shape in bodies(kit):
        assy.add(shape, name=name, color=cq.Color(colour))
    assy.save(str(HERE / kit / "assembly.step"))
    cq.exporters.export(assy.toCompound(), str(HERE / kit / "assembly.stl"), tolerance=0.05)
    bb = assy.toCompound().BoundingBox()
    print(f"{kit}: {bb.xlen:.0f} x {bb.ylen:.0f} x {bb.zlen:.0f} mm")


if __name__ == "__main__":
    for k in sys.argv[1:] or ["iron", "small"]:
        main(k)
