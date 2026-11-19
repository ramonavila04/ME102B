#!/usr/bin/env python3
"""Pill path from a V7 module's pocket to the V7 weighing station.

    python -m sim.v7_drop --pills iron small --trials 200 --workers 4

The module campaign (`sim.campaign v2_v7_module`) stops counting a pill at the beam-break,
8 mm into the exit duct. This run follows it the rest of the way, through the parts the team
designed: the duct end, the V7 central opening, the V7 funnel (an inclined chute to the
front) and the weighing station.

Scene (all static, enclosure frame, mm): the V7 enclosure, funnel, funnel mounts, weighing
station and front panel from `cad/onshape/V7_Pill_Dispenser_Heat_Inserts.step`, and all six
modules' exit regions (disc, back plate with duct, hopper; cropped around the exit) placed
exactly as `cad/variants/v2_v7_module/assemble.py` places them.

Each trial draws, with its own seed: the module (1 to 6), the pill's size inside its
tolerance, part and pill friction 0.2 to 0.6 (the campaign's range), the pill's tilt in the
pocket (up to 20°) and spin, and the speed the disc gave it (0 to 65 mm/s, the pocket's
speed at 25 rpm). The pill starts seated in the pocket that is over the exit hole, with the
disc stopped, so the start is the same one the campaign sees when a pill reaches the exit.

Outcome per trial:
  ok        the pill comes to rest touching the weighing station
  stuck     it comes to rest anywhere else (the part it rests on is reported)
  escaped   it leaves the scene
  moving    still moving after the time limit
Physics settings (time step, contact model) are the campaign's, from sim/engine.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import multiprocessing as mp
import sys
import time
from pathlib import Path

import mujoco
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim import engine as E  # noqa: E402
from sim.convexify import decompose_file  # noqa: E402
from sim.pills import PILLS  # noqa: E402

MOD_DIR = ROOT / "cad" / "variants" / "v2_v7_module"
V7_STEP = ROOT / "cad" / "onshape" / "V7_Pill_Dispenser_Heat_Inserts.step"
V7_CACHE = ROOT / "sim" / ".cache" / "v7_parts"
V7_PARTS = {   # name in the STEP → (decomposition tol, min cell, crop box in the enclosure frame)
    "Enclosure": (0.15, 2.0, ((-90, -165, -165), (90, 90, 2))),
    "Funnel": (0.15, 2.0, None),
    "Funnel_mounts": (0.15, 2.0, None),
    "Weighing_station": (0.1, 1.0, None),
    "Front_panel_controls": (0.15, 2.0, None),
}
# around the exit, in the V2 world frame the module's sim STLs are saved in
MODULE_CROP = ((-20, 0, -25), (20, 62, 32))
T_MAX = 6.0          # s after release
REST_SPEED = 3.0     # mm/s
REST_TIME = 0.3      # s below REST_SPEED = at rest
OUT = ROOT / "results" / "v7_drop"
CHUTE_DIR = MOD_DIR / os.environ.get("CHUTE_DIR", "chute")
CHUTE_PARTS = ["chute", "bracket_right", "bracket_left", "bracket_front"]
USE_CUP = os.environ.get("V7_CUP", "1") == "1"   # with --chute: the pill cup in the tray (weighed)
USE_CHUTE = False    # --chute: the replacement chute (cad/variants/v2_v7_module/chute.py) instead of the V7 funnel


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


M = _load("v7_build_for_drop", MOD_DIR / "build.py")
b = M.b


def export_v7_parts():
    """Write the V7 parts used here as STLs (enclosure frame), once."""
    V7_CACHE.mkdir(parents=True, exist_ok=True)
    if all((V7_CACHE / f"{n}.stl").exists() for n in V7_PARTS):
        return
    import cadquery as cq
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    doc = TDocStd_Document(TCollection_ExtendedString("d"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.ReadFile(str(V7_STEP))
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labs, ch = TDF_LabelSequence(), TDF_LabelSequence()
    st.GetFreeShapes(labs)
    st.GetComponents_s(labs.Value(1), ch)
    for i in range(1, ch.Length() + 1):
        a = TDataStd_Name()
        n = a.Get().ToExtString() if ch.Value(i).FindAttribute(TDataStd_Name.GetID_s(), a) else "?"
        n = n.split(" <")[0]
        if n in V7_PARTS:
            cq.exporters.export(cq.Shape.cast(st.GetShape_s(ch.Value(i))), str(V7_CACHE / f"{n}.stl"),
                                tolerance=0.05, angularTolerance=0.1)


# ------------------------------------------------------------------ frames
def world_to_module(p):
    """V2 world frame (the module's sim STLs) → module frame (see build.to_module)."""
    p = np.asarray(p, float)
    return np.stack([-p[..., 0], -p[..., 1] + M.Y0, p[..., 2] + M.Z0], -1)


def module_to_enclosure(p, k):
    a = math.radians(M.MOD_ANGLES[k] - 90)
    c, s = math.cos(a), math.sin(a)
    p = np.asarray(p, float) + np.array([0, M.MOD_R, 0])
    return np.stack([c * p[..., 0] - s * p[..., 1], s * p[..., 0] + c * p[..., 1], p[..., 2]], -1)


def world_rot_to_enclosure(k):
    """Rotation matrix of the V2 world → enclosure map for module k."""
    a = math.radians(M.MOD_ANGLES[k] - 90)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    return rz @ np.diag([-1.0, -1.0, 1.0])


def local_to_world(p):
    """Local disc frame → V2 world (rotation by BETA about x)."""
    cb, sb = math.cos(math.radians(b.BETA)), math.sin(math.radians(b.BETA))
    p = np.asarray(p, float)
    return np.stack([p[..., 0], cb * p[..., 1] - sb * p[..., 2], sb * p[..., 1] + cb * p[..., 2]], -1)


# ------------------------------------------------------------------ scene
def _pieces_xml(prefix, pieces, transform, assets, mu, rgba):
    out = []
    for i, pc in enumerate(pieces):
        ext = pc.vertices.max(0) - pc.vertices.min(0)
        if ext.min() < 0.05:      # flat sliver left by a crop plane: no volume, nothing to hit
            continue
        v = transform(pc.vertices)
        name = f"{prefix}__{i}"
        assets.append(E._mesh_xml(name, v).replace("<mesh ", '<mesh inertia="shell" ', 1))
        out.append(f'<geom name="{name}" type="mesh" mesh="{name}" rgba="{rgba}" contype="0" '
                   f'conaffinity="1" priority="1" friction="{mu} 0.005 0.0001" group="1"/>')
    return out


def scene_pieces(kit):
    """[(prefix, pieces, transform)] for every static part, cached per kit."""
    export_v7_parts()
    out = []
    for n, (tol, cell, crop) in V7_PARTS.items():
        if USE_CHUTE and n == "Funnel":
            continue
        out.append((n, decompose_file(V7_CACHE / f"{n}.stl", tol=tol, min_cell=cell, crop=crop),
                    lambda v: v))
    if USE_CHUTE:
        for n in CHUTE_PARTS:
            out.append((f"Chute_{n}", decompose_file(CHUTE_DIR / f"{n}.stl", tol=0.1, min_cell=1.0), lambda v: v))
        if USE_CUP:   # named Weighing_*: it sits on the tray and counts as the station
            out.append(("Weighing_cup", decompose_file(CHUTE_DIR / "pill_cup.stl", tol=0.1, min_cell=1.0),
                        lambda v: v))
    d = MOD_DIR / kit
    if not (d / "sim_backplate.stl").exists():
        M.build(kit)
    # the disc is the V2 one (same STL the module campaign simulates), stopped with a pocket
    # over the exit (index angle 0)
    parts = [("disc", ROOT / "cad" / "variants" / "v2_inclined_disc" / kit / "disc.stl", 0.05),
             ("backplate", d / "sim_backplate.stl", 0.1), ("hopper", d / "sim_hopper.stl", 0.1)]
    for name, stl, tol in parts:
        pcs = decompose_file(stl, tol=tol, min_cell=0.4, crop=MODULE_CROP)
        for k in range(6):
            out.append((f"m{k + 1}_{name}", pcs,
                        (lambda kk: (lambda v: module_to_enclosure(world_to_module(v), kk)))(k)))
    return out


def build(kit, pill, mu_part, mu_pill):
    return build_multi(kit, [pill], mu_part, mu_pill, names=["pill"])


def build_multi(kit, pills, mu_part, mu_pill, names=None):
    names = names or [f"pill{i}" for i in range(len(pills))]
    assets, geoms = [], []
    for prefix, pcs, tf in scene_pieces(kit):
        rgba = "0.6 0.6 0.65 1" if not prefix.startswith("m") else "0.9 0.7 0.3 1"
        geoms += _pieces_xml(prefix, pcs, lambda v: tf(v), assets, mu_part, rgba)
    bodies = []
    for i, (nm, pl) in enumerate(zip(names, pills)):
        assets.append(E._mesh_xml(f"pillmesh{i}", np.asarray(pl.mesh(16).vertices)))
        bodies.append(f'''<body name="{nm}" pos="{0.4 + 0.03 * i} 0 0.3"><freejoint name="{nm}"/>
      <geom name="{nm}" type="mesh" mesh="pillmesh{i}" mass="{pl.mass_g / 1000:.6g}" contype="1"
            conaffinity="1" friction="{mu_pill} 0.005 0.0001" condim="4" rgba="0.75 0.2 0.15 1"/>
    </body>''')
    xml = f"""<mujoco model="v7_drop">
  <compiler angle="degree" autolimits="true"/>
  <option timestep="{E.TIMESTEP}" integrator="implicitfast" cone="elliptic" impratio="2"
          gravity="0 0 -{E.GRAVITY}"/>
  <default><geom solref="{E.CONTACT_TIMECONST} 1" solimp="0.95 0.99 0.0002" margin="0.00005"/></default>
  <asset>{"".join(assets)}</asset>
  <worldbody>
    {"".join(geoms)}
    {"".join(bodies)}
  </worldbody>
</mujoco>"""
    return mujoco.MjModel.from_xml_string(xml)


def _quat_from_matrix(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, float).reshape(-1))
    return q


