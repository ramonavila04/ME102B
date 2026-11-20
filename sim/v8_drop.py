#!/usr/bin/env python3
"""Pill path in the V8 housing: from a V2 module's pocket to the weighing station.

    python -m sim.v8_drop --pills iron small --trials 200 --workers 4
    python -m sim.v8_drop --pills iron small --trials 200 --workers 4 --dose 4

Same trial, physics and outcomes as `sim.v7_drop` (see its docstring), on the V8 scene:
  * six unmodified V2 modules (cad/variants/v2_inclined_disc), placed as
    cad/variants/v8_housing/layout.py places them: disc, back plate with its 96 mm duct and
    motor saddle, hopper, and the bought drive parts (gearmotor, coupler, strap) as static
    solids, all cropped round the exit and duct;
  * the V8 deck, chute, brackets and pill cup (cad/variants/v8_housing/parts);
  * the V7 inner shell, lower body, funnel posts, weighing station and front panel.
Results go to results/v8_drop[_doseN]/.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim import v7_drop as D  # noqa: E402
from sim.convexify import decompose_file  # noqa: E402

V8 = ROOT / "cad" / "variants" / "v8_housing"
V2 = ROOT / "cad" / "variants" / "v2_inclined_disc"
CACHE = ROOT / "sim" / ".cache" / "v8_parts"
_s = importlib.util.spec_from_file_location("v8_layout", V8 / "layout.py")
Ly = importlib.util.module_from_spec(_s)
_s.loader.exec_module(Ly)
b = Ly.b

# V2 world crop round the exit, the whole 96 mm duct and the motor's rear end
MODULE_CROP = ((-22, 0, -78), (22, 108, 32))


def pt_enc(v, k):
    """V2 world → enclosure for module k (vectorised Ly.pt_enc)."""
    v = np.asarray(v, float)
    a = math.radians(Ly.mod_rot_deg(k))
    c, s = math.cos(a), math.sin(a)
    mx, my = Ly.mouth_xy(k)
    x, y, z = v[..., 0], v[..., 1] - Ly.MOUTH_Y, v[..., 2]
    return np.stack([c * x - s * y + mx, s * x + c * y + my, z + Ly.H], -1)


def _export_static():
    """STLs (enclosure frame) of the V7 pieces kept in the V8, and of the V2 drive solids."""
    import cadquery as cq
    CACHE.mkdir(parents=True, exist_ok=True)
    want = {"v7_shell", "v7_lower", "drive_iron", "drive_small"}
    if all((CACHE / f"{n}.stl").exists() for n in want):
        return
    _, shell, lower, _ = Ly.v7_enclosure_pieces()
    cq.exporters.export(cq.Workplane(obj=shell), str(CACHE / "v7_shell.stl"), tolerance=0.05, angularTolerance=0.1)
    cq.exporters.export(cq.Workplane(obj=lower), str(CACHE / "v7_lower.stl"), tolerance=0.05, angularTolerance=0.1)
    sp = importlib.util.spec_from_file_location("v2_assemble", V2 / "assemble.py")
    a = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(a)
    for kit in ("iron", "small"):
        solids = [s.val() for n, c, s in a.drive_bodies(kit) if n in ("gearmotor", "coupler_flexible", "clamp")]
        cq.exporters.export(cq.Workplane(obj=cq.Compound.makeCompound(solids)), str(CACHE / f"drive_{kit}.stl"),
                            tolerance=0.05, angularTolerance=0.1)


def scene_pieces(kit):
    D.export_v7_parts()
    _export_static()
    out = []
    crop_enc = ((-110, -165, -165), (110, 110, 12))
    out.append(("Enclosure_shell", decompose_file(CACHE / "v7_shell.stl", tol=0.15, min_cell=2.0, crop=crop_enc), lambda v: v))
    out.append(("Enclosure_lower", decompose_file(CACHE / "v7_lower.stl", tol=0.15, min_cell=2.0, crop=crop_enc), lambda v: v))
    for n in ("Funnel_mounts", "Weighing_station", "Front_panel_controls"):
        tol, cell, _ = D.V7_PARTS[n]
        out.append((n, decompose_file(D.V7_CACHE / f"{n}.stl", tol=tol, min_cell=cell), lambda v: v))
    out.append(("Deck", decompose_file(V8 / "parts" / "deck.stl", tol=0.15, min_cell=2.0,
                                       crop=((-90, -90, -6), (90, 90, 36))), lambda v: v))   # with the 30 mm fence
    for n in ("chute", "bracket_right", "bracket_left", "bracket_front"):
        out.append((f"Chute_{n}", decompose_file(V8 / "parts" / f"{n}.stl", tol=0.1, min_cell=1.0), lambda v: v))
    out.append(("Weighing_cup", decompose_file(V8 / "parts" / "pill_cup.stl", tol=0.1, min_cell=1.0), lambda v: v))
    parts = [("disc", V2 / kit / "disc.stl", 0.05), ("backplate", V2 / kit / "backplate.stl", 0.1),
             ("hopper", V2 / kit / "hopper.stl", 0.1), ("drive", CACHE / f"drive_{kit}.stl", 0.2)]
    for name, stl, tol in parts:
        pcs = decompose_file(stl, tol=tol, min_cell=0.4, crop=MODULE_CROP)
        for k in range(Ly.N_MOD):
            out.append((f"m{k + 1}_{name}", pcs, (lambda kk: (lambda v: pt_enc(v, kk)))(k)))
    return out


def release_state(kit, k, pill, tilt, spin, az, v_tan):
    """As sim.v7_drop.release_state, with the V8 placement (a rotation about z, no mirror)."""
    import trimesh
    pp = b.pocket_params(kit)
    ang = math.radians(pp.get("exit_angle", 90.0))
    c_loc = np.array([pp["r_center"] * math.cos(ang), pp["r_center"] * math.sin(ang),
                      -pp["depth"] - b.RUN + pill.thickness / 2 + 0.2])
    a = math.radians(Ly.mod_rot_deg(k))
    R_w = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    cb, sb = math.cos(math.radians(b.BETA)), math.sin(math.radians(b.BETA))
    R_lw = np.array([[1, 0, 0], [0, cb, -sb], [0, sb, cb]])
    R_le = R_w @ R_lw
    pos = pt_enc(D.local_to_world(c_loc), k)

    def rot(axis, deg):
        return trimesh.transformations.rotation_matrix(math.radians(deg), axis)[:3, :3]
    R_p = R_le @ rot([0, 0, 1], az) @ rot([1, 0, 0], tilt) @ rot([0, 0, 1], spin)
    v_loc = np.array([-math.sin(ang), math.cos(ang), 0.0]) * v_tan
    return pos, R_p, R_le @ v_loc


D.scene_pieces = scene_pieces
D.release_state = release_state
D.OUT = ROOT / "results" / "v8_drop"

if __name__ == "__main__":
    D.main()
