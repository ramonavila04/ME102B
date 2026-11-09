"""MuJoCo dispense-cycle simulator shared by every variant.

A variant module provides `spec(pill_id) -> dict` (see sim/variants/README.md).
`run_trial(spec_fn, pill_id, seed)` builds the scene with randomised pills and
friction, fills the hopper, runs N dispense cycles with the motor model, and
classifies each cycle as ok / double / miss / jam / lost / leak.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import mujoco
import numpy as np

from sim import pills as pills_mod
from sim.convexify import decompose_file

MM = 1e-3
GRAVITY = 9.81

# Motor: Pololu #5229 1000:1 HPCB 12 V (ASSUMPTIONS M1)
MOTOR_NO_LOAD_RPM = 35.0
MOTOR_TORQUE_LIMIT = 1.0     # N·m, gearbox recommended maximum (10 kg·cm)
MOTOR_REFLECTED_J = 0.003    # kg·m², ~3e-9 kg·m² micro-motor rotor × 986² (ASSUMPTIONS M1)
SERVO_KP = 20.0              # N·m/rad, encoder position loop
SERVO_KD = 0.9               # N·m·s/rad

TIMESTEP = 0.000125
CONTACT_TIMECONST = 0.0005   # s; ≥ 4 steps for stability, gives ~0.1 mm penetration at 0.1 m/s
FILL_DAMPING = 60.0         # 1/s, applied to pills only while the hopper is being filled
JAM_SPEED_FRAC = 0.10
JAM_TIME = 0.30
JAM_SAT_TIME = 0.15       # s at the torque limit = the real motor would stall
JAM_LAG_DEG = 10.0        # encoder position error that means a stall
PINCH_DEPTH_MM = 0.25     # overlap with BOTH a rotor part and a fixed part, pressing from opposite sides
PINCH_TIME = 0.010        # s the squeeze must last (a rigid pill that could escape would have)


@dataclass
class CycleResult:
    outcome: str
    count: int
    duration_s: float
    jam_site: str | None = None
    jam_pos_mm: list | None = None
    lost: int = 0


@dataclass
class TrialResult:
    variant: str
    pill: str
    seed: int
    fill: int
    mu_part: float
    mu_pill: float
    cycles: list = field(default_factory=list)
    leak: int = 0
    wall_s: float = 0.0
    max_contact_depth_mm: float = 0.0  # deepest pill contact seen (mm); large values flag soft-contact artefacts
    frames: list | None = None

    @property
    def passed(self) -> bool:
        return self.leak == 0 and all(c.outcome == "ok" for c in self.cycles)


# ---------------------------------------------------------------- scene build
def _mesh_xml(name: str, verts_mm: np.ndarray) -> str:
    v = " ".join(f"{x * MM:.7g}" for x in verts_mm.reshape(-1))
    return f'<mesh name="{name}" vertex="{v}"/>'


def _part_geoms(part: dict, assets: list, rgba: str, mu: float) -> str:
    pieces = decompose_file(part["stl"], tol=part.get("tol", 0.05),
                            min_cell=part.get("min_cell", 0.8), crop=part.get("crop"))
    out = []
    for i, p in enumerate(pieces):
        mname = f"{part['name']}__{i}"
        assets.append(_mesh_xml(mname, p.vertices))
        out.append(f'<geom name="{mname}" type="mesh" mesh="{mname}" rgba="{rgba}" '
                   f'contype="0" conaffinity="1" priority="1" friction="{mu} 0.005 0.0001" '
                   f'group="{1 if part["body"] == "static" else 2}"/>')
    return "\n".join(out)


def build_model(spec: dict, pill_samples: list, mu_part: float, mu_pill: float):
    assets: list[str] = []
    static_xml, rotor_xml = [], []
    for part in spec["parts"]:
        g = _part_geoms(part, assets, part.get("rgba", "0.8 0.8 0.85 1"), mu_part)
        (static_xml if part["body"] == "static" else rotor_xml).append(g)

    j = spec["joint"]
    if j["type"] == "hinge":
        joint = (f'<joint name="drive" type="hinge" axis="{" ".join(map(str, j["axis"]))}" '
                 f'pos="{" ".join(str(x * MM) for x in j["pos"])}" armature="{MOTOR_REFLECTED_J}" '
                 f'damping="0.001"/>')
    else:  # slide driven through a crank of radius crank_r (scotch yoke)
        r = j["crank_r"] * MM
        joint = (f'<joint name="drive" type="slide" axis="{" ".join(map(str, j["axis"]))}" '
                 f'armature="{MOTOR_REFLECTED_J / r ** 2:.6g}" damping="0.01"/>')
    rotor_mass = spec.get("rotor_mass_kg", 0.02)

    flaps_xml = []
    for k, f in enumerate(spec.get("flaps", [])):
        root, tip = np.array(f["root"]) * MM, np.array(f["tip"]) * MM
        half_w = f["width"] / 2 * MM
        flaps_xml.append(
            f'<body name="flap{k}" pos="{root[0]:.6g} {root[1]:.6g} {root[2]:.6g}">'
            f'<joint name="flap{k}" type="hinge" axis="{" ".join(map(str, f["axis"]))}" '
            f'stiffness="{f["stiffness"]}" damping="{f.get("damping", 1e-4)}" armature="{f.get("armature", 2e-7)}" '
            f'limited="false"/>'
            f'<geom name="flap{k}" type="capsule" fromto="0 -{half_w:.6g} 0 0 {half_w:.6g} 0" '
            f'size="{f["thickness"] / 2 * MM:.6g}" contype="0" conaffinity="1" priority="1" '
            f'friction="{mu_part} 0.005 0.0001" rgba="0.2 0.2 0.2 1" mass="0.0002"/>'
            f'<geom name="flap{k}_blade" type="box" pos="{(tip - root)[0] / 2:.6g} 0 {(tip - root)[2] / 2:.6g}" '
            f'size="{f["thickness"] / 2 * MM:.6g} {half_w:.6g} {np.linalg.norm(tip - root) / 2:.6g}" '
            f'euler="0 {math.degrees(math.atan2((tip - root)[0], (tip - root)[2])):.4f} 0" '
            f'contype="0" conaffinity="1" priority="1" friction="{mu_part} 0.005 0.0001" '
            f'rgba="0.2 0.2 0.2 1" mass="0.0002"/>'
            f'</body>')

    pill_xml = []
    for i, p in enumerate(pill_samples):
        if p.kind == "capsule":
            geom = (f'<geom name="pill{i}" type="capsule" size="{p.width / 2 * MM:.6g}" '
                    f'fromto="{-(p.length - p.width) / 2 * MM:.6g} 0 0 {(p.length - p.width) / 2 * MM:.6g} 0 0"')
        else:
            mname = f"pillmesh{i}"
            assets.append(_mesh_xml(mname, np.asarray(p.mesh(16).vertices)))
            geom = f'<geom name="pill{i}" type="mesh" mesh="{mname}"'
        pill_xml.append(
            f'<body name="pill{i}" pos="{2 + i * 0.05} 0 0"><freejoint name="pill{i}"/>'
            f'{geom} mass="{p.mass_g / 1000:.6g}" contype="1" conaffinity="1" '
            f'friction="{mu_pill} 0.005 0.0001" condim="4" rgba="0.75 0.2 0.15 1"/></body>')

    xml = f"""<mujoco model="{spec['name']}">
  <compiler angle="degree" autolimits="true"/>
  <option timestep="{TIMESTEP}" integrator="implicitfast" cone="elliptic" impratio="2"
          gravity="0 0 -{GRAVITY}"/>
  <default><geom solref="{CONTACT_TIMECONST} 1" solimp="0.95 0.99 0.0002" margin="0.00005"/></default>
  <asset>{"".join(assets)}</asset>
  <worldbody>
    {"".join(static_xml)}
    {"".join(flaps_xml)}
    <body name="rotor">
      {joint}
      <inertial pos="0 0 0" mass="{rotor_mass}" diaginertia="1e-5 1e-5 1e-5"/>
      {"".join(rotor_xml)}
    </body>
    {"".join(pill_xml)}
  </worldbody>
  <actuator><motor name="drive" joint="drive" ctrllimited="false"/></actuator>