# ------------------------------------------------------------------ trial
def run(kit, seed, record=False):
    rng = np.random.default_rng(seed)
    k = int(rng.integers(0, 6))
    pill = PILLS[kit].sample(rng)
    mu_part, mu_pill = rng.uniform(0.2, 0.6), rng.uniform(0.2, 0.6)
    tilt, spin, az = rng.uniform(0, 20), rng.uniform(0, 360), rng.uniform(0, 360)
    v_tan = rng.uniform(0, 65)
    model = build(kit, pill, mu_part, mu_pill)
    data = mujoco.MjData(model)

    pos, R_p, v = release_state(kit, k, pill, tilt, spin, az, v_tan)
    jq = model.jnt_qposadr[model.joint("pill").id]
    jd = model.jnt_dofadr[model.joint("pill").id]
    data.qpos[jq:jq + 3] = pos * E.MM
    data.qpos[jq + 3:jq + 7] = _quat_from_matrix(R_p)
    data.qvel[jd:jd + 3] = v * E.MM
    mujoco.mj_forward(model, data)
    return _follow(model, data, kit, seed, k, pill, mu_part, mu_pill, tilt, v_tan, record)


def release_state(kit, k, pill, tilt, spin, az, v_tan):
    """Pill seated in the pocket over module k's exit, disc stopped: (pos mm, R, v mm/s),
    enclosure frame."""
    # pocket over the exit: local disc frame, pocket centre at the exit angle; the pill sits on
    # the back plate (disc back face − RUN), lifted 0.2 mm
    pp = b.pocket_params(kit)
    ang = math.radians(pp.get("exit_angle", 90.0))
    c_loc = np.array([pp["r_center"] * math.cos(ang), pp["r_center"] * math.sin(ang),
                      -pp["depth"] - b.RUN + pill.thickness / 2 + 0.2])
    R_w = world_rot_to_enclosure(k)
    cb, sb = math.cos(math.radians(b.BETA)), math.sin(math.radians(b.BETA))
    R_lw = np.array([[1, 0, 0], [0, cb, -sb], [0, sb, cb]])
    R_le = R_w @ R_lw                                   # local disc frame → enclosure
    pos = module_to_enclosure(world_to_module(local_to_world(c_loc)), k)
    # orientation: pill thickness axis along the disc axis, tilted and spun
    def rot(axis, deg):
        return trimesh.transformations.rotation_matrix(math.radians(deg), axis)[:3, :3]
    R_p = R_le @ rot([0, 0, 1], az) @ rot([1, 0, 0], tilt) @ rot([0, 0, 1], spin)
    # pocket velocity: the disc turns about local +z (drive dir=1), tangent at the exit angle
    v_loc = np.array([-math.sin(ang), math.cos(ang), 0.0]) * v_tan
    v = R_le @ v_loc
    return pos, R_p, v


