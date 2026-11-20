"""V7 module with its spur-gear transmission modelled (backlash, mesh stiffness, losses).

Same geometry as `v2_v7_module`; the difference is the drive. There the motor turns the
disc shaft directly (as in the stand-alone V2's coupler drive). Here the encoder and the
servo loop are on the motor shaft, and the disc is driven through the printed 1:1 spur pair
(cad/variants/v2_v7_module/build.py: module 1.5, 14 teeth, 6 mm wide, PLA):

  backlash      3.0° at the disc: 0.55 mm at the 10.5 mm pitch radius. The CAD allows
                0.1 mm per gear (0.2 mm, 1.1°); 3° covers printing error and centre-
                distance error on top of that (worst case, not nominal).
  mesh stiffness 158 N·m/rad: ISO 6336's 14 N/(mm·µm) for steel scaled by E (PLA 3.5 GPa
                / steel 206 GPa), × 6 mm face width, × r² at the pitch radius.
  damping       0.016 N·m·s/rad (damping ratio 0.2 against the disc side).
  efficiency    0.9 for the printed pair.
  rotor inertia the disc body as before plus 3e-7 kg·m² for shaft and gear; the motor's
                reflected inertia now sits on the motor shaft, not on the disc.
"""
import importlib.util
from pathlib import Path

_s = importlib.util.spec_from_file_location("v2_v7_module_base", Path(__file__).with_name("v2_v7_module.py"))
_base = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_base)

GEAR = dict(backlash_deg=3.0, k_mesh=158.0, c_mesh=0.016, efficiency=0.9, rotor_J=3e-7)


def spec(pill_id):
    s = _base.spec(pill_id)
    s["gear"] = dict(GEAR)
    s["name"] = "V2 inclined pocket disc, V7 module, gear drive with 3° backlash"
    return s
