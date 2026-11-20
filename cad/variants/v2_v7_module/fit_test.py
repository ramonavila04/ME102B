#!/usr/bin/env python3
"""Fit-test coupon for the V7 module: print it once on the printer and filament that will
make the real parts, then pick the fits before printing six module sets.

    python cad/variants/v2_v7_module/fit_test.py      # writes fit_test/fit_coupon.{step,stl}

One flat bar, every hole vertical (no supports), each hole's size offset debossed beside it:

  row 1  R4-ZZ bearing pockets   Ø15.875 + 0.00 / 0.10 / 0.20 / 0.30   -> BRG_FIT (V2 build.py, now 0.10)
  row 2  M3 heat-set insert holes Ø3.9 / 4.0 / 4.1 / 4.2, 9 mm deep      -> INSERT_HOLE (now 4.0)
         1/4" shaft bores         Ø6.35 + 0.10 / 0.20 / 0.30             -> spacer and gear bores (now +0.20)
         motor D-shaft bores      Ø3.0 + 0.00 / 0.05 / 0.10, 2.5 flat   -> motor gear bore (now +0.10)

Bearing: should press in by thumb or with a vice and not fall out. Insert: should go in
square with the iron and leave no gap at the rim. Shaft: should slide through without play
you can feel. Motor shaft: light push fit (the gear also gets a drop of CA).
"""
from __future__ import annotations

import json
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
OUT = HERE / "fit_test"

BRG_OD, BRG_W = 15.875, 4.98
T = 9.0                    # coupon thickness (bearing pocket depth > bearing width, insert 6 mm + 3)
TEXT_H, TEXT_D = 3.0, 0.6


def coupon() -> cq.Workplane:
    w, d = 92.0, 46.0
    bar = cq.Workplane("XY").rect(w, d).extrude(T).edges("|Z").fillet(3.0)
    cuts, labels = [], []
    # row 1: bearing pockets, through
    for i, fit in enumerate((0.0, 0.10, 0.20, 0.30)):
        x = -33.0 + 22.0 * i
        cuts.append(cq.Workplane("XY").workplane(offset=-1).center(x, 8.0).circle((BRG_OD + fit) / 2).extrude(T + 2))
        labels.append((f"{fit:.1f}", x, -2.5))
    # row 2: inserts, shaft bores, motor bores
    row = [("ins", 3.9), ("ins", 4.0), ("ins", 4.1), ("ins", 4.2),
           ("sh", 0.10), ("sh", 0.20), ("sh", 0.30),
           ("mot", 0.0), ("mot", 0.05), ("mot", 0.10)]
    for i, (kind, v) in enumerate(row):
        x = -40.0 + 8.9 * i
        y = -10.5
        if kind == "ins":
            cuts.append(cq.Workplane("XY").workplane(offset=-1).center(x, y).circle(v / 2).extrude(T + 2))
            labels.append((f"{v:.1f}", x, y - 6.5))
        elif kind == "sh":
            cuts.append(cq.Workplane("XY").workplane(offset=-1).center(x, y).circle((6.35 + v) / 2).extrude(T + 2))
            labels.append((f"{v:.1f}"[-2:], x, y - 6.5))
        else:
            r = (3.0 + v) / 2
            bore = cq.Workplane("XY").workplane(offset=-1).center(x, y).circle(r).extrude(T + 2)
            flat = cq.Workplane("XY").workplane(offset=-1).center(x + 2.5 - 1.5 + v / 2 + 2, y).rect(4, 6).extrude(T + 2)
            cuts.append(bore.cut(flat))
            labels.append((f"{v:.2f}"[-2:], x, y - 6.5))
    for c in cuts:
        bar = bar.cut(c)
    for txt, x, y in labels:
        bar = bar.cut(cq.Workplane("XY").workplane(offset=T).center(x, y)
                      .text(txt, TEXT_H, -TEXT_D, combine=False, halign="center", valign="center"))
    # row-2 group marks: I(nsert), S(haft), M(otor)
    for txt, x in (("I", -40.0 + 8.9 * 1.5), ("S", -40.0 + 8.9 * 5), ("M", -40.0 + 8.9 * 8)):
        bar = bar.cut(cq.Workplane("XY").workplane(offset=T).center(x, -21.0)
                      .text(txt, TEXT_H, -TEXT_D, combine=False, halign="center", valign="center"))
    return bar


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    c = coupon()
    cq.exporters.export(c, str(OUT / "fit_coupon.step"))
    cq.exporters.export(c, str(OUT / "fit_coupon.stl"), tolerance=0.02, angularTolerance=0.08)
    man = dict(variant="v2_v7_module", pill="fit_test",
               parts=[dict(name="fit_coupon", stl="fit_coupon.stl", step="fit_coupon.step",
                           print_rotation=[0, 0, 0], bed="flat", max_overhang_mm2=4.0)], clearances=[])
    (OUT / "manifest.json").write_text(json.dumps(man, indent=2))


if __name__ == "__main__":
    build()
    print("wrote", OUT / "fit_coupon.stl")