def _follow(model, data, kit, seed, k, pill, mu_part, mu_pill, tilt, v_tan, record):
    jd = model.jnt_dofadr[model.joint("pill").id]
    pid = model.body("pill").id
    rest_since, t_land, frames = None, None, [] if record else None
    outcome, where, max_pen = "moving", None, 0.0
    station_geoms = {i for i in range(model.ngeom)
                     if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or "").startswith("Weighing")}
    next_frame = 0.0
    while data.time < T_MAX:
        mujoco.mj_step(model, data)
        if not np.isfinite(data.qpos).all():
            outcome = "unstable"
            break
        p = data.xpos[pid] / E.MM
        if frames is not None and data.time >= next_frame:
            frames.append([round(data.time, 4)] + [round(x, 3) for x in p]
                          + [round(x, 4) for x in data.xquat[pid]])
            next_frame += 1 / 60
        if p[2] < -170 or abs(p[0]) > 130 or abs(p[1]) > 180:
            outcome = "escaped"
            break
        touching = set()
        for c in data.contact[:data.ncon]:
            g = c.geom2 if model.geom_bodyid[c.geom1] == pid else c.geom1
            touching.add(g)
            max_pen = max(max_pen, -c.dist / E.MM)
        if t_land is None and touching & station_geoms:
            t_land = data.time
        speed = np.linalg.norm(data.qvel[jd:jd + 3]) / E.MM
        if speed < REST_SPEED and data.time > 0.2:
            rest_since = data.time if rest_since is None else rest_since
            if data.time - rest_since >= REST_TIME:
                names = sorted({(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or "?").split("__")[0]
                                for g in touching})
                if touching & station_geoms:
                    outcome = "ok"
                else:
                    outcome, where = "stuck", ", ".join(names) or "nothing"
                break
        else:
            rest_since = None
    res = dict(kit=kit, seed=seed, module=k + 1, mu_part=round(mu_part, 3), mu_pill=round(mu_pill, 3),
               tilt=round(tilt, 1), v_tan=round(v_tan, 1), outcome=outcome, where=where,
               t_land=None if t_land is None else round(t_land, 3), t_end=round(data.time, 3),
               rest_pos=[round(float(x), 1) for x in data.xpos[pid] / E.MM],
               max_pen_mm=round(max_pen, 3))
    if record:
        res["frames"] = frames
    return res


