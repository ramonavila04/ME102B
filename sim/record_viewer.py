#!/usr/bin/env python3
"""Record real simulator trials for the three.js viewer (viewer/index.html).

    python -m sim.record_viewer v2_inclined_disc:iron:1001 v0_original:iron:1003 ...

Each entry runs `sim.engine.run_trial(..., record=True)` — the same code path as the
campaigns — and stores the variant's meshes (world frame, mm), the pill shape, the
recorded poses at 60 fps and the cycle outcomes in viewer/trials/<variant>_<pill>_<seed>.json.
The viewer only replays this data; nothing is animated by hand.
"""
from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.engine import run_trial  # noqa: E402
from sim.pills import PILLS  # noqa: E402

OUT = ROOT / "viewer" / "trials"


def _mesh_json(stl, crop=None, faces=6000):
    m = trimesh.load(stl, force="mesh")
    if crop is not None:
        lo, hi = np.array(crop[0], float), np.array(crop[1], float)
        box = trimesh.creation.box(bounds=[lo, hi])
        try:
            m = m.intersection(box)
        except Exception:
            pass
    if len(m.faces) > faces:
        m = m.simplify_quadric_decimation(face_count=faces)
    return dict(v=np.round(m.vertices, 2).reshape(-1).tolist(), f=m.faces.reshape(-1).tolist())


def record(variant: str, pill: str, seed: int) -> Path:
    mod = importlib.import_module(f"sim.variants.{variant}")
    spec = mod.spec(pill)
    res = run_trial(mod.spec, pill, seed, record=True)
    parts = []
    for p in spec["parts"]:
        parts.append(dict(name=p["name"], body=p["body"], **_mesh_json(p["stl"], p.get("crop"))))
    pm = PILLS[pill].mesh(16)
    j = spec["joint"]
    joint = dict(type=j["type"], axis=list(j.get("axis", (0, 0, 1))), pos=list(j.get("pos", (0, 0, 0))),
                 crank_r=j.get("crank_r"))
    data = dict(
        variant=variant, variant_name=spec["name"], pill=pill, pill_label=PILLS[pill].label, seed=seed,
        fill=res.fill, mu_part=round(res.mu_part, 3), mu_pill=round(res.mu_pill, 3),
        passed=res.passed, leak=res.leak, sim_unstable=res.sim_unstable,
        cycles=[dict(outcome=c.outcome, count=c.count, steps=c.steps, duration_s=round(c.duration_s, 3),
                     jam_site=c.jam_site, jam_pos_mm=c.jam_pos_mm) for c in res.cycles],
        joint=joint, parts=parts,
        pill_mesh=dict(v=np.round(pm.vertices, 3).reshape(-1).tolist(), f=pm.faces.reshape(-1).tolist()),
        frames=[[f[0], f[1], f[2]] for f in res.frames],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{variant}_{pill}_{seed}.json"
    path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"{path.name}: {[(c.outcome, c.count) for c in res.cycles]} "
          f"{len(res.frames)} frames, {path.stat().st_size / 1e6:.1f} MB")
    return path


def rebuild_index():
    items = []
    for p in sorted(OUT.glob("*.json")):
        if p.name == "index.json":
            continue
        d = json.loads(p.read_text())
        items.append(dict(file=p.name, variant=d["variant_name"], pill=d["pill"], seed=d["seed"],
                          outcomes=[c["outcome"] for c in d["cycles"]],
                          jam_site=next((c["jam_site"] for c in d["cycles"] if c["jam_site"]), None)))
    (OUT / "index.json").write_text(json.dumps(items, indent=1))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        v, p, s = arg.split(":")
        record(v, p, int(s))
    rebuild_index()
