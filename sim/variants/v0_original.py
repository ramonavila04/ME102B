"""V0: the team's current design, imported unchanged from the Onshape STEP export."""
from __future__ import annotations

import math
from pathlib import Path

from sim.step_import import export_parts

ROOT = Path(__file__).resolve().parents[2]
STEP = ROOT / "cad" / "onshape" / "Pill_Dispenser_Clip_On_Canister_67p5mm.step.step"
if not STEP.exists():
    STEP = ROOT / "cad" / "onshape" / "Pill_Dispenser_Clip_On_Canister_67p5mm.step"
STL_DIR = ROOT / "sim" / ".cache" / "v0_stl"

# Bristle geometry measured from the 69 REFERENCE_ONLY_Flexible_Bristles bodies:
# roots at (x=3.1, z=0.6), tips at (x=-2.7, z=-7.7), y = ±(4.1 … 30.4), Ø0.4 mm, 0.75 mm pitch.
BRISTLE_ROOT_XZ = (3.1, 0.6)
BRISTLE_TIP_XZ = (-2.7, -7.7)
BRISTLE_LEN = math.dist(BRISTLE_ROOT_XZ, BRISTLE_TIP_XZ)
# Nylon 0.4 mm bristle cantilever: k = 3EI/L^3 with E = 2.5 GPa (ASSUMPTIONS S3).
_I = math.pi * 0.4e-3 ** 4 / 64
_K_TIP = 3 * 2.5e9 * _I / (BRISTLE_LEN * 1e-3) ** 3      # N/m per bristle
FLAP_WIDTH = 5.2                                            # mm of brush per flap
_BRISTLES_PER_FLAP = FLAP_WIDTH / 0.75
FLAP_STIFFNESS = _K_TIP * _BRISTLES_PER_FLAP * (BRISTLE_LEN * 1e-3) ** 2  # N·m/rad


def _parts() -> dict:
    return export_parts(STEP, STL_DIR, skip=lambda n: n.startswith("REFERENCE_ONLY")
                        or n in ("Pill_Dispenser_Clip_On_Canister",))


def site_namer(part: str, pos_mm) -> str:
    x, y, z = pos_mm
    if part.startswith("Lower_enclosure"):
        if x > 3.5:
            return "F1 deck stripping edge (chamfered wedge above rotor, drop side)"
        return "F1 deck edge above rotor (fill-opening rim)"
    if part.startswith("Canister"):
        return "F1 canister rim above rotor"
    if part.startswith("flap"):
        return "F4 brush"
    if part.startswith("Floor") or part.startswith("Stationary_floor"):
        if z < -13.5:
            return "F7 2.35 mm gap under rotor wall (floor liner)"
        return "F6 floor-hole edge"
    if part.startswith("Full_width_brush_holder"):
        return "F3 brush holder bar (pill standing proud of pocket)"
    if part.startswith("Separate_vertical_pill_chute"):
        return "F6 chute entry"
    return part


def spec(pill_id: str) -> dict:
    p = _parts()
    # (name, crop box, hull tolerance mm). Hopper walls only guide pills: 0.25 mm is fine.
    # Everything within a pill height of the rotor keeps 0.05 mm.
    static = [
        ("Canister_OD67p5_H70", None, 0.25),
        ("Lower_enclosure_with_integrated_snap_clips", ((-40, -40, -27), (40, 40, -4)), 0.05),
        ("Lower_enclosure_with_integrated_snap_clips", ((-40, -40, -4), (40, 40, 16)), 0.25),
        ("Stationary_floor", None, 0.05),
        ("Floor_liner_unchanged_depth", None, 0.05),
        ("Separate_vertical_pill_chute", ((-40, -40, -45), (40, 40, 0)), 0.1),
        ("Full_width_brush_holder", None, 0.1),
    ]
    rotor = ["Three_tangential_pocket_rotor", "Unchanged_pill_opening_1",
             "Unchanged_pill_opening_2", "Unchanged_pill_opening_3", "Center_D_drive_shaft"]
    parts = [dict(name=f"{n}" if k == 0 or static[k - 1][0] != n else f"{n}_upper", stl=p[n],
                  body="static", crop=c, tol=t) for k, (n, c, t) in enumerate(static)]
    parts += [dict(name=n, stl=p[n], body="rotor", rgba="0.95 0.75 0.2 1",
                   crop=((-40, -40, -17), (40, 40, 10)) if n == "Center_D_drive_shaft" else None)
              for n in rotor]
    flaps = []
    ys = [4.1 + FLAP_WIDTH * (k + 0.5) for k in range(5)]
    for y in ys + [-v for v in ys]:
        flaps.append(dict(root=(BRISTLE_ROOT_XZ[0], y, BRISTLE_ROOT_XZ[1]),
                          tip=(BRISTLE_TIP_XZ[0], y, BRISTLE_TIP_XZ[1]),
                          axis=(0, 1, 0), width=FLAP_WIDTH, thickness=0.6,
                          stiffness=FLAP_STIFFNESS))
    fills = {"iron": (3, 20), "small": (3, 30), "caplet": (3, 12), "cap0": (3, 12)}

    def accept(x, y, z, r):
        rad = math.hypot(x, y)
        if rad > 30.5 - r:
            return False
        if z < 10 + r and rad < 4 + r:      # drive shaft tip
            return False
        if x > 3 - r and z < 9 + (x - 3) * 0.66 + 2 * r:   # stay above the sloped baffle
            return False
        return True

    return dict(
        name="V0 original (team CAD)",
        parts=parts,
        joint=dict(type="hinge", axis=(0, 0, 1), pos=(0, 0, 0)),
        rotor_mass_kg=0.012,
        # The team ran the motor at full duty (PWMA tied high): ~30 rpm under load.
        drive=dict(index_deg=120.0, rpm=30.0, dir=-1, accel_s=0.15, settle_s=0.6, start_deg=0.0),
        flaps=flaps,
        spawn=dict(x=(-30, 30), y=(-30, 30), z=(6, 66 if pill_id in ('iron', 'small') else 150), accept=accept),
        fill=fills[pill_id],
        exit=dict(z=-28.0, x=(8.0, 21.0), y=(-14.0, 14.0)),
        loss_z=-24.0,     # below the floor (z=-25.1 underside) but outside the chute = fell past the rotor
        fill_s=1.2 if pill_id in ('iron', 'small') else 1.8, settle_s=0.6,
        site_namer=site_namer,
    )
