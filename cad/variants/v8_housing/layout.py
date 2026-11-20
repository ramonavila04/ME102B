"""V8 housing: shared layout, frames and the reused V7 / V2 parts.

Enclosure frame = the V7 frame (mm): deck top z = 0, +y to the back, the front panel at −y.
V2 world frame = the stand-alone V2's frame: disc centre at the origin, the drive and exit
duct toward +y and down, the table (top of the V2 base plate) at z = BASE_Z = −78.

Six unmodified V2 modules (coupler drive) stand on pods on the deck in a pinwheel:
module k's exit-duct mouth is at radius RP, angle 60·k, and its drive points PHI degrees off
the inward radial direction. PHI = 50°, RP = 32 mm came from a packing search on the real
module solids (iron and small envelopes together): neighbours stay ≥ 4.5 mm apart, a pill
falling from any mouth misses every other module, and the hopper tops reach 189 mm from the
axis (pointing straight in, the same 3 mm gap needs RP = 35 and 201 mm).
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = ROOT / "sim" / ".cache" / "v7_brep"
V7_STEP = ROOT / "cad" / "onshape" / "V7_Pill_Dispenser_Heat_Inserts.step"

_spec = importlib.util.spec_from_file_location("v2_build", ROOT / "cad" / "variants" / "v2_inclined_disc" / "build.py")
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)

PHI = 50.0            # drive direction, degrees off the inward radial
RP = 32.0             # duct-mouth radius
MOUTH_Y = 95.8        # duct mouth centre, V2 world y (iron; small 94.3)
POD_T = 6.0           # pod plate thickness (the V2 base plate's)
H = POD_T - b.BASE_Z  # V2 world origin above the deck top: pod top = V2 table
N_MOD = 6
CENTRE = (0.0, -15.0)  # centre of the duct-mouth ring: 15 mm toward the front, so the chute's
                       # 37° floor stays under the deck below the rear mouths


def mod_rot_deg(k: int) -> float:
    """Rotation about z taking V2-world +y (drive direction) to module k's drive direction."""
    th = math.radians(60 * k)
    ang = th + math.pi + math.radians(PHI)
    return math.degrees(ang - math.pi / 2)


def mouth_xy(k: int):
    th = math.radians(60 * k)
    return CENTRE[0] + RP * math.cos(th), CENTRE[1] + RP * math.sin(th)


def rotate_k(shape, k: int):
    """Module 0's copy of a part → module k's (60° steps about the ring centre)."""
    c = (CENTRE[0], CENTRE[1], 0)
    return shape.rotate(c, (c[0], c[1], 1), 60 * k)


def to_enc(shape, k: int):
    """V2 world → enclosure frame for module k (Workplane or Shape)."""
    mx, my = mouth_xy(k)
    return (shape.translate((0, -MOUTH_Y, 0)).rotate((0, 0, 0), (0, 0, 1), mod_rot_deg(k))
            .translate((mx, my, H)))


def pt_enc(p, k: int):
    x, y, z = p[0], p[1] - MOUTH_Y, p[2]
    a = math.radians(mod_rot_deg(k))
    mx, my = mouth_xy(k)
    return (x * math.cos(a) - y * math.sin(a) + mx, x * math.sin(a) + y * math.cos(a) + my, z + H)


# ----------------------------------------------------------------- V7 parts (reused unchanged)
V7_NAMES = {"Enclosure": "Enclosure", "Funnel_mounts": "Funnel_mounts", "Weighing_station": "Weighing_station",
            "Front_panel_controls": "Front_panel_controls", "Station_fasteners": "Station_fasteners"}


def _read_v7():
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.ReadFile(str(V7_STEP))
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labs = TDF_LabelSequence()
    st.GetFreeShapes(labs)
    ch = TDF_LabelSequence()
    st.GetComponents_s(labs.Value(1), ch)
    out = {}
    for i in range(1, ch.Length() + 1):
        a = TDataStd_Name()
        n = a.Get().ToExtString() if ch.Value(i).FindAttribute(TDataStd_Name.GetID_s(), a) else "?"
        n = n.split(" <")[0]
        if n in V7_NAMES:
            out[n] = cq.Shape.cast(st.GetShape_s(ch.Value(i)))
    return out


def v7(name: str) -> cq.Shape:
    """A V7 part as one shape (cached as BREP after the first read of the 12 MB STEP)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.brep"
    if not f.exists():
        for n, s in _read_v7().items():
            s.exportBrep(str(CACHE / f"{n}.brep"))
    return cq.Shape.importBrep(str(f))


def v7_kept_fasteners():
    """The V7 "Station_fasteners" are the screws and inserts of the old modules and of the
    deck; only the six deck-to-shell ones (radius ~100 mm) are kept in the V8."""
    import math as _m
    return [s for s in v7("Station_fasteners").Solids()
            if 95 < _m.hypot(s.Center().x, s.Center().y) < 106]


def v7_enclosure_pieces():
    """The V7 enclosure's printed pieces: deck (z −5..0), inner shell, lower body, and the
    small insert/screw solids."""
    sol = v7("Enclosure").Solids()
    deck = [s for s in sol if s.BoundingBox().zmin > -5.5 and s.Volume() > 1e4]
    shell = [s for s in sol if s.BoundingBox().zmax > -6 and s.BoundingBox().zmax < -4 and s.Volume() > 1e4]
    lower = [s for s in sol if s.BoundingBox().zmax < -50 and s.Volume() > 1e4]
    small = [s for s in sol if s.Volume() <= 1e4]
    return deck[0], shell[0], lower[0], small


# ----------------------------------------------------------------- V2 module (unchanged parts)
def v2_module_bodies(kit: str):
    """(name, colour, solid in the V2 world) for one V2 module without its stand-alone base
    and cup: disc, back plate, hopper, cover, side plates and the bought drive parts."""
    sp = importlib.util.spec_from_file_location("v2_assemble", ROOT / "cad" / "variants" / "v2_inclined_disc" / "assemble.py")
    a = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(a)
    return [(n, c, s) for n, c, s in a.bodies(kit) if n not in ("base", "cup")]
