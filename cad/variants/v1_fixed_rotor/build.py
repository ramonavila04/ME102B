#!/usr/bin/env python3
"""V1: minimal fix of the team's indexed-rotor dispenser (CadQuery, parametric).

    python cad/variants/v1_fixed_rotor/build.py [iron small caplet cap0]

Same architecture as the team's design: a vertical-axis rotor under a Ø67.5 mm
canister, a fixed deck with a fill opening, a drop hole over a chute and the
1000:1 micro gearmotor underneath. What changes (see DESIGN.md):

* one pill-specific pocket ring per pill type (pocket = pill + tolerance +
  clearance per side, depth so one seated pill sits just below the rotor top);
* the rotor slides on the floor with 0.4 mm clearance and the deck sits 0.4 mm
  above it: no 2.35 mm step and no 0.35 mm FDM-hostile gap;
* the fill opening lies entirely inside the rotor disc (no path past the rim);
* the stripping edge is a vertical face (no converging wedge), set oblique to
  the pocket motion so protruding pills are ploughed back toward the hub;
* a cone plus a ridge baffle in the hopper feed pills onto the pocket track;
* the brush is removed.

Coordinates: mm, +z up, rotor axis = z, rotor top face at z = 0, drop hole on +x.
Every part is exported in assembled position. Per pill: rotor, floor, deck
(pill-specific kit). Common: lower_enclosure, canister (exported per pill folder
too, because the checker wants all mating parts in one manifest).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cadquery as cq
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sim.pills import PILLS  # noqa: E402

HERE = Path(__file__).resolve().parent
PLA_DENSITY = 1.24e-3  # g/mm^3

# ------------------------------------------------------------------ parameters
COMMON = dict(
    od=67.5,                 # module outer diameter (team footprint)
    rotor_r=26.0,            # same rotor diameter as the team's (Ø52)
    run_gap=0.4,             # rotor-floor, rotor-deck and rotor-rim running clearance
    fdm_clear=0.35,          # pocket clearance per side beyond the largest pill
    seat_margin=0.25,        # thickest pill's top sits this far below the rotor top
    track_r=15.0,            # pocket pitch radius (same for all pills -> common chute)
    r_open=22.0,             # fill opening outer radius (inside the Ø52 rotor)
    edge_face=2.0,           # vertical stripping-face height above the deck underside
    cone_deg=50.0,           # hopper cone slope (above the 31° friction angle of mu=0.6)
    baffle_deg=50.0,         # ridge-baffle slope over the covered sector
    edge_oblique_deg=25.0,   # stripping edge tilt from radial (outer end upstream)
    deck_bore_r=31.1,        # hopper bore (canister ID) at the cone top
    floor_bottom=-12.0,      # floor-part underside (common for every pill kit)
    boss_r=5.0,              # rotor hub boss radius (D-bore for the 3 mm D shaft)
    hole_margin=1.0,         # drop hole = pocket outline + this per side
    chute_wall=1.6,
    encl_bottom=-64.0,
    canister_h=60.0,
    screw_r=30.0,            # 3x M2 screw circle
    screw_angles=(60.0, 180.0, 300.0),
)

# Pockets per revolution: as many as fit with >= 4.5 mm webs.
POCKETS = {"iron": 6, "small": 8, "caplet": 3, "cap0": 3}


def params_for(pill_id: str, **over) -> dict:
    p = dict(COMMON)
    p.update(over)
    pill = PILLS[pill_id]
    c = p["fdm_clear"]
    if pill.kind == "tablet":
        dmax = pill.length + pill.tol
        L = W = dmax + 2 * c
        tmax = pill.thickness + pill.tol
    elif pill.kind == "capsule":
        L = pill.length + pill.tol_length + 2 * c
        W = pill.width + pill.tol + 2 * c
        tmax = pill.width + pill.tol
    else:
        L = pill.length + pill.tol_length + 2 * c
        W = pill.width + pill.tol + 2 * c
        tmax = pill.thickness + pill.tol
    T = tmax - p["run_gap"] + p["seat_margin"]          # rotor (= pocket) thickness
    n = over.get("pockets", POCKETS[pill_id])
    p.update(pill=pill_id, kind=pill.kind, pocket_L=round(L, 3), pocket_W=round(W, 3),
             rotor_t=round(T, 3), pockets=n, pitch_deg=360.0 / n, pill_tmax=tmax)
    p["floor_top"] = -T - p["run_gap"]
    p["deck_z0"] = p["run_gap"]
    p["deck_z1"] = p["run_gap"] + p["edge_face"]
    p["wall_top"] = p["deck_z1"] + (p["deck_bore_r"] - p["r_open"]) * math.tan(math.radians(p["cone_deg"]))
    _edges(p)
    return p


# ------------------------------------------------------------- 2-D geometry
def _rot(v, deg):
    a = math.radians(deg)
    return np.array([v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)])


def pocket_outline(p, theta_deg, grow=0.0, n=48):
    """Points on the outline of the pocket centred at angle theta (long axis tangential)."""
    L, W = p["pocket_L"] + 2 * grow, p["pocket_W"] + 2 * grow
    a = (L - W) / 2
    pts = []
    for t in np.linspace(0, 2 * np.pi, n, endpoint=False):
        # local frame: u = radial, v = tangential
        u, v = W / 2 * math.cos(t), W / 2 * math.sin(t)
        v += math.copysign(a, v) if a > 0 else 0.0
        pts.append((p["track_r"] + u, v))
    return np.array([_rot(q, theta_deg) for q in pts])


def _edges(p):
    """Stripping edge E1 (oblique) and re-entry edge E2 meeting at apex A near the hub.

    Covered sector = {s1 <= 0 and s2 <= 0}, s_i = n_i . (x - Q_i), n_i pointing into the
    fill side. Pockets rest at k*pitch (k = 0 over the drop hole); the rotor turns CCW.
    """
    R, pitch = p["track_r"], p["pitch_deg"]
    th1 = math.radians(360 - pitch / 2)
    r1 = np.array([math.cos(th1), math.sin(th1)]); t1 = np.array([-math.sin(th1), math.cos(th1)])
    q1 = R * r1
    margin = 0.6
    fill_pk, drop_pk, next_pk = (pocket_outline(p, -pitch), pocket_outline(p, 0.0),
                                 pocket_outline(p, pitch))
    gam = p["edge_oblique_deg"]
    while True:
        g = math.radians(gam)
        n1 = -math.cos(g) * t1 - math.sin(g) * r1          # upstream + inward
        s_fill = (fill_pk - q1) @ n1
        s_drop = (drop_pk - q1) @ n1
        if (s_fill.min() >= margin and s_drop.max() <= -margin) or gam <= 0:
            break
        gam -= 0.5
    d1 = np.array([n1[1], -n1[0]])                        # along the edge
    A = q1 - (q1 @ d1) * d1                               # foot of the perpendicular from the hub
    th2 = math.radians(pitch / 2)
    q2 = R * np.array([math.cos(th2), math.sin(th2)])
    d2 = (q2 - A) / np.linalg.norm(q2 - A)
    n2 = np.array([-d2[1], d2[0]])
    if (next_pk - A) @ n2 @ np.ones(len(next_pk)) < 0:
        n2 = -n2
    s2_next = (next_pk - A) @ n2
    s2_drop = (drop_pk - A) @ n2
    assert s2_next.min() >= margin and s2_drop.max() <= -margin, "re-entry edge cuts a pocket"
    p.update(edge_gamma_deg=gam, apex=A.round(4).tolist(), e1_q=q1.round(4).tolist(),
             e1_n=n1.round(6).tolist(), e2_q=A.round(4).tolist(), e2_n=n2.round(6).tolist())


def covered(p, x, y):
    """True where the deck covers the rotor (outside the fill opening)."""
    if math.hypot(x, y) > p["r_open"]:
        return True
    s1 = (x - p["e1_q"][0]) * p["e1_n"][0] + (y - p["e1_q"][1]) * p["e1_n"][1]
    s2 = (x - p["e2_q"][0]) * p["e2_n"][0] + (y - p["e2_q"][1]) * p["e2_n"][1]
    return s1 <= 0 and s2 <= 0


# --------------------------------------------------------------------- solids
def _cyl(r, z0, z1, x=0.0, y=0.0):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def _pocket_prism(p, theta_deg, z0, z1, grow=0.0):
    L, W = p["pocket_L"] + 2 * grow, p["pocket_W"] + 2 * grow
    c = _rot((p["track_r"], 0.0), theta_deg)
    wp = cq.Workplane("XY").workplane(offset=z0).center(float(c[0]), float(c[1]))
    if abs(L - W) < 1e-6:
        sk = wp.circle(W / 2)
    else:
        sk = wp.slot2D(L, W, theta_deg + 90.0)
    return sk.extrude(z1 - z0)


def _halfspace_below(origin, xdir, normal, size=400.0):
    """Solid on the -normal side of the plane through origin."""
    pl = cq.Plane(origin=tuple(map(float, origin)), xDir=tuple(map(float, xdir)),
                  normal=tuple(map(float, normal)))
    return cq.Workplane(pl).rect(size, size).extrude(-size / 2)


def rotor(p):
    T = p["rotor_t"]
    body = _cyl(p["rotor_r"], -T, 0.0)
    boss = _cyl(p["boss_r"], p["floor_bottom"] - 1.0, -T + 0.01)
    body = body.union(boss)
    for k in range(p["pockets"]):
        body = body.cut(_pocket_prism(p, k * p["pitch_deg"], -T - 1, 1))
    # D-bore for the 3 mm D shaft (flat at 1.0 mm from the axis), +0.05 mm fit
    zb0, zb1 = p["floor_bottom"] - 1.5, -3.0
    bore = _cyl(1.525, zb0, zb1).cut(
        cq.Workplane("XY").workplane(offset=zb0 - 1).center(1.05 + 2, 0).rect(4, 4).extrude(zb1 - zb0 + 2))
    return body.cut(bore)


def floor_part(p):
    """Floor the rotor slides on, drop hole, hub hole, and the spacer ring that carries the deck."""
    zf, zb = p["floor_top"], p["floor_bottom"]
    body = _cyl(p["od"] / 2, zb, zf)
    ring = _cyl(p["od"] / 2, zf - 0.01, p["deck_z0"]).cut(_cyl(p["rotor_r"] + p["run_gap"], zf - 1, p["deck_z0"] + 1))
    body = body.union(ring)
    body = body.cut(_pocket_prism(p, 0.0, zb - 1, zf + 1, grow=p["hole_margin"]))
    body = body.cut(_cyl(p["boss_r"] + p["run_gap"], zb - 1, zf + 1))
    for a in p["screw_angles"]:
        x, y = _rot((p["screw_r"], 0), a)
        body = body.cut(_cyl(1.2, zb - 1, p["deck_z0"] + 1, x, y))
    return body


def deck(p):
    """Deck plate 0.4 mm above the rotor, vertical oblique stripping edge, cone and ridge baffle."""
    z0, z1, zt = p["deck_z0"], p["deck_z1"], p["wall_top"]
    R_out = p["od"] / 2
    # plate ring outside the opening + cone
    prof = (cq.Workplane("XZ").moveTo(p["r_open"], z0).lineTo(R_out, z0).lineTo(R_out, zt)
            .lineTo(p["deck_bore_r"], zt).lineTo(p["r_open"], z1).close())
    body = prof.revolve(360, (0, 0, 0), (0, 1, 0))
    # covered wedge: plate (z0..z1) + roof rising from both edges at baffle_deg
    tb = math.tan(math.radians(p["baffle_deg"]))
    wedge = _cyl(p["deck_bore_r"] + 0.5, z0, zt)
    for q, n in ((p["e1_q"], p["e1_n"]), (p["e2_q"], p["e2_n"])):
        n = np.array(n)
        xdir = (n[1], -n[0], 0.0)
        # fill side removed: halfspace s <= 0  <=> below plane with normal (n, 0)
        wedge = wedge.intersect(_halfspace_below((q[0], q[1], 0.0), xdir, (n[0], n[1], 0.0)))
        nrm = np.array([tb * n[0], tb * n[1], 1.0])
        wedge = wedge.intersect(_halfspace_below((q[0], q[1], z1), xdir, nrm))
    body = body.union(wedge)
    # locating lip for the canister
    body = body.union(_cyl(R_out, zt - 0.01, zt + 3.0).cut(_cyl(32.5, zt - 1, zt + 4)))
    # 3x M2 clamp screws (head counterbore from the funnel surface)
    for a in p["screw_angles"]:
        x, y = _rot((p["screw_r"], 0), a)
        body = body.cut(_cyl(1.2, z0 - 1, zt + 1, x, y)).cut(_cyl(2.1, z1 + 2.0, zt + 5, x, y))
    return body


def lower_enclosure(p):
    """Cup under the floor: chute to the cup below, motor post, screw bosses (common part)."""
    zb, zt = p["encl_bottom"], p["floor_bottom"]
    R = p["od"] / 2
    body = _cyl(R, zb, zt).cut(_cyl(R - 2.45, zb + 2.0, zt + 1))
    # chute sized for the largest pocket kit (cap0): hole outline + 0.5 mm
    ci = chute_inner(p)
    w = p["chute_wall"]
    outer = cq.Workplane("XY").workplane(offset=zb).center(ci["cx"], 0).rect(ci["hx"] * 2 + 2 * w, ci["hy"] * 2 + 2 * w).extrude(zt - zb)
    inner = cq.Workplane("XY").workplane(offset=zb - 1).center(ci["cx"], 0).rect(ci["hx"] * 2, ci["hy"] * 2).extrude(zt - zb + 2)
    body = body.union(outer).cut(inner)
    # motor post (Pololu micro-gearmotor bracket #989, 2x M2 into the post face at x = -6.5)
    post = cq.Workplane("XY").workplane(offset=zb + 1).center(-9.5, 0).rect(6.0, 26.0).extrude(-20 - zb - 1)
    body = body.union(post)
    for yy in (-9.0, 9.0):
        # teardrop (55° roof) so the horizontal pilot hole prints without support
        hole = (cq.Workplane("YZ").workplane(offset=-14).center(yy, -27.0)
                .polyline([(-0.8, -0.8), (0.8, -0.8), (0.8, 0.2), (0.0, 0.2 + 0.8 * math.tan(math.radians(55))),
                           (-0.8, 0.2)]).close().extrude(9))
        body = body.cut(hole)
    # wire exit
    body = body.cut(_cyl(2.5, zb - 1, zb + 3, -12, 21))
    for a in p["screw_angles"]:
        x, y = _rot((p["screw_r"], 0), a)
        body = body.union(_cyl(2.4, zb + 1, zt, x, y)).cut(_cyl(0.85, zt - 10, zt + 1, x, y))
    return body


def chute_inner(p):
    big = params_for("cap0", **{k: p[k] for k in COMMON})
    hx = big["pocket_W"] / 2 + big["hole_margin"] + 0.5
    hy = big["pocket_L"] / 2 + big["hole_margin"] + 0.5
    return dict(cx=p["track_r"], hx=round(hx, 3), hy=round(hy, 3))


def canister(p):
    z0 = p["wall_top"]
    R = p["od"] / 2
    body = _cyl(R, z0 + 3.0, z0 + p["canister_h"]).union(_cyl(32.2, z0, z0 + 3.01))
    return body.cut(_cyl(p["deck_bore_r"] - 0.15, z0 - 1, z0 + p["canister_h"] + 1))


PARTS = [  # name, builder, print rotation (deg), what it is
    ("rotor", rotor, [180, 0, 0]),
    ("floor", floor_part, [0, 0, 0]),
    ("deck", deck, [0, 0, 0]),
    ("lower_enclosure", lower_enclosure, [0, 0, 0]),
    ("canister", canister, [180, 0, 0]),
]


def build(pill_id: str, **over) -> dict:
    p = params_for(pill_id, **over)
    out = HERE / pill_id
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    vols = {}
    for name, fn, rot in PARTS:
        wp = fn(p)
        shape = wp.val() if len(wp.vals()) == 1 else wp.combine().val()
        vols[name] = shape.Volume()
        cq.exporters.export(wp, str(out / f"{name}.step"))
        cq.exporters.export(wp, str(out / f"{name}.stl"), tolerance=0.02, angularTolerance=0.1)
        parts.append(dict(name=name, stl=f"{name}.stl", step=f"{name}.step", print_rotation=rot))
    p["rotor_mass_g"] = round(vols["rotor"] * PLA_DENSITY, 2)
    p["chute"] = chute_inner(p)
    man = dict(
        variant="v1_fixed_rotor", pill=pill_id, parts=parts,
        clearances=[
            dict(a="rotor", b="floor", min=0.3, what="rotor on floor / rim in spacer ring / hub in floor hole (0.4 modelled)"),
            dict(a="rotor", b="deck", min=0.3, what="deck underside over rotor top (0.4 modelled)"),
            dict(a="rotor", b="lower_enclosure", min=0.3, what="hub boss vs chute, post and screw bosses"),
        ],
        params={k: v for k, v in p.items() if not callable(v)},
    )
    (out / "manifest.json").write_text(json.dumps(man, indent=1, default=float))
    return man


if __name__ == "__main__":
    for pid in (sys.argv[1:] or list(PILLS)):
        m = build(pid)
        pr = m["params"]
        print(f"{pid}: pocket {pr['pocket_L']}x{pr['pocket_W']} depth {pr['rotor_t']} "
              f"N={pr['pockets']} edge gamma {pr['edge_gamma_deg']} deg, rotor {pr['rotor_mass_g']} g")
