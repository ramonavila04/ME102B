#!/usr/bin/env python3
"""Combine a kit's parts into one assembly file for viewing in CAD.

    python cad/variants/v2_inclined_disc/assemble.py iron

The part STEP files are already saved in their assembled position, so this only groups
them. Writes <kit>/assembly.step (named, coloured parts) and <kit>/assembly.stl.
The motor, fasteners and electronics are not modelled.
"""
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
PARTS = [("disc", "orange"), ("backplate", "gray20"), ("hopper", "lightblue"),
         ("cover", "lightblue"), ("clamp", "gray20"), ("side_left", "gray"),
         ("side_right", "gray"), ("base", "gray"), ("cup", "white")]


def main(kit):
    assy = cq.Assembly(name=f"v2_inclined_disc_{kit}")
    for name, colour in PARTS:
        f = HERE / kit / f"{name}.step"
        if not f.exists():
            f = HERE / "common" / f"{name}.step"
        assy.add(cq.importers.importStep(str(f)), name=name, color=cq.Color(colour))
    assy.save(str(HERE / kit / "assembly.step"))
    cq.exporters.export(assy.toCompound(), str(HERE / kit / "assembly.stl"), tolerance=0.05)
    bb = assy.toCompound().BoundingBox()
    print(f"{kit}: {bb.xlen:.0f} x {bb.ylen:.0f} x {bb.zlen:.0f} mm")


if __name__ == "__main__":
    for k in sys.argv[1:] or ["iron", "small"]:
        main(k)
