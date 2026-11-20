"""Can the chute be put into the V7 enclosure? (run from the repo root)

    python sim/v7_chute_install.py [chute folder] [--after bracket_left,bracket_right]

Default folder: cad/variants/v2_v7_module/chute (the chute, its brackets and the cup).

The chute's lip sits under the enclosure's front window lintel and its sides under ribs, so it
cannot be lowered straight into place. Checked path, with the deck off and the front panel
and brackets already fitted: hold the chute OFFSET mm behind its final position, lower it
straight down from above the rim, then slide it forward OFFSET mm onto the brackets.
Brackets named with --after are fitted after the chute instead: each is then lowered
straight down onto its post, with the chute in place.

Each moving part is split into exact convex pieces; obstacle surfaces are sampled every
~0.5 mm and must stay MARGIN mm outside every piece. Exit status 1 if any step is blocked.
"""
import sys

import numpy as np
import trimesh

sys.path.insert(0, '.')
from sim.convexify import decompose_file  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith('--')]
D = (args[0].rstrip('/') + '/') if args else 'cad/variants/v2_v7_module/chute/'
AFTER = []
if '--after' in sys.argv:
    AFTER = sys.argv[sys.argv.index('--after') + 1].split(',')
BRACKETS = ['bracket_right', 'bracket_left', 'bracket_front']
V7 = [('enclosure', 'sim/.cache/v7_parts/Enclosure.stl'), ('funnel_mounts', 'sim/.cache/v7_parts/Funnel_mounts.stl'),
      ('station', 'sim/.cache/v7_parts/Weighing_station.stl'),
      ('front_panel', 'sim/.cache/v7_parts/Front_panel_controls.stl')]
OFFSET, MARGIN = 40.0, 0.25


def hulls_of(stl):
    out = []
    for p in decompose_file(stl, tol=0.1, min_cell=1.0):
        h = trimesh.Trimesh(np.asarray(p.vertices)).convex_hull
        out.append((h.face_normals, (h.face_normals * h.triangles[:, 0]).sum(1), h.bounds))
    return out, trimesh.load(stl).bounds


def sample(sources, cb, reach):
    """Obstacle points near the moving part's box `cb` grown by `reach` (deck region excluded:
    the deck is off)."""
    obs = {}
    for k, f in sources:
        m = trimesh.load(f)
        c = m.triangles_center
        keep = ((c[:, 0] > cb[0][0] - reach[0]) & (c[:, 0] < cb[1][0] + reach[0]) & (c[:, 1] > cb[0][1] - reach[1])
                & (c[:, 1] < cb[1][1] + reach[1]) & (c[:, 2] > cb[0][2] - 5) & (c[:, 2] < -5.2))
        if not keep.any():
            continue
        sub = m.submesh([np.where(keep)[0]], append=True)
        p, _ = trimesh.sample.sample_surface(sub, min(int(sub.area / 0.25) + 1, 300000))
        obs[k] = np.vstack([p, sub.vertices])
    return obs


def hits(hulls, cb, obs, off, margin=MARGIN):
    res = {}
    for k, p in obs.items():
        q = p - off
        q = q[(q[:, 2] > cb[0][2] - 1) & (q[:, 2] < cb[1][2] + 1) & (q[:, 1] > cb[0][1] - 1) & (q[:, 1] < cb[1][1] + 1)
              & (q[:, 0] > cb[0][0] - 1) & (q[:, 0] < cb[1][0] + 1)]
        n = 0
        for A, b, bb in hulls:
            r = q[(q[:, 0] > bb[0][0]) & (q[:, 0] < bb[1][0]) & (q[:, 1] > bb[0][1]) & (q[:, 1] < bb[1][1])
                  & (q[:, 2] > bb[0][2]) & (q[:, 2] < bb[1][2])]
            if len(r):
                n += int(((r @ A.T) - b < -margin).all(1).sum())
        if n:
            res[k] = n
    return res


def run_path(name, stl, sources, steps, reach):
    hulls, cb = hulls_of(stl)
    obs = sample(sources, cb, reach)
    bad = 0
    for off in steps:
        h = hits(hulls, cb, obs, np.array(off, float))
        if h:
            bad += 1
            print(f"{name}: blocked at offset {tuple(round(v, 1) for v in off)}: {h}")
    print(f"{name}: {len(steps)} steps, {bad} blocked")
    return bad


bad = 0
chute_steps = [(0, OFFSET, dz) for dz in (140, 130, 120, 110, 100, 95, 90, 80, 64, 48, 32, 16, 8, 4, 2, 0)] + \
              [(0, dy, 0.0) for dy in np.arange(OFFSET, -0.1, -2.5)]
before = V7 + [(n, D + n + '.stl') for n in BRACKETS if n not in AFTER]
bad += run_path('chute', D + 'chute.stl', before, chute_steps, (70, 90))
for n in AFTER:
    sources = V7 + [(m, D + m + '.stl') for m in BRACKETS if m != n] + [('chute', D + 'chute.stl')]
    bad += run_path(n, D + n + '.stl', sources, [(0, 0, dz) for dz in (80, 60, 40, 30, 20, 10, 5, 2, 1, 0)], (30, 30))
print("PASS" if not bad else "FAIL")
sys.exit(1 if bad else 0)
