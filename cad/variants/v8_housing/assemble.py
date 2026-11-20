#!/usr/bin/env python3
"""Assemble the V8 housing with six V2 modules, check for clashes, and write views.

    python cad/variants/v8_housing/assemble.py              # iron modules: check + views
    python cad/variants/v8_housing/assemble.py small --step # also write assembly STEP/STL

Clashes are measured on tessellated solids (manifold3d), so a reported overlap under
~1 mm³ is tessellation noise. Expected overlaps (press fits, inserts, the strap clamp, the
V2 side plates in their pod slots' glue gap) are listed in EXPECTED and reported apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from manifold3d import Manifold, Mesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout as Ly  # noqa: E402

PARTS = HERE / "parts"
NEW = ["deck", "chute", "pill_cup", "tray", "bracket_right", "bracket_left", "bracket_front"]
# pairs that touch or overlap on purpose (substring match on both names)
EXPECTED = [("disc", "shaft"), ("gearmotor", "coupler"), ("shaft", "coupler"), ("clamp", "gearmotor"),
            ("shaft", "collar"), ("side_", "pod"), ("v7_small", "lower"), ("v7_small", "shell"),
            ("Station_fasteners", "lower"), ("Station_fasteners", "Weighing"), ("chute", "bracket"),
            ("bracket", "Funnel_mounts"), ("lower", "shell"), ("Weighing", "lower"), ("deck", "shell"),
            ("Front_panel", "shell"), ("Front_panel", "lower"), ("bearing", "shaft"), ("spacer", "shaft")]


def to_mesh(shape, tol=0.2):
    if isinstance(shape, cq.Workplane):
        shape = shape.val() if len(shape.vals()) == 1 else cq.Compound.makeCompound(shape.vals())
    v, f = shape.tessellate(tol, 0.3)
    return trimesh.Trimesh(np.array([p.toTuple() for p in v]), np.array(f), process=True)


def man(t: trimesh.Trimesh):
    parts = [p for p in t.split(only_watertight=False)] or [t]
    out = Manifold()
    for p in parts:
        m = Manifold(Mesh(vert_properties=np.asarray(p.vertices, np.float32), tri_verts=np.asarray(p.faces, np.uint32)))
        out = out + m
    return out


def bodies(kit: str):
    """[(name, group, trimesh)] for the whole dispenser."""
    out = []
    deck, shell, lower, small = Ly.v7_enclosure_pieces()
    out += [("v7_shell", "v7", to_mesh(shell)), ("v7_lower", "v7", to_mesh(lower))]
    out += [(f"v7_small{i}", "v7", to_mesh(s)) for i, s in enumerate(small)]
    for n in ("Funnel_mounts", "Weighing_station", "Front_panel_controls"):
        out.append((n, "v7", to_mesh(Ly.v7(n), 0.3)))
    out.append(("Station_fasteners", "v7", to_mesh(cq.Compound.makeCompound(Ly.v7_kept_fasteners()), 0.3)))
    for n in NEW:
        out.append((n, "new", trimesh.load(PARTS / f"{n}.stl")))
    pod = cq.importers.importStep(str(PARTS / "pod.step"))
    mods = [(n, c, s) for n, c, s in Ly.v2_module_bodies(kit)]
    for k in range(Ly.N_MOD):
        out.append((f"m{k}_pod", f"m{k}", to_mesh(pod.rotate((0, 0, 0), (0, 0, 1), 60 * k))))
        for n, c, s in mods:
            out.append((f"m{k}_{n}", f"m{k}", to_mesh(Ly.to_enc(s, k))))
    return out


def expected(a, b):
    a2, b2 = a.split("_", 1)[-1] if a.startswith("m") and a[1].isdigit() else a, \
        b.split("_", 1)[-1] if b.startswith("m") and b[1].isdigit() else b
    for p, q in EXPECTED:
        if (p in a2 and q in b2) or (q in a2 and p in b2):
            # module parts only "expected" within the same module
            if a.startswith("m") and b.startswith("m") and a[:2] != b[:2]:
                return False
            return True
    return False


def check(kit: str):
    B = bodies(kit)
    M = [(n, g, man(t), t.bounds) for n, g, t in B]
    hits, exp = [], []
    for i in range(len(M)):
        for j in range(i + 1, len(M)):
            n1, g1, m1, b1 = M[i]
            n2, g2, m2, b2 = M[j]
            if g1 == g2 and g1 == "v7":
                continue
            if g1 == g2 and g1.startswith("m") and expected(n1, n2):
                continue
            if np.any(b1[1] < b2[0]) or np.any(b2[1] < b1[0]):
                continue
            v = (m1 ^ m2).volume()
            if v > 1.0:
                (exp if expected(n1, n2) else hits).append((n1, n2, v))
    print(f"== {kit}: unexpected overlaps (> 1 mm³)")
    for n1, n2, v in sorted(hits, key=lambda h: -h[2]):
        print(f"  {n1} / {n2}: {v:.1f} mm³")
    if not hits:
        print("  none")
    print(f"== expected contacts: {len(exp)} (inserts, fits, slots)")
    allv = np.vstack([t.vertices for _, _, t in B])
    r = np.hypot(allv[:, 0], allv[:, 1])
    print(f"== extent: x {allv[:, 0].min():.0f}..{allv[:, 0].max():.0f}, y {allv[:, 1].min():.0f}..{allv[:, 1].max():.0f}, "
          f"z {allv[:, 2].min():.0f}..{allv[:, 2].max():.0f}; furthest point {r.max():.0f} mm from the axis")
    return B, hits


COLORS = {"v7": (0.75, 0.75, 0.78), "new": (0.30, 0.55, 0.85)}


def render(B, path, views=(("iso", 30, -60), ("front", 10, -90), ("top", 89, -90))):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(6 * len(views), 6.5))
    light = np.array([0.3, -0.5, 0.8])
    light /= np.linalg.norm(light)
    for i, (title, el, az) in enumerate(views):
        ax = fig.add_subplot(1, len(views), i + 1, projection="3d")
        for n, g, t in B:
            if "small" in n or n == "Station_fasteners":
                continue
            t2 = t.simplify_quadric_decimation(face_count=min(len(t.faces), 3000)) if len(t.faces) > 3000 else t
            base = COLORS.get(g, (0.95, 0.6, 0.25))
            if "hopper" in n or "cover" in n:
                base = (0.6, 0.8, 0.95)
            if "gearmotor" in n:
                base = (0.85, 0.7, 0.2)
            if "pod" in n or "side_" in n:
                base = (0.35, 0.35, 0.38)
            shade = 0.45 + 0.55 * np.clip(t2.face_normals @ light, 0, 1)
            cols = np.clip(np.outer(shade, base), 0, 1)
            pc = Poly3DCollection(t2.triangles, facecolors=cols, edgecolors="none", linewidths=0)
            ax.add_collection3d(pc)
        ax.set_xlim(-200, 200), ax.set_ylim(-200, 200), ax.set_zlim(-170, 230)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(el, az)
        ax.set_axis_off()
        ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=90)


def sections(B, path):
    """Side section at x = 0 and a plan of the deck, pods and duct mouths."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def col(n, g):
        if g == "new":
            return "tab:blue"
        if g == "v7":
            return "0.45"
        if "disc" in n or "backplate" in n:
            return "tab:orange"
        if "gearmotor" in n:
            return "goldenrod"
        if "pod" in n or "side_" in n:
            return "0.2"
        return "lightsteelblue"
    fig, ax = plt.subplots(1, 2, figsize=(18, 8.5))
    for n, g, t in B:
        if "small" in n or n == "Station_fasteners":
            continue
        s = t.section(plane_origin=[0.01, 0, 0], plane_normal=[1, 0, 0])
        if s is not None:
            for e in s.discrete:
                ax[0].plot(e[:, 1], e[:, 2], color=col(n, g), lw=0.8)
    ax[0].set_title("Section x = 0, front at the left: chute (blue) from the drop ring to the cup "
                    "on the weighing station, under the front panel", fontsize=9)
    for n, g, t in B:
        z = {"deck": -2.5, "chute": None}.get(n, 3.0 if "pod" in n else None)
        if n == "chute":
            # floor outline: section just above the floor plane is awkward; use the plan hull
            v = t.vertices
            from scipy.spatial import ConvexHull
            hpts = v[ConvexHull(v[:, :2]).vertices][:, :2]
            ax[1].fill(hpts[:, 0], hpts[:, 1], color="tab:blue", alpha=0.15, lw=0)
            continue
        if z is None:
            continue
        s = t.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if s is not None:
            for e in s.discrete:
                ax[1].plot(e[:, 0], e[:, 1], color=col(n, g), lw=0.8)
    for k in range(Ly.N_MOD):
        mx, my = Ly.mouth_xy(k)
        ax[1].add_patch(plt.Circle((mx, my), 10, color="tab:red", alpha=0.35))
        d = Ly.pt_enc((0, 0, 0), k)
        ax[1].plot(d[0], d[1], "k+")
        ax[1].annotate(f"module {k + 1}", (d[0], d[1]), fontsize=8)
    ax[1].add_patch(plt.Circle((0, 0), 42, fill=False, ls="--", color="tab:red"))
    ax[1].set_title("Plan: deck (blue), pods (dark), chute footprint (shaded), duct mouths (red), "
                    "disc centres (+)", fontsize=9)
    for a in ax:
        a.set_aspect("equal")
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=80)


