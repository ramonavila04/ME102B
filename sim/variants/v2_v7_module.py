"""V2 inclined pocket disc packaged as a V7 enclosure module (cad/variants/v2_v7_module).

The disc, hopper bore, cover and the front of the back plate are the V2 parts; what
changes for the pills is the exit duct (38 mm, exit-relief section only for its first
12 mm) and the hopper flange trim. This variant reuses the V2 spec with those two meshes
swapped and the exit test moved to the end of the shorter duct.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad" / "variants" / "v2_v7_module"

# a private copy of the V2 variant, so patching its build constants affects nothing else
_s = importlib.util.spec_from_file_location("v2_for_v7", Path(__file__).with_name("v2_inclined_disc.py"))
V2 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(V2)
_m = importlib.util.spec_from_file_location("v7_build", CAD / "build.py")
M = importlib.util.module_from_spec(_m)
_m.loader.exec_module(M)

RPM = V2.RPM
site_namer = V2.site_namer


def spec(pill_id: str) -> dict:
    if not (CAD / pill_id / "sim_backplate.stl").exists():
        M.build(pill_id)
    V2.build.DUCT_LEN = M.DUCT_LEN            # exit_fn reads this when it is called
    s = V2.spec(pill_id)
    for p in s["parts"]:
        if p["name"] in ("backplate", "hopper"):
            p["stl"] = CAD / pill_id / f"sim_{p['name']}.stl"
    s["name"] = "V2 inclined pocket disc, V7 module"
    return s
