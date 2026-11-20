#!/usr/bin/env python3
"""Tipping check for the V8 housing with six V2 modules.

    python cad/variants/v8_housing/tipping.py

Masses (estimates, listed so they can be replaced by weighed values):
  printed parts    volume × 1.24 g/cm³ × FILL (FILL = 0.6: walls plus 25-40 % infill)
  per module       gearmotor 10.5 g, 1/4" steel shaft 57 mm 14 g, 2 × R4 bearing 4 g each,
                   flexible coupler 6 g
  electronics      300 g on the floor (breadboards, boards, wiring), centred
  pills            a full hopper: HOPPER_FILL_G of tablets at the hopper's centroid
The base touches the table along the lower body's bottom outline (z −159.5).
Reports the centre of mass and, for a sideways push at the top of a hopper and a downward
push on a hopper's outer rim, the force that starts tipping.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assemble as A  # noqa: E402
import layout as Ly  # noqa: E402

FILL = 0.6
RHO = 1.24e-3            # g/mm³
G = 9.81e-3              # N per g
BOUGHT = [("gearmotor", 10.5), ("shaft_quarter_inch", 14.0), ("bearing_front_R4ZZ", 4.0),
          ("bearing_rear_R4ZZ", 4.0), ("coupler_flexible", 6.0)]
ELECTRONICS_G = 300.0
HOPPER_FILL_G = 60.0     # ~150 iron tablets at 0.4 g; the hopper holds more of the small ones


def main(kit="iron", full=(True,) * 6):
    B = A.bodies(kit)
    m_tot, mom = 0.0, np.zeros(3)
    hop = {}
    for n, g, t in B:
        bought = next((m for k, m in BOUGHT if k in n), None)
        if bought is not None:
            m = bought
            c = t.bounds.mean(0)
        else:
            if not t.is_watertight:
                t = t.convex_hull if t.volume <= 0 else t
            m = abs(t.volume) * RHO * FILL
            c = t.center_mass if t.is_watertight else t.bounds.mean(0)
        if n.endswith("_hopper"):
            hop[n[:2]] = (c, t.bounds)
        m_tot += m
        mom += m * np.asarray(c)
    for i, k in enumerate(sorted(hop)):
        if full[i]:
            m_tot += HOPPER_FILL_G
            mom += HOPPER_FILL_G * hop[k][0]
    m_tot += ELECTRONICS_G
    mom += ELECTRONICS_G * np.array([0, 0, -150.0])
    com = mom / m_tot
    W = m_tot * G
    # base outline: lower body's bottom section
    lower = [t for n, g, t in B if n == "v7_lower"][0]
    sec = lower.section(plane_origin=[0, 0, lower.bounds[0][2] + 0.5], plane_normal=[0, 0, 1])
    pts = np.vstack([e[:, :2] for e in sec.discrete])
    hull = trimesh.convex.convex_hull(np.c_[pts, np.zeros(len(pts))]) if False else None
    from scipy.spatial import ConvexHull
    h = ConvexHull(pts)
    poly = pts[h.vertices]
    z_floor = lower.bounds[0][2]
    print(f"total mass {m_tot:.0f} g ({W:.1f} N); centre of mass ({com[0]:.1f}, {com[1]:.1f}, {com[2]:.1f}) mm, "
          f"{com[2] - z_floor:.0f} mm above the table")
    # sideways push at each hopper top, horizontal, radially outward (worst direction for it)
    worst_side, worst_down = 1e9, 1e9
    for k in sorted(hop):
        c, bb = hop[k]
        allv = [t for n, g, t in B if n == f"{k}_hopper"][0].vertices
        r = np.hypot(allv[:, 0], allv[:, 1])
        far = allv[np.argmax(r)]
        top = allv[np.argmax(allv[:, 2])]
        d = far[:2] / np.linalg.norm(far[:2])          # outward direction at that hopper
        # tipping edge: support polygon's extreme point along d
        edge = poly[np.argmax(poly @ d)]
        lever_w = (edge - com[:2]) @ d                 # weight's restoring arm
        F_side = W * lever_w / (top[2] - z_floor)
        F_down = W * lever_w / max((far[:2] - edge) @ d, 1e-6)
        worst_side, worst_down = min(worst_side, F_side), min(worst_down, F_down)
        print(f"  module {k}: hopper rim {np.linalg.norm(far[:2]):.0f} mm out, top {top[2] - z_floor:.0f} mm up; "
              f"base edge {edge @ d:.0f} mm out; tips at {F_side:.1f} N sideways at the top or "
              f"{F_down:.1f} N pressing down on the outer rim")
    print(f"worst: {worst_side:.1f} N sideways at a hopper top, {worst_down:.1f} N down on a hopper rim")
    return worst_side, worst_down


if __name__ == "__main__":
    main()
