#!/usr/bin/env python3
"""Export the team's Onshape CAD to STEP/STL files in cad/onshape/.

Reads cad/onshape_documents.json, which lists Onshape URLs to export. Each URL
must open a Part Studio or Assembly tab, for example:
    https://cad.onshape.com/documents/<did>/w/<wid>/e/<eid>

Authentication uses Onshape API keys (Onshape Developer Portal -> API keys),
read from the environment variables ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY.
Never commit the keys; in GitHub they are stored as repository secrets.

Usage:
    python tools/onshape_sync.py            # export everything listed
    python tools/onshape_sync.py --dry-run  # only check the URLs and access
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://cad.onshape.com"
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "cad" / "onshape_documents.json"
OUT = ROOT / "cad" / "onshape"
URL_RE = re.compile(
    r"/documents/(?P<did>[0-9a-f]{24})/(?P<wvm>[wvm])/(?P<wvmid>[0-9a-f]{24})"
    r"/e/(?P<eid>[0-9a-f]{24})"
)


def session() -> requests.Session:
    access = os.environ.get("ONSHAPE_ACCESS_KEY")
    secret = os.environ.get("ONSHAPE_SECRET_KEY")
    if not access or not secret:
        sys.exit("Set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY (Onshape API keys).")
    s = requests.Session()
    s.auth = (access, secret)  # Onshape accepts API keys as HTTP Basic auth.
    s.headers["Accept"] = "application/json;charset=UTF-8; qs=0.09"
    return s


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "unnamed"


def element_info(s, did, wvm, wvmid, eid) -> dict:
    r = s.get(f"{BASE}/api/v6/documents/d/{did}/{wvm}/{wvmid}/elements",
              params={"elementId": eid}, timeout=60)
    r.raise_for_status()
    items = r.json()
    if not items:
        raise RuntimeError(f"Element {eid} not found in document {did}")
    return items[0]


def translate(s, did, wvm, wvmid, eid, kind: str, fmt: str) -> bytes:
    """Start an Onshape translation, wait for it, and return the file bytes."""
    path = "partstudios" if kind == "PARTSTUDIO" else "assemblies"
    body = {"formatName": fmt, "storeInDocument": False}
    if fmt == "STL":
        body.update({"units": "millimeter", "mode": "binary", "grouping": True,
                     "resolution": "fine"})
    r = s.post(f"{BASE}/api/v6/{path}/d/{did}/{wvm}/{wvmid}/e/{eid}/translations",
               json=body, timeout=60)
    r.raise_for_status()
    tid = r.json()["id"]
    for _ in range(120):  # up to ~6 minutes
        time.sleep(3)
        t = s.get(f"{BASE}/api/v6/translations/{tid}", timeout=60)
        t.raise_for_status()
        state = t.json()
        if state["requestState"] == "DONE":
            fid = state["resultExternalDataIds"][0]
            f = s.get(f"{BASE}/api/v6/documents/d/{did}/externaldata/{fid}",
                      headers={"Accept": "application/octet-stream"}, timeout=300)
            f.raise_for_status()
            return f.content
        if state["requestState"] == "FAILED":
            raise RuntimeError(f"Translation failed: {state.get('failureReason')}")
    raise TimeoutError("Onshape translation did not finish in time")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    docs = json.loads(CONFIG.read_text())["documents"]
    s = session()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, failures = [], 0
    for entry in docs:
        m = URL_RE.search(entry["url"])
        if not m:
            print(f"SKIP (not a Part Studio/Assembly URL): {entry['url']}")
            failures += 1
            continue
        did, wvm, wvmid, eid = m.group("did", "wvm", "wvmid", "eid")
        try:
            info = element_info(s, did, wvm, wvmid, eid)
            kind = info["elementType"]
            if kind not in ("PARTSTUDIO", "ASSEMBLY"):
                raise RuntimeError(f"tab type {kind} cannot be exported")
            name = slug(entry.get("name") or info["name"])
            print(f"{name}: {kind}")
            if args.dry_run:
                continue
            formats = entry.get("formats", ["STEP", "STL"])
            if kind == "ASSEMBLY":
                formats = [f for f in formats if f != "STL"] or ["STEP"]
            files = []
            for fmt in formats:
                data = translate(s, did, wvm, wvmid, eid, kind, fmt)
                ext = {"STEP": "step", "STL": "stl"}[fmt]
                # Multi-part STL exports arrive as a zip archive.
                if fmt == "STL" and data[:2] == b"PK":
                    ext = "stl.zip"
                dest = OUT / f"{name}.{ext}"
                dest.write_bytes(data)
                files.append(dest.name)
                print(f"  wrote {dest.relative_to(ROOT)} ({len(data)} bytes)")
            manifest.append({"name": name, "url": entry["url"], "type": kind,
                             "onshape_element_name": info["name"], "files": files})
        except Exception as exc:  # report every document, then fail at the end
            print(f"ERROR {entry['url']}: {exc}")
            failures += 1
    if not args.dry_run:
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
