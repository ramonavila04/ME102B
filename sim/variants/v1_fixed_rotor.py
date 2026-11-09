"""V1: minimal fix of the team's indexed rotor (CAD: cad/variants/v1_fixed_rotor/build.py)."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad" / "variants" / "v1_fixed_rotor"


def _build_module():
    s = importlib.util.spec_from_file_location("v1_build", CAD / "build.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _manifest(pill_id: str) -> dict:
    mf = CAD / pill_id / "manifest.json"
    if not mf.exists():
        _build_module().build(pill_id)
    return json.loads(mf.read_text())


def spec(pill_id: str) -> dict:
    man = _manifest(pill_id)
    p = man["params"]
    d = CAD / pill_id
    stl = lambda n: str(d / f"{n}.stl")
    z_low = p["deck_z0"] + 3.6        # deck below this keeps the 0.05 mm hull tolerance
    parts = [
        dict(name="rotor", stl=stl("rotor"), body="rotor", rgba="0.95 0.75 0.2 1", crop=None, tol=0.05),
        dict(name="floor", stl=stl("floor"), body="static", crop=None, tol=0.05),
        dict(name="deck", stl=stl("deck"), body="static", crop=((-40, -40, -1), (40, 40, z_low)), tol=0.05),
        dict(name="deck_upper", stl=stl("deck"), body="static", crop=((-40, -40, z_low), (40, 40, 60)), tol=0.2),
        dict(name="canister", stl=stl("canister"), body="static", crop=None, tol=0.25),
        dict(name="chute", stl=stl("lower_enclosure"), body="static",
             crop=((-40, -40, -40), (40, 40, p["floor_bottom"] + 0.5)), tol=0.1),
    ]
    ch = p["chute"]
    big = pill_id in ("caplet", "cap0")
    z_spawn = p["wall_top"] + 1.0
    bore = p["deck_bore_r"] - 0.4

    def accept(x, y, z, r):
        return math.hypot(x, y) <= bore - r and z >= z_spawn + r

    e1q, e1n = p["e1_q"], p["e1_n"]

    def site_namer(part: str, pos_mm) -> str:
        x, y, z = pos_mm
        rad = math.hypot(x, y)
        if part.startswith("deck"):
            s1 = (x - e1q[0]) * e1n[0] + (y - e1q[1]) * e1n[1]
            if abs(s1) < 6 and rad < p["r_open"] + 2:
                return "deck stripping edge (fill -> covered)"
            if rad > p["r_open"] - 6:
                return "deck opening rim (outer)"
            return "deck re-entry edge / baffle"
        if part == "floor":
            if x > 5 and abs(y) < p["pocket_L"] / 2 + 3 and z < p["floor_top"] + 3:
                return "drop-hole edge"
            if rad > p["rotor_r"] - 1:
                return "spacer ring at rotor rim"
            return "floor under rotor"
        if part == "chute":
            return "chute"
        if part == "canister":
            return "canister wall"
        return part

    fills = {"iron": (3, 20), "small": (3, 30), "caplet": (3, 12), "cap0": (3, 12)}
    return dict(
        name="V1 fixed rotor",
        parts=parts,
        joint=dict(type="hinge", axis=(0, 0, 1), pos=(0, 0, 0)),
        rotor_mass_kg=p["rotor_mass_g"] / 1000,
        drive=dict(index_deg=p["pitch_deg"], rpm=p.get("rpm", 20.0), dir=1, accel_s=0.15,
                   settle_s=0.6, start_deg=0.0, max_steps=p["pockets"]),
        spawn=dict(x=(-bore, bore), y=(-bore, bore),
                   z=(z_spawn, z_spawn + (130 if big else 55)), accept=accept),
        fill=fills[pill_id],
        exit=dict(z=p["floor_bottom"] - 12.0, x=(ch["cx"] - ch["hx"], ch["cx"] + ch["hx"]),
                  y=(-ch["hy"], ch["hy"])),
        loss_z=p["floor_bottom"] - 2.0,
        fill_s=1.8 if big else 1.2, settle_s=0.6,
        site_namer=site_namer,
    )