DOSE_GAP_MAX = 4.0    # s allowed per pill before the next is released anyway


def run_dose(kit, seed, n):
    """n pills, one after another, each from a random module, the next released when the last
    is at rest (as the firmware dispenses a dose). Passes when every pill ends at rest on the
    station or on other pills, and no pill touches anything but the station and other pills:
    a pill leaning on the chute would take weight off the load cell."""
    rng = np.random.default_rng(seed)
    mu_part, mu_pill = rng.uniform(0.2, 0.6), rng.uniform(0.2, 0.6)
    draws = []
    for _ in range(n):
        draws.append(dict(k=int(rng.integers(0, 6)), pill=PILLS[kit].sample(rng), tilt=rng.uniform(0, 20),
                          spin=rng.uniform(0, 360), az=rng.uniform(0, 360), v_tan=rng.uniform(0, 65)))
    model = build_multi(kit, [d["pill"] for d in draws], mu_part, mu_pill)
    data = mujoco.MjData(model)
    jq = [model.jnt_qposadr[model.joint(f"pill{i}").id] for i in range(n)]
    jd = [model.jnt_dofadr[model.joint(f"pill{i}").id] for i in range(n)]
    pid = [model.body(f"pill{i}").id for i in range(n)]
    station = {i for i in range(model.ngeom)
               if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or "").startswith("Weighing")}
    pill_geoms = {model.body_geomadr[b_] for b_ in pid}

    def park(i):
        data.qpos[jq[i]:jq[i] + 3] = [0.4 + 0.03 * i, 0, 0.3]
        data.qpos[jq[i] + 3:jq[i] + 7] = [1, 0, 0, 0]
        data.qvel[jd[i]:jd[i] + 6] = 0

    for i in range(n):
        park(i)
    released = []
    outcome, where = "ok", None
    for i, d in enumerate(draws):
        pos, R_p, v = release_state(kit, d["k"], d["pill"], d["tilt"], d["spin"], d["az"], d["v_tan"])
        data.qpos[jq[i]:jq[i] + 3] = pos * E.MM
        data.qpos[jq[i] + 3:jq[i] + 7] = _quat_from_matrix(R_p)
        data.qvel[jd[i]:jd[i] + 6] = 0
        data.qvel[jd[i]:jd[i] + 3] = v * E.MM
        released.append(i)
        t0, rest_since = data.time, None
        while data.time - t0 < DOSE_GAP_MAX:
            for j in range(i + 1, n):
                park(j)
            mujoco.mj_step(model, data)
            if not np.isfinite(data.qpos).all():
                return dict(kit=kit, seed=seed, n=n, outcome="unstable", where=None)
            sp = max(np.linalg.norm(data.qvel[jd[j]:jd[j] + 3]) / E.MM for j in released)
            if sp < REST_SPEED and data.time - t0 > 0.2:
                rest_since = rest_since if rest_since is not None else data.time
                if data.time - rest_since >= REST_TIME:
                    break
            else:
                rest_since = None
        for j in released:
            p = data.xpos[pid[j]] / E.MM
            if p[2] < -170 or abs(p[0]) > 130 or abs(p[1]) > 180:
                return dict(kit=kit, seed=seed, n=n, outcome="escaped", where=f"pill {j + 1}",
                            modules=[d_["k"] + 1 for d_ in draws])
    mujoco.mj_forward(model, data)
    bad = set()
    for c in data.contact[:data.ncon]:
        for a_, b2 in ((c.geom1, c.geom2), (c.geom2, c.geom1)):
            if model.geom_bodyid[a_] in pid and b2 not in station and b2 not in pill_geoms:
                bad.add((mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, b2) or "?").split("__")[0])
    moving = max(np.linalg.norm(data.qvel[jd[j]:jd[j] + 3]) / E.MM for j in range(n)) >= REST_SPEED
    if bad:
        outcome, where = "touching", ", ".join(sorted(bad))
    elif moving:
        outcome = "moving"
    return dict(kit=kit, seed=seed, n=n, outcome=outcome, where=where, mu_part=round(mu_part, 3),
                mu_pill=round(mu_pill, 3), modules=[d["k"] + 1 for d in draws],
                rest_pos=[[round(float(x), 1) for x in data.xpos[b_] / E.MM] for b_ in pid],
                t_end=round(data.time, 3))


