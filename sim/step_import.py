"""Read a STEP assembly into named, placed parts and export one STL per part."""
from __future__ import annotations

import collections
import re
from pathlib import Path

import cadquery as cq
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool


def read_parts(step_path: str | Path) -> list[tuple[str, cq.Shape]]:
    """Return (name, shape) for every leaf part, with assembly placement applied."""
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(step_path)) != 1:
        raise IOError(f"cannot read {step_path}")
    reader.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name(label) -> str:
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            return attr.Get().ToExtString()
        return "unnamed"

    out: list[tuple[str, cq.Shape]] = []

    def visit(label, loc):
        if tool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                ref = TDF_Label()
                tool.GetReferredShape_s(comp, ref)
                visit(ref, loc * tool.GetLocation_s(comp))
        else:
            out.append((name(label), cq.Shape.cast(tool.GetShape_s(label).Moved(loc))))

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        visit(roots.Value(i), TopLoc_Location())
    return out


def export_parts(step_path: str | Path, out_dir: str | Path, skip=lambda n: False,
                 tolerance: float = 0.03) -> dict[str, Path]:
    """Export each part to <out_dir>/<name>.stl (duplicates get _2, _3 ...)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = collections.Counter()
    paths: dict[str, Path] = {}
    for n, shape in read_parts(step_path):
        if skip(n):
            continue
        seen[n] += 1
        key = n if seen[n] == 1 else f"{n}_{seen[n]}"
        p = out_dir / (re.sub(r"[^A-Za-z0-9_-]+", "_", key) + ".stl")
        if not p.exists():
            cq.exporters.export(cq.Workplane().add(shape), str(p), tolerance=tolerance,
                                angularTolerance=0.1)
        paths[key] = p
    return paths