</mujoco>"""
    return mujoco.MjModel.from_xml_string(xml)


# --------------------------------------------------------------- drive model
class Drive:
    """Trapezoidal index move tracked by a PD loop with the motor's torque–speed line."""

    def __init__(self, spec: dict, model):
        d = spec["drive"]
        self.index = math.radians(d["index_deg"]) * d.get("dir", 1)
        self.w_max = d["rpm"] * 2 * math.pi / 60
        self.t_acc = d.get("accel_s", 0.15)
        self.slide = spec["joint"]["type"] == "slide"
        self.r = spec["joint"].get("crank_r", 1.0) * MM
        self.theta0 = math.radians(d.get("start_deg", 0.0))
        self.target = self.theta0
        self.move_start = None
        self.move_from = self.theta0
        self.theta_hold = self.theta0

    def move_time(self) -> float:
        a = abs(self.index)
        acc_ang = self.w_max * self.t_acc
        if a <= acc_ang:
            return 2 * math.sqrt(a * self.t_acc / self.w_max)
        return a / self.w_max + self.t_acc

    def ref(self, t: float):
        """Reference crank angle and speed at time t."""
        if self.move_start is None:
            return self.theta_hold, 0.0
        tau = t - self.move_start
        a_tot = abs(self.index)
        sgn = math.copysign(1, self.index)
        acc = self.w_max / self.t_acc
        T = self.move_time()
        if a_tot <= self.w_max * self.t_acc:
            v_pk = acc * T / 2
            if tau < T / 2:
                s, v = 0.5 * acc * tau ** 2, acc * tau
            elif tau < T:
                tt = T - tau
                s, v = a_tot - 0.5 * acc * tt ** 2, acc * tt
            else:
                s, v = a_tot, 0.0
        else:
            if tau < self.t_acc:
                s, v = 0.5 * acc * tau ** 2, acc * tau
            elif tau < T - self.t_acc:
                s, v = 0.5 * self.w_max * self.t_acc + self.w_max * (tau - self.t_acc), self.w_max
            elif tau < T:
                tt = T - tau
                s, v = a_tot - 0.5 * acc * tt ** 2, acc * tt
            else:
                s, v = a_tot, 0.0
        return self.move_from + sgn * s, sgn * v

    def start_move(self, t: float):
        self.move_from = self.target
        self.target = self.target + self.index
        self.move_start = t

    def finish(self):
        self.theta_hold = self.target
        self.move_start = None

    # crank angle <-> joint coordinate
    def to_joint(self, theta: float) -> float:
        return self.r * math.sin(theta) if self.slide else theta

    def crank_state(self, q: float, qd: float, theta_guess: float):
        if not self.slide:
            return q, qd
        # pick the crank angle branch nearest the reference
        s = max(-1.0, min(1.0, q / self.r))
        base = math.asin(s)
        cands = [base + 2 * math.pi * k for k in range(-3, 4)] + \
                [math.pi - base + 2 * math.pi * k for k in range(-3, 4)]
        theta = min(cands, key=lambda c: abs(c - theta_guess))
        c = math.cos(theta)
        w = qd / (self.r * c) if abs(c) > 0.15 else qd / (self.r * math.copysign(0.15, c))
        return theta, w

    def control(self, t: float, q: float, qd: float) -> tuple[float, float, float]:
        th_ref, w_ref = self.ref(t)
        theta, w = self.crank_state(q, qd, th_ref)
        tau = SERVO_KP * (th_ref - theta) + SERVO_KD * (w_ref - w)
        w0 = MOTOR_NO_LOAD_RPM * 2 * math.pi / 60
        hi = MOTOR_TORQUE_LIMIT * min(1.0, max(0.0, 1 - w / w0) * 2.0)
        lo = -MOTOR_TORQUE_LIMIT * min(1.0, max(0.0, 1 + w / w0) * 2.0)
        self.saturated = tau >= hi * 0.98 or tau <= lo * 0.98
        self.lag = abs(th_ref - theta)
        tau = max(lo, min(hi, tau))
        if not self.slide:
            return tau, theta, w
        c = math.cos(theta)
        lever = max(abs(c), 0.05) * self.r  # force = torque / (r cos θ)
        return tau / lever * math.copysign(1, c), theta, w


