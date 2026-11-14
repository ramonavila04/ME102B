"""Pill set used by every variant (PLAN.md section 1, ASSUMPTIONS A2/A3).

All lengths in millimetres, masses in grams. Edit the nominal values here after
measuring real pills; CAD and sim both read this file.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import trimesh


@dataclass(frozen=True)
class Pill:
    id: str
    label: str
    kind: str          # "tablet" | "caplet" | "capsule"
    length: float      # longest dimension (diameter for round tablets)
    width: float       # second dimension (diameter for round tablets and capsules)
    thickness: float   # smallest dimension
    band: float        # straight side-wall height for tablets/caplets (0 for capsules)
    tol: float         # ± tolerance applied to length/width/thickness
    tol_length: float  # ± tolerance on length (capsules differ)
    mass_g: float

    @property
    def bounding_radius(self) -> float:
        return 0.5 * float(np.linalg.norm([self.length, self.width, self.thickness]))

    def sample(self, rng: np.random.Generator) -> "Pill":
        """Draw one pill with every dimension uniform inside its tolerance."""
        d = lambda t: rng.uniform(-t, t)
        if self.kind == "tablet":
            dia = self.length + d(self.tol)
            th = self.thickness + d(self.tol)
            return replace(self, length=dia, width=dia, thickness=th,
                           band=self.band * th / self.thickness)
        if self.kind == "capsule":
            dia = self.width + d(self.tol)
            return replace(self, length=self.length + d(self.tol_length), width=dia, thickness=dia)
        th = self.thickness + d(self.tol)
        return replace(self, length=self.length + d(self.tol_length), width=self.width + d(self.tol),
                       thickness=th, band=self.band * th / self.thickness)

    def mesh(self, segments: int = 32) -> trimesh.Trimesh:
        """Convex surface mesh of the pill, centred, thickness along z, length along x."""
        if self.kind == "capsule":
            m = trimesh.creation.capsule(height=self.length - self.width, radius=self.width / 2,
                                         count=[segments, segments // 2])
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
            return m
        # Tablet / caplet: plan outline (circle or stadium) with a straight band
        # and domed faces. Each face is an elliptical dome over the outline.
        cap = (self.thickness - self.band) / 2
        a, b = self.length / 2, self.width / 2
        straight = a - b  # half-length of the straight part of a stadium (0 for a circle)
        pts = []
        rings = 4
        for k in range(rings):  # dome rings from rim (k=0) toward the top
            s = 1 - (k / rings) * 0.999
            h = self.band / 2 + cap * np.sqrt(max(0.0, 1 - s * s))
            for t in np.linspace(0, 2 * np.pi, segments, endpoint=False):
                x, y = b * s * np.cos(t), b * s * np.sin(t)
                x += np.sign(np.cos(t)) * straight * s if straight > 0 else 0.0
                pts += [(x, y, h), (x, y, -h)]
        pts += [(0, 0, self.thickness / 2), (0, 0, -self.thickness / 2)]
        return trimesh.convex.convex_hull(np.array(pts))


PILLS = {
    "iron": Pill("iron", "Nature Made Iron 65 mg (team test pill, ESTIMATED size)", "tablet",
                 length=9.5, width=9.5, thickness=5.0, band=2.6, tol=0.15, tol_length=0.15,
                 mass_g=0.40),
    "small": Pill("small", "Small round tablet (81 mg aspirin class)", "tablet",
                  length=6.0, width=6.0, thickness=2.8, band=1.6, tol=0.10, tol_length=0.10,
                  mass_g=0.10),
    "caplet": Pill("caplet", "Large oblong caplet (multivitamin class)", "caplet",
                   length=19.0, width=8.5, thickness=6.5, band=3.5, tol=0.20, tol_length=0.20,
                   mass_g=1.20),
    "cap0": Pill("cap0", "Size-0 hard capsule", "capsule",
                 length=21.7, width=7.65, thickness=7.65, band=0.0, tol=0.08, tol_length=0.30,
                 mass_g=0.50),
}

if __name__ == "__main__":
    for p in PILLS.values():
        m = p.mesh()
        ext = m.extents
        print(f"{p.id:7s} extents {ext.round(2)} vol {m.volume:7.1f} mm3 "
              f"density {p.mass_g / m.volume * 1000:.2f} g/cc watertight={m.is_watertight}")