def export_step(kit: str):
    a = cq.Assembly(name=f"v8_housing_{kit}")
    deck, shell, lower, small = Ly.v7_enclosure_pieces()
    for n, s in (("v7_inner_shell", shell), ("v7_lower_body", lower)):
        a.add(s, name=n, color=cq.Color("gray70"))
    for n in ("Funnel_mounts", "Weighing_station", "Front_panel_controls"):
        a.add(Ly.v7(n), name=n, color=cq.Color("gray60"))
    a.add(cq.Compound.makeCompound(Ly.v7_kept_fasteners()), name="deck_fasteners", color=cq.Color("gray60"))
    for n in NEW:
        a.add(cq.importers.importStep(str(PARTS / f"{n}.step")), name=n, color=cq.Color("steelblue"))
    pod = cq.importers.importStep(str(PARTS / "pod.step"))
    for k in range(Ly.N_MOD):
        a.add(pod.rotate((0, 0, 0), (0, 0, 1), 60 * k), name=f"module_{k + 1}_pod", color=cq.Color("gray30"))
        for n, c, s in Ly.v2_module_bodies(kit):
            a.add(Ly.to_enc(s, k), name=f"module_{k + 1}_{n}", color=cq.Color(c))
    a.save(str(HERE / f"v8_assembly_{kit}.step"))
    print(f"wrote v8_assembly_{kit}.step")


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    kit = args[0] if args else "iron"
    B, hits = check(kit)
    (HERE / "views").mkdir(exist_ok=True)
    render(B, HERE / "views" / f"v8_{kit}.png")
    sections(B, HERE / "views" / f"v8_sections_{kit}.png")
    if "--step" in sys.argv:
        export_step(kit)