# ------------------------------------------------------------------ the trial
def _rand_quat(rng):
    u = rng.normal(size=4)
    return u / np.linalg.norm(u)


def _spawn(spec, model, data, pill_samples, n, rng):
    """Place n pills without overlap inside the spawn region; park the rest."""
    region = spec["spawn"]
    placed = []
    for i in range(len(pill_samples)):
        adr = model.jnt_qposadr[model.joint(f"pill{i}").id]
        if i >= n:
            data.qpos[adr:adr + 3] = [5 + i * 0.05, 5, 5]
            continue
        r = pill_samples[i].bounding_radius
        for _ in range(4000):
            x = rng.uniform(*region["x"]); y = rng.uniform(*region["y"]); z = rng.uniform(*region["z"])
            if "accept" in region and not region["accept"](x, y, z, r):
                continue
            if all(np.linalg.norm(np.array([x, y, z]) - c) > r + rc + 0.3 for c, rc in placed):
                break
        else:
            raise RuntimeError("could not place pills in the spawn region; enlarge it")
        placed.append((np.array([x, y, z]), r))
        data.qpos[adr:adr + 3] = np.array([x, y, z]) * MM
        data.qpos[adr + 3:adr + 7] = _rand_quat(rng)


def _jam_site(spec, model, data, pill_body_ids, rotor_body):
    """Name the stationary geometry a pill is pinched against when the drive stalls."""
    best = (0.0, None, None)
    f6 = np.zeros(6)
    pill_on_rotor = set()
    for c in data.contact[:data.ncon]:
        b1, b2 = model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]
        if rotor_body in (b1, b2) and (b1 in pill_body_ids or b2 in pill_body_ids):
            pill_on_rotor.add(b1 if b1 in pill_body_ids else b2)
    for k, c in enumerate(data.contact[:data.ncon]):
        b1, b2 = model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]
        pb = b1 if b1 in pill_body_ids else (b2 if b2 in pill_body_ids else None)
        if pb is None or pb not in pill_on_rotor:
            continue
        other_geom = c.geom2 if pb == b1 else c.geom1
        if model.geom_bodyid[other_geom] in (rotor_body,) or model.geom_bodyid[other_geom] in pill_body_ids:
            continue
        mujoco.mj_contactForce(model, data, k, f6)
        if f6[0] > best[0]:
            gname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, other_geom) or "?"
            best = (f6[0], gname.split("__")[0], data.xpos[pb] / MM)
    if best[1] is None:
        # pill trapped between rotor and another pill, or drive overload with no pinch
        site = "pill-pile (pill wedged between rotor and other pills)" if pill_on_rotor else "drive overload"
        pos = data.xpos[next(iter(pill_on_rotor))] / MM if pill_on_rotor else None
        return site, pos
    namer = spec.get("site_namer")
    return (namer(best[1], best[2]) if namer else best[1]), best[2]