def _one(a):
    t = time.time()
    try:
        r = run_dose(*a) if len(a) == 3 else run(*a)
    except Exception as e:     # report, don't hide
        r = dict(kit=a[0], seed=a[1], outcome="error", where=repr(e))
    r["wall_s"] = round(time.time() - t, 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pills", nargs="+", default=["iron", "small"])
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--chute", action="store_true", help="replacement chute instead of the V7 funnel")
    ap.add_argument("--dose", type=int, default=1,
                    help="pills per trial, released one after another (a dose); 1 = single pill")
    a = ap.parse_args()
    global USE_CHUTE, OUT
    if a.chute:
        USE_CHUTE, OUT = True, OUT.with_name("v7_drop_chute")
    if a.dose > 1:
        OUT = OUT.with_name(OUT.name + f"_dose{a.dose}")
    OUT.mkdir(parents=True, exist_ok=True)
    for kit in a.pills:
        scene_pieces(kit)          # build the decomposition cache once, before forking
        jobs = [(kit, a.seed0 + i) + ((a.dose,) if a.dose > 1 else ()) for i in range(a.trials)]
        res = []
        with mp.get_context("fork").Pool(a.workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_one, jobs), 1):
                res.append(r)
                if i % 10 == 0 or i == len(jobs):
                    tally = {}
                    for x in res:
                        tally[x["outcome"]] = tally.get(x["outcome"], 0) + 1
                    print(f"[{OUT.name}/{kit}] {i}/{len(jobs)} {tally}", flush=True)
        res.sort(key=lambda r: r["seed"])
        tally, where = {}, {}
        for x in res:
            tally[x["outcome"]] = tally.get(x["outcome"], 0) + 1
            if x["outcome"] != "ok":
                where[x.get("where") or x["outcome"]] = where.get(x.get("where") or x["outcome"], 0) + 1
        lands = [x["t_land"] for x in res if x.get("t_land") is not None]
        summ = dict(trials=len(res), outcomes=tally, failure_sites=where,
                    t_land_s=dict(median=float(np.median(lands)) if lands else None,
                                  max=float(np.max(lands)) if lands else None),
                    max_pen_mm=max((x.get("max_pen_mm", 0) for x in res), default=0))
        (OUT / f"{kit}.json").write_text(json.dumps(dict(summary=summ, trials=res), indent=1))
        print(f"== {OUT.name}/{kit}: {json.dumps(summ)}", flush=True)


if __name__ == "__main__":
    main()
