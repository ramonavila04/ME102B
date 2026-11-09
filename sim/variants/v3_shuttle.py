"""V3: reciprocating shuttle (scotch-yoke slide), CAD in cad/variants/v3_shuttle/build.py.

One crank revolution = one dispense stroke: the pocket starts under the hopper throat
(theta = -90 deg, x = -R), carries one pill under the cover plate to the drop hole
(theta = +90 deg, x = +R) and returns. The firmware indexes one more revolution if the
chute sensor saw nothing (max_steps).
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad" / "variants" / "v3_shuttle"
PILL_IDS = ("iron", "small", "caplet", "cap0")


def _build_mod():
    spec = importlib.util.spec_from_file_location("v3_build", CAD / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ensure_built():
    """Rebuild every pill's CAD if build.py is newer than any manifest (lock: parallel workers)."""
    src = (CAD / "build.py").stat().st_mtime
    stale = [p for p in PILL_IDS
             if not (CAD / p / "manifest.json").exists() or (CAD / p / "manifest.json").stat().st_mtime < src]
    if not stale:
        return
    with open(CAD / ".build.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        mod = _build_mod()
        for p in PILL_IDS:
            m = CAD / p / "manifest.json"
            if not m.exists() or m.stat().st_mtime < src:
                mod.build(p)


def _manifest(pill_id: str) -> dict:
    _ensure_built()
    return json.loads((CAD / pill_id / "manifest.json").read_text())


def spec(pill_id: str) -> dict:
    man = _manifest(pill_id)
    P = man["params"]
    d = CAD / pill_id
    R = P["crank_r"]
    D = P["depth"]
    zfb = P["z_floor_bot"]
    gap = P["gap"]
    xc = (P["throat_x0"] + P["throat_x1"]) / 2
    wt = P["throat_x1"] - P["throat_x0"]
    lt = P["throat_y"]
    ax, ay = math.radians(P["wall_angle_x"]), math.radians(P["wall_angle_y"])
    z_top = gap + P["hopper_h"]
    z_ext = z_top + P["hopper_ext"]

    x0t = P["throat_x0"]
    yin = P["slide_w"] / 2 + gap
    # Crops are tiled: the decomposer accepts a hull whose added volume / hull area < tol,
    # which lets one hull of a large plate swallow a hole in it (the drop hole vanished when
    # the floor was a single crop). Tiles no wider than ~TILE mm keep every hole open.
    TILE = 6.0

    def tiles(name, stl, lo, hi, tol, body="static", tile=TILE, **kw):
        nx = max(1, math.ceil((hi[0] - lo[0]) / tile))
        ny = max(1, math.ceil((hi[1] - lo[1]) / tile))
        xs = [lo[0] + (hi[0] - lo[0]) * k / nx for k in range(nx + 1)]
        ys = [lo[1] + (hi[1] - lo[1]) * k / ny for k in range(ny + 1)]
        return [dict(name=f"{name}_{i * ny + j}", stl=stl, body=body, tol=tol,
                     crop=((xs[i], ys[j], lo[2]), (xs[i + 1], ys[j + 1], hi[2])), **kw)
                for i in range(nx) for j in range(ny)]

    x0t = P["throat_x0"]
    yin = P["slide_w"] / 2 + gap
    y_pp = P["seat_y"] / 2 + P["drop_e"] + P["chute_e"] + P["hopper_wall"] + 4   # pill-path half width
    hx_ch = P["seat_x"] / 2 + P["drop_e"] + P["chute_e"] + P["hopper_wall"] + 1
    parts = (
        # the cover plate / throat edges are where pills are stripped: exact (0.05 mm) hulls
        tiles("hopper", d / "hopper.stl", (x0t - 30, -yin - 8, 0), (P["base_x1"] + 1, yin + 8, 8), 0.05,
              tile=12.0)
        + [dict(name="hopper_upper", stl=d / "hopper.stl", body="static", tol=0.25,
                crop=((x0t - 60, -60, 8), (P["base_x1"] + 1, 60, z_ext + 1)))]
        + tiles("guide_base", d / "guide_base.stl", (x0t - 3, -y_pp, zfb - 1),
                (R + P["seat_x"] / 2 + 6, y_pp, -D + 0.05), 0.05)
        + tiles("chute", d / "chute.stl", (R - hx_ch - 6, -y_pp, zfb - 40), (R + hx_ch + 6, y_pp, zfb + 0.1), 0.1)
        + tiles("slide", d / "slide.stl", (-P["seat_x"] / 2 - P["ramp_len"] - 3, -y_pp, -D - 1),
                (P["seat_x"] / 2 + 3, y_pp, 1), 0.05, body="rotor", rgba="0.95 0.75 0.2 1")
        + tiles("slide_far", d / "slide.stl", (min(x0t - R - 4, P["x_crank"] + 6), -yin, -D - 1),
                (-P["seat_x"] / 2 - P["ramp_len"] - 3, yin, 1), 0.05, body="rotor", rgba="0.95 0.75 0.2 1",
                tile=40.0)
    )

    def half_widths(z):
        h = min(max(z - gap, 0.0), P["hopper_h"])
        return wt / 2 + h / math.tan(ax), lt / 2 + h / math.tan(ay)

    def accept(x, y, z, r):
        hx, hy = half_widths(z)
        if z < z_top:   # sloped walls: keep the centre r away from the wall plane
            hx -= r / math.sin(ax); hy -= r / math.sin(ay)
        else:
            hx -= r; hy -= r
        return abs(x - xc) <= hx and abs(y) <= hy and z > gap + r + 1.0

    hx_top, hy_top = half_widths(z_top)
    long_pill = pill_id in ("caplet", "cap0")
    fills = {"iron": (3, 20), "small": (3, 30), "caplet": (3, 12), "cap0": (3, 12)}

    def site_namer(part: str, pos):
        x, y, z = pos
        part = part.rsplit("_", 1)[0] if part.rsplit("_", 1)[-1].isdigit() else part
        if part.startswith("hopper"):
            if z < 6:
                return "throat exit edge (stripper)" if x > xc else "throat entry edge"
            return "hopper wall"
        if part == "guide_base":
            return "floor: drop-hole edge" if x > 0 else "floor under pocket"
        if part == "chute":
            return "chute"
        return part

    ex_hx = P["seat_x"] / 2 + P["drop_e"] + P["chute_e"]
    ex_hy = P["seat_y"] / 2 + P["drop_e"] + P["chute_e"]
    return dict(
        name="V3 shuttle (scotch-yoke slide)",
        parts=parts,
        joint=dict(type="slide", axis=(1, 0, 0), crank_r=R),
        rotor_mass_kg=P["slide_mass_g"] / 1000,
        drive=dict(index_deg=360.0, rpm=30.0, dir=1, accel_s=0.15, settle_s=0.6,
                   start_deg=-90.0, max_steps=6),
        spawn=dict(x=(xc - hx_top, xc + hx_top), y=(-hy_top, hy_top),
                   z=(gap + 3, 150.0), accept=accept),
        fill=fills[pill_id],
        exit=dict(z=zfb - 12.0, x=(R - ex_hx, R + ex_hx), y=(-ex_hy, ex_hy)),
        loss_z=zfb - 2.0,
        fill_s=2.2, settle_s=0.6,
        site_namer=site_namer,
    )
