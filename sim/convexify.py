"""Exact-boundary convex decomposition of a printed part for MuJoCo.

MuJoCo collides meshes through their convex hulls, so a concave part (a rotor
with pockets, a funnel, a chute) must be split into convex pieces. Approximate
decomposers (V-HACD, CoACD) can bulge past the real surface by a millimetre or
more, which would close the 0.3–3 mm gaps this project is about.

This decomposer only ever cuts the solid with axis-aligned planes and hulls each
piece. Every hull vertex lies on the original surface or on a cut plane, so a
hull can only add material inside concave regions. A piece is split again until
its hull adds less than `tol` mm of material on average over its surface, or
the cell reaches `min_cell` mm. The worst added thickness per piece is reported,
so the modelled gaps are known.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold, Mesh

CACHE = Path(__file__).resolve().parent / ".cache" / "convex"


@dataclass
class Piece:
    vertices: np.ndarray  # (n, 3) mm
    faces: np.ndarray
    excess_mm: float      # hull volume beyond the solid, divided by hull area


def _to_manifold(mesh: trimesh.Trimesh) -> Manifold:
    m = Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                      tri_verts=np.asarray(mesh.faces, np.uint32)))
    if m.status().name != "NoError":
        raise ValueError(f"mesh is not a closed manifold: {m.status()}")
    return m


def _mesh_of(m: Manifold) -> trimesh.Trimesh:
    g = m.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts),
                           process=False)


def _crop(m: Manifold, lo, hi) -> Manifold:
    for axis in range(3):
        n = np.zeros(3); n[axis] = 1.0
        m = m.trim_by_plane(n.tolist(), float(lo[axis]))
        m = m.trim_by_plane((-n).tolist(), float(-hi[axis]))
    return m


def decompose(mesh: trimesh.Trimesh, tol: float = 0.05, min_cell: float = 0.8,
              crop: tuple | None = None, max_pieces: int = 4000) -> list[Piece]:
    root = _to_manifold(mesh)
    if crop is not None:
        root = _crop(root, *crop)
    pieces: list[Piece] = []
    stack = [root]
    while stack:
        m = stack.pop()
        if m.is_empty() or m.volume() < 1e-3:
            continue
        comps = m.decompose()
        if len(comps) > 1:
            stack.extend(comps)
            continue
        hull = m.hull()
        area = max(hull.surface_area(), 1e-9)
        excess = (hull.volume() - m.volume()) / area
        bb = np.array(m.bounding_box()).reshape(2, 3)
        size = bb[1] - bb[0]
        if excess <= tol or size.max() <= min_cell:
            hm = _mesh_of(hull)
            pieces.append(Piece(np.asarray(hm.vertices), np.asarray(hm.faces), float(excess)))
            if len(pieces) > max_pieces:
                raise RuntimeError("decomposition exceeded max_pieces; loosen tol or crop")
            continue
        axis = int(np.argmax(size))
        cut = float(_best_cut(m, bb, axis))
        n = [0.0, 0.0, 0.0]; n[axis] = 1.0
        a, b = m.split_by_plane(n, cut)
        stack.extend([a, b])
    return pieces


def _best_cut(m: Manifold, bb, axis: int) -> float:
    """Cut at the middle of the longest axis; nudged off exact symmetry planes
    so cuts don't land on a face of the part (which makes slivers)."""
    lo, hi = bb[0][axis], bb[1][axis]
    return lo + (hi - lo) * 0.5 + 1e-3 * (hi - lo)


def decompose_file(stl_path: str | Path, tol: float = 0.05, min_cell: float = 0.8,
                   crop: tuple | None = None) -> list[Piece]:
    """Cached decomposition of an STL in millimetres."""
    stl_path = Path(stl_path)
    key = hashlib.sha256(stl_path.read_bytes()
                         + json.dumps([tol, min_cell, crop], default=list).encode()).hexdigest()[:20]
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{stl_path.stem}_{key}.npz"
    if cf.exists():
        d = np.load(cf, allow_pickle=True)
        return [Piece(v, f, e) for v, f, e in zip(d["v"], d["f"], d["e"])]
    mesh = trimesh.load(stl_path, force="mesh")
    pieces = decompose(mesh, tol=tol, min_cell=min_cell, crop=crop)
    np.savez_compressed(cf, v=np.array([p.vertices for p in pieces], dtype=object),
                        f=np.array([p.faces for p in pieces], dtype=object),
                        e=np.array([p.excess_mm for p in pieces]))
    return pieces


if __name__ == "__main__":
    import sys
    import time
    t = time.time()
    ps = decompose_file(sys.argv[1])
    ex = np.array([p.excess_mm for p in ps])
    print(f"{len(ps)} pieces in {time.time()-t:.1f}s; excess mean {ex.mean():.3f} "
          f"max {ex.max():.3f} mm")
