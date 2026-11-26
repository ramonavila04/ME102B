"""V2 inclined pocket disc as a V7 module with a VERTICAL canister
(cad/variants/v2_v7_vertical/concept.py).

Same disc, back plate, short exit duct and exit test as `v2_v7_module`; the hopper is
replaced by the concept's: the V2 bore kept for 15 mm in front of the disc, a throat, and an
upright canister standing over the module like the V7 canisters. The throat's solid closes
the upper half of the bore (the V2 half-cover's job); there is no cover part. Pills are poured into the canister (spawned inside its upright tube)
and fall through the throat onto the disc.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad" / "variants" / "v2_v7_vertical"

_s = importlib.util.spec_from_file_location("v7_module_for_vertical", Path(__file__).with_name("v2_v7_module.py"))
BASE = importlib.util.module_from_spec(_s)
_s.loader.exec_module(BASE)
_c = importlib.util.spec_from_file_location("v7_vertical_concept", CAD / "concept.py")
C = importlib.util.module_from_spec(_c)
_c.loader.exec_module(C)

RPM = BASE.RPM
site_namer = BASE.site_namer


def spec(pill_id: str) -> dict:
    if not (CAD / pill_id / "sim_hopper.stl").exists():
        C.export_sim(pill_id, CAD / pill_id)
    s = BASE.spec(pill_id)
    s["parts"] = [p for p in s["parts"] if p["name"] != "cover"]   # the throat caps the bore
    for p in s["parts"]:
        if p["name"] == "hopper":
            p["stl"] = CAD / pill_id / "sim_hopper.stl"
    s["parts"].append(dict(name="hopper_throat", stl=CAD / pill_id / "sim_throat.stl", body="static", tol=0.1))
    s["parts"].append(dict(name="hopper_canister", stl=CAD / pill_id / "sim_canister.stl", body="static", tol=0.1))
    from sim.pills import PILLS
    pill_r = PILLS[pill_id].bounding_radius
    Y0, Z0 = C.m.Y0, C.m.Z0

    def accept(x, y, z, r):
        """Inside the canister's upright tube (module frame: world turned 180 deg about z)."""
        xm, ym, zm = -x, -y + Y0, z + Z0
        return (math.hypot(xm, ym - C.CAN_Y) < C.CAN_R - r - 1.0 and C.THROAT_Z + r + 1.0 < zm < C.CAN_TOP_Z + 150)

    # sampling box: the tube, in the world frame
    R = C.CAN_R
    xs = (-R, R)
    ys = (-(C.CAN_Y + R) + Y0, -(C.CAN_Y - R) + Y0)
    zs = (C.THROAT_Z - Z0, C.CAN_TOP_Z + 150 - Z0)
    s["spawn"] = dict(x=xs, y=(min(ys), max(ys)), z=zs, accept=accept)
    s["fill_s"] = 4.5          # a longer fall than the V2's pour into the leaning hopper
    s["name"] = "V2 inclined pocket disc, V7 module, vertical canister"
    return s
