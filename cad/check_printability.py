#!/usr/bin/env python3
"""FDM printability check for a variant's exported parts (success condition 1).

    python cad/check_printability.py cad/variants/v2_inclined_disc/iron/manifest.json

The manifest (written by each variant's CAD script) lists:
  parts: [{name, stl, print_rotation: [rx, ry, rz] degrees, min_wall: 1.2}]
  clearances: [{a, b, min: 0.3, what: "..."}]   # moving pairs, as assembled

Checks:
  * wall thickness: inward ray from ~20 000 surface samples; the 1st percentile
    must be >= min_wall. (Rays starting on a sharp edge hit the neighbouring face
    and read short, so the extreme minimum is reported but not used to fail.)
  * clearance: exact minimum distance between assembled solids (manifold3d).
  * overhang: in print orientation, downward faces steeper than 45° that are not
    on the bed. Area must be <= `max_overhang_mm2` (default 4 mm², i.e. small
    bridged hole tops only), so the part prints without supports.
Exit status is non-zero if any check fails.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold, Mesh


def _manifold(m: trimesh.Trimesh) -> Manifold:
    return Manifold(Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                         tri_verts=np.asarray(m.faces, np.uint32)))


def wall_thickness(mesh: trimesh.Trimesh, n: int = 20000, seed: int = 0):
    pts, fidx = trimesh.sample.sample_surface_even(mesh, n, seed=seed)
    nrm = mesh.face_normals[fidx]
    origins = pts - nrm * 1e-3
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, -nrm, multiple_hits=False)
    d = np.full(len(pts), np.inf)
    d[ray_idx] = np.linalg.norm(locs - origins[ray_idx], axis=1)
    d = d[np.isfinite(d)]
    return float(np.percentile(d, 1)), float(d.min())


def overhang_area(mesh: trimesh.Trimesh, rot_deg) -> float:
    m = mesh.copy()
    R = trimesh.transformations.euler_matrix(*np.radians(rot_deg), axes="sxyz")
    m.apply_transform(R)
    zmin = m.bounds[0][2]
    nz = m.face_normals[:, 2]
    fz = m.triangles_center[:, 2]
    bad = (nz < -math.cos(math.radians(45))) & (fz > zmin + 0.25)
    return float(m.area_faces[bad].sum())


def check(manifest_path: str | Path) -> bool:
    manifest_path = Path(manifest_path)
    man = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    meshes = {}
    ok = True
    print(f"== {man.get('variant', '?')} / {man.get('pill', '?')}")
    for p in man["parts"]:
        m = trimesh.load(base / p["stl"], force="mesh")
        meshes[p["name"]] = m
        p1, pmin = wall_thickness(m)
        ov = overhang_area(m, p.get("print_rotation", [0, 0, 0]))
        lim = p.get("max_overhang_mm2", 4.0)
        wall_ok = p1 >= p.get("min_wall", 1.2) - 1e-6
        ov_ok = ov <= lim
        ok &= wall_ok and ov_ok and m.is_watertight
        print(f"  {p['name']:28s} wall p1={p1:5.2f} (min ray {pmin:4.2f}) "
              f"{'OK ' if wall_ok else 'FAIL'} | overhang {ov:6.1f} mm2 {'OK ' if ov_ok else 'FAIL'} "
              f"| watertight {m.is_watertight}")
    for c in man.get("clearances", []):
        a, b = _manifold(meshes[c["a"]]), _manifold(meshes[c["b"]])
        inter = a ^ b
        gap = 0.0 if inter.volume() > 1e-6 else a.min_gap(b, 5.0)
        good = gap >= c.get("min", 0.3) - 1e-6
        ok &= good
        print(f"  clearance {c['a']} <-> {c['b']}: {gap:5.2f} mm (need {c.get('min', 0.3)}) "
              f"{'OK' if good else 'FAIL'}  {c.get('what', '')}")
    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    results = [check(p) for p in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