def run_trial(spec_fn, pill_id: str, seed: int, cycles: int = 3, record: bool = False,
              fill: int | None = None, debug: list | None = None) -> TrialResult:
    t_wall = time.time()
    rng = np.random.default_rng(seed)
    spec = spec_fn(pill_id)
    base = pills_mod.PILLS[pill_id]
    n_max = spec["fill"][1]
    n = fill if fill is not None else int(rng.integers(spec["fill"][0], n_max + 1))
    samples = [base.sample(rng) for _ in range(n_max)]
    mu_part, mu_pill = rng.uniform(0.2, 0.6), rng.uniform(0.2, 0.6)
    spec["drive"] = dict(spec["drive"])
    spec["drive"]["start_deg"] = spec["drive"].get("start_deg", 0.0) + rng.uniform(-2.0, 2.0)

    model = build_model(spec, samples, mu_part, mu_pill)
    data = mujoco.MjData(model)
    drive = Drive(spec, model)
    jid = model.joint("drive").id
    qadr, dadr = model.jnt_qposadr[jid], model.jnt_dofadr[jid]
    data.qpos[qadr] = drive.to_joint(drive.theta0)
    _spawn(spec, model, data, samples, n, rng)
    mujoco.mj_forward(model, data)

    res = TrialResult(spec["name"], pill_id, seed, n, float(mu_part), float(mu_pill))
    pill_bodies = [model.body(f"pill{i}").id for i in range(n_max)]
    pill_set = set(pill_bodies[:n])
    rotor_body = model.body("rotor").id
    pill_qadr = [model.jnt_qposadr[model.joint(f"pill{i}").id] for i in range(n_max)]
    gone = set(range(n, n_max))
    ex = spec["exit"]
    frames = [] if record else None
    frame_dt, next_frame = 1 / 60, 0.0

    def park(i):
        a = pill_qadr[i]
        data.qpos[a:a + 3] = [5 + i * 0.05, -5, 5]
        data.qvel[model.jnt_dofadr[model.joint(f"pill{i}").id]:][:6] = 0
        gone.add(i)

    pen_stats = {"max_free": 0.0}
    flap_bodies = {model.body(f"flap{k}").id for k in range(len(spec.get("flaps", [])))}

    pinch_since: dict = {}

    def pinch():
        """Rotor squeezing a pill, or a chain of up to 3 touching pills, against fixed geometry.

        A squeeze is: every contact along the chain overlaps more than PINCH_DEPTH_MM and the
        rotor's push on the first pill opposes the fixed part's push on the last (dot < -0.3).
        It is a jam once it persists PINCH_TIME. Brush flaps never count as fixed: a bristle
        buckles long before it can clamp a pill. Returns (pill_body, fixed_geom) or None.
        """
        rot, fix, edges = {}, {}, {}
        for c in data.contact[:data.ncon]:
            depth = -c.dist / MM
            b1, b2 = model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]
            if depth > pen_stats["max_free"] and (b1 in pill_set or b2 in pill_set):
                pen_stats["max_free"] = depth
            if depth <= PINCH_DEPTH_MM:
                continue
            n = np.array(c.frame[:3])
            if b1 in pill_set and b2 in pill_set:
                edges.setdefault(b1, set()).add(b2); edges.setdefault(b2, set()).add(b1)
                continue
            for pb, other_g, other_b, sgn in ((b2, c.geom1, b1, 1.0), (b1, c.geom2, b2, -1.0)):
                if pb not in pill_set or other_b in pill_set or other_b in flap_bodies:
                    continue
                if other_b == rotor_body:
                    rot.setdefault(pb, []).append(sgn * n)
                else:
                    fix.setdefault(pb, []).append((sgn * n, other_g))
        found = {}
        for p0, nrs in rot.items():
            seen, frontier = {p0}, [p0]
            for _ in range(3):
                for q in list(frontier):
                    for nb in edges.get(q, ()):
                        if nb not in seen:
                            seen.add(nb); frontier.append(nb)
            for q in seen:
                for nf, g in fix.get(q, ()):
                    if any(float(nr @ nf) < -0.3 for nr in nrs):
                        found[(p0, q)] = (q, g)
        now = data.time
        for key in list(pinch_since):
            if key not in found:
                del pinch_since[key]
        for key, val in found.items():
            if now - pinch_since.setdefault(key, now) >= PINCH_TIME:
                return val
        return None

    def scan():
        counted, lost = 0, 0
        for i in range(n):
            if i in gone:
                continue
            x, y, z = data.xpos[pill_bodies[i]] / MM
            if debug is not None:
                v = float(np.linalg.norm(data.cvel[pill_bodies[i]][3:]))
                if v > 2.5 and len(debug) < 20:
                    cs = []
                    for c in data.contact[:data.ncon]:
                        b1, b2 = model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]
                        if pill_bodies[i] in (b1, b2):
                            g = c.geom2 if b1 == pill_bodies[i] else c.geom1
                            cs.append((mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g), round(c.dist / MM, 2)))
                    debug.append(dict(t=round(data.time, 4), pill=i, v=round(v, 2),
                                      pos=[round(a, 1) for a in (x, y, z)], contacts=cs[:6],
                                      rotor_w=round(float(data.qvel[dadr]), 3), tau=round(float(data.ctrl[0]), 3)))
            inside = ex["x"][0] <= x <= ex["x"][1] and ex["y"][0] <= y <= ex["y"][1]
            if z < ex["z"] and inside:
                counted += 1; park(i)
            elif (z < spec["loss_z"] and not inside) or z < ex["z"] - 40 or abs(x) > 200 or abs(y) > 200:
                lost += 1; park(i)
        return counted, lost

    def frame():
        nonlocal next_frame
        if frames is not None and data.time >= next_frame:
            frames.append([round(data.time, 4), round(float(data.qpos[qadr]), 6),
                           [[round(v, 3) for v in (data.xpos[b] / MM)] +
                            [round(v, 4) for v in data.xquat[b]] if i not in gone else None
                            for i, b in enumerate(pill_bodies[:n])]])
            next_frame += frame_dt

    def step(t_end, moving: bool):
        """Advance to t_end. Returns (counted, lost, jammed)."""
        counted = lost = 0
        slow_since = None
        sat_since = None
        k = 0
        while data.time < t_end:
            tau, theta, w = drive.control(data.time, data.qpos[qadr], data.qvel[dadr])
            data.ctrl[0] = tau
            mujoco.mj_step(model, data)
            k += 1
            if k % 10 == 0:
                c, l = scan(); counted += c; lost += l
                frame()
                if moving and pinch() is not None:
                    return counted, lost, True
                if moving and drive.move_start is not None:
                    if drive.saturated:
                        sat_since = sat_since or data.time
                        if data.time - sat_since >= JAM_SAT_TIME:
                            return counted, lost, True
                    else:
                        sat_since = None
                    if drive.lag > math.radians(JAM_LAG_DEG):
                        return counted, lost, True
                    _, w_ref = drive.ref(data.time)
                    in_cruise = data.time - drive.move_start > drive.t_acc and \
                        data.time < drive.move_start + drive.move_time() - drive.t_acc
                    if in_cruise and abs(w) < JAM_SPEED_FRAC * drive.w_max:
                        slow_since = slow_since or data.time
                        if data.time - slow_since >= JAM_TIME:
                            return counted, lost, True
                    else:
                        slow_since = None
        return counted, lost, False

    # fill: pills fall into the hopper under heavy damping (setup only), then settle undamped
    pill_dofs = [model.jnt_dofadr[model.joint(f"pill{i}").id] for i in range(n)]
    masses = [float(model.body_mass[b]) for b in pill_bodies[:n]]
    fill_s = spec.get("fill_s", 1.2)
    while data.time < fill_s:
        for dof, m_ in zip(pill_dofs, masses):
            data.qfrc_applied[dof:dof + 3] = -FILL_DAMPING * m_ * data.qvel[dof:dof + 3]
            data.qfrc_applied[dof + 3:dof + 6] = -FILL_DAMPING * 1e-9 * data.qvel[dof + 3:dof + 6]
        tau, _, _ = drive.control(data.time, data.qpos[qadr], data.qvel[dadr])
        data.ctrl[0] = tau
        mujoco.mj_step(model, data)
    data.qfrc_applied[:] = 0
    c, l, _ = step(fill_s + spec.get("settle_s", 0.6), moving=False)
    res.leak = c
    lost_fill = l
    for _ in range(cycles):
        t0 = data.time
        drive.start_move(t0)
        T = drive.move_time()
        c1, l1, jam = step(t0 + T, moving=True)
        if not jam:
            # allow up to 3x nominal time for the move to really finish
            err_deadline = t0 + 3 * T
            while abs(drive.crank_state(data.qpos[qadr], data.qvel[dadr], drive.target)[0] - drive.target) > math.radians(3) \
                    and data.time < err_deadline:
                cx, lx, _ = step(data.time + 0.02, moving=False); c1 += cx; l1 += lx
            if abs(drive.crank_state(data.qpos[qadr], data.qvel[dadr], drive.target)[0] - drive.target) > math.radians(3):
                jam = True
        site = pos = None
        if jam:
            pc = pinch()
            if pc is not None:
                gname = (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, pc[1]) or "?").split("__")[0]
                pos = data.xpos[pc[0]] / MM
                namer = spec.get("site_namer")
                site = namer(gname, pos) if namer else gname
            else:
                site, pos = _jam_site(spec, model, data, pill_set, rotor_body)
            res.cycles.append(CycleResult("jam", c1, data.time - t0, site,
                                          None if pos is None else [round(float(v), 2) for v in pos], l1))
            break
        drive.finish()
        c2, l2, _ = step(data.time + spec["drive"].get("settle_s", 0.6), moving=False)
        cnt, lost = c1 + c2, l1 + l2
        if lost:
            out = "lost"
        elif cnt == 1:
            out = "ok"
        elif cnt >= 2:
            out = "double"
        else:
            out = "miss"
        res.cycles.append(CycleResult(out, cnt, data.time - t0, lost=lost))
    if lost_fill:
        res.cycles.insert(0, CycleResult("lost", 0, 0.0, lost=lost_fill))
    res.frames = frames
    res.max_contact_depth_mm = round(pen_stats["max_free"], 3)
    res.wall_s = time.time() - t_wall
    return res
