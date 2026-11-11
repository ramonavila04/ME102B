"""V2: inclined pocket disc (rim-notch singulator). Geometry from cad/variants/v2_inclined_disc."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad" / "variants" / "v2_inclined_disc"

_spec = importlib.util.spec_from_file_location("v2_build", CAD / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

B = math.radians(build.BETA)
CB, SB = math.cos(B), math.sin(B)


# Disc speed while indexing. Iron runs slow: a tablet lying flat needs ~0.06 s to tip into
# the standing slot, and at 25 rpm the slot is fully under it for only ~0.03 s (rev 16).
RPM = {"iron": 6.0}


def to_local(x, y, z):
    """World → disc frame (inverse of rotation about x by BETA)."""
    return x, CB * y + SB * z, -SB * y + CB * z


def to_world(x, y, z):
    return x, CB * y - SB * z, SB * y + CB * z


def _ensure(pill_id: str) -> dict:
    man = CAD / pill_id / "manifest.json"
    if not man.exists() or not (CAD / "common" / "manifest.json").exists():
        build.build(pill_id)
        build.build_common()
    return json.loads(man.read_text())


def site_namer(part: str, pos):
    xl, yl, zl = to_local(*pos)
    ang = math.degrees(math.atan2(yl, xl)) % 360
    if part.startswith("backplate"):
        return f"exit hole / back plate (pill at {ang:.0f}°)"
    if part.startswith("hopper"):
        return f"hopper wall (pill at {ang:.0f}°)"
    if part.startswith("cover"):
        return "cover"
    return part


def spec(pill_id: str) -> dict:
    man = _ensure(pill_id)
    pp = man["params"]
    d = CAD / pill_id
    c = CAD / "common"
    zb, _ = build.backplate_z(pp)
    parts = [
        dict(name="disc", stl=d / "disc.stl", body="rotor", tol=0.05, rgba="0.95 0.75 0.2 1"),
        dict(name="backplate", stl=d / "backplate.stl", body="static", tol=0.1),
        dict(name="hopper", stl=d / "hopper.stl", body="static", tol=0.1),
        dict(name="cover", stl=c / "cover.stl", body="static", tol=0.2),
    ]
    r_in, L = pp["r_inner"], pp["length"]
    ang0 = math.radians(build.EXIT_ANGLE)

    def exit_fn(x, y, z):
        xl, yl, zl = to_local(x, y, z)
        # rotate into the exit-notch frame (notch axis along +x)
        u = math.cos(ang0) * xl + math.sin(ang0) * yl
        v = -math.sin(ang0) * xl + math.cos(ang0) * yl
        inside = (r_in - 4 <= u <= build.R_WALL + 3) and abs(v) <= L / 2 + 4
        # counted only once the pill has slid out of the end of the duct
        return inside, zl < zb - build.DUCT_LEN - 2.0

    from sim.pills import PILLS
    pill_r = PILLS[pill_id].bounding_radius

    H = build.HOPPER_TOP                           # the pour opening (lower half) is at this height

    def accept(x, y, z, r):
        """Inside the lower half of the hopper, or above the fill opening so that the
        pill's vertical drop passes through the open lower half (where the user pours)."""
        xl, yl, zl = to_local(x, y, z)
        if zl <= H - r - 1.0:
            r_lim = build.bore_r(math.atan2(yl, xl), zl + r)   # leaning pool-side wall
            if pp.get("pocket") == "standing slot":            # keep clear of the disc cone
                cone_z = build.CONE_H if math.hypot(xl, yl) < pp["r_inner"] + r + 1 else 0.0
                if zl < cone_z + r + 1.0:
                    return False
            return (math.hypot(xl, yl) < r_lim - r - 0.5 and yl < -2 - r * 0.5 and zl > r + 1.0)
        s = (zl - H) / CB                       # world-vertical drop to the opening plane
        yp = yl - s * SB
        return math.hypot(xl, yp) < build.bore_r(math.atan2(yp, xl), H) - r - 1.0 and yp < build.COVER_Y - 3 - r

    corners = [to_world(xx, yy, zz) for xx in (-31, 31) for yy in (-31, 0) for zz in (0, H)]
    xs, ys, zs = zip(*corners)
    zs = list(zs) + [max(zs) + 450]
    # shrink the sampling box to the region accept() actually allows (the pour column is a
    # thin tilted crescent; a loose box wastes the engine's placement attempts)
    import numpy as _np
    _rng = _np.random.default_rng(12345)
    _pts = _np.c_[_rng.uniform(min(xs), max(xs), 60000), _rng.uniform(min(ys), max(ys), 60000),
                  _rng.uniform(min(zs), max(zs), 60000)]
    _ok = _np.array([accept(px, py, pz, pill_r) for px, py, pz in _pts])
    _a = _pts[_ok]
    xs, ys = (_a[:, 0].min() - 1, _a[:, 0].max() + 1), (_a[:, 1].min() - 1, _a[:, 1].max() + 1)
    fills = {"iron": (3, 20), "small": (3, 30), "caplet": (3, 12), "cap0": (3, 12)}
    return dict(
        name="V2 inclined pocket disc",
        parts=parts,
        joint=dict(type="hinge", axis=(0.0, -SB, CB), pos=(0, 0, 0)),
        rotor_mass_kg=0.015,
        drive=dict(index_deg=pp["pitch_deg"], rpm=RPM.get(pill_id, 25.0), dir=1, accel_s=0.12, settle_s=0.6,
                   start_deg=0.0, max_steps=2 * pp["n"]),   # up to two revolutions per dispense
        spawn=dict(x=(min(xs), max(xs)), y=(min(ys), max(ys)), z=(min(zs), max(zs)), accept=accept),
        fill=fills[pill_id],
        exit=dict(fn=exit_fn),
        loss_z=-45.0,
        fill_s=3.8, settle_s=0.6,
        site_namer=site_namer,
    )
