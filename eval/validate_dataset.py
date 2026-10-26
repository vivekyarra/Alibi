"""Validate the real dataset manifest (SPEC 11.2, H5–H7): schema, hashes, counts per cell, ground truth, splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = Path(__file__).with_name("manifest_schema.json")
CORE = ("phone_model", "app", "lighting", "motion")
MIN_PER_CELL = 5
MIN_ORIGINALS = 300
MIN_DAYS = 5
MIN_PHONES = 3


def check(manifest: dict[str, Any], root: Path, verify_hashes: bool = True) -> list[str]:
    errs: list[str] = []
    schema = json.loads(SCHEMA.read_text())
    req = schema["properties"]["clips"]["items"]["required"]
    props = schema["properties"]["clips"]["items"]["properties"]
    clips = manifest.get("clips", [])
    ids = Counter(c.get("clip_id") for c in clips)
    errs += [f"duplicate clip_id {k}" for k, n in ids.items() if n > 1]
    for c in clips:
        cid = c.get("clip_id", "?")
        for k in req:
            if k not in c:
                errs.append(f"{cid}: missing {k}")
        for k, spec in props.items():
            if k in c and "enum" in spec and c[k] not in spec["enum"]:
                errs.append(f"{cid}: {k}={c[k]!r} not in {spec['enum']}")
        try:
            datetime.fromisoformat(str(c.get("gt_start_utc", "")).replace("Z", "+00:00"))
        except ValueError:
            errs.append(f"{cid}: gt_start_utc is not ISO 8601")
        if c.get("people_present") and not c.get("consent_ids"):
            errs.append(f"{cid}: people present but no consent_ids")
        f = root / str(c.get("file", ""))
        if not f.exists():
            errs.append(f"{cid}: file not found {f}")
        elif verify_hashes and hashlib.sha256(f.read_bytes()).hexdigest() != c.get("sha256"):
            errs.append(f"{cid}: sha256 mismatch")
    originals = [c for c in clips if c.get("compression") == "original" and not c.get("derived_from")]
    if len(originals) < MIN_ORIGINALS:
        errs.append(f"originals: {len(originals)} < {MIN_ORIGINALS}")
    if len({c.get("recorded_day") for c in originals}) < MIN_DAYS:
        errs.append(f"recording days < {MIN_DAYS}")
    phones = {c.get("phone_model") for c in originals}
    if len(phones) < MIN_PHONES:
        errs.append(f"phone models: {len(phones)} < {MIN_PHONES}")
    if originals and all(c.get("used_for_calibration_rig", False) for c in originals):
        errs.append("no phone model outside the calibration set")
    cells = Counter(tuple(c.get(k) for k in CORE) for c in originals if abs(float(c.get("duration_s", 0)) - 30) < 3)
    errs += [f"core cell {cell}: {n} clips < {MIN_PER_CELL}" for cell, n in cells.items() if n < MIN_PER_CELL]
    sessions: dict[str, set[str]] = {}
    for c in clips:
        sessions.setdefault(c.get("session_id", ""), set()).add(c.get("split", ""))
    errs += [f"session {s} appears in both splits" for s, sp in sessions.items() if len(sp) > 1]
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--no-hash", action="store_true")
    a = ap.parse_args()
    p = Path(a.manifest)
    if not p.exists():
        print(f"manifest not found: {p} (human task H5)")
        return 1
    errs = check(json.loads(p.read_text()), p.parent, not a.no_hash)
    for e in errs:
        print("FAIL", e)
    print("DATASET OK" if not errs else f"{len(errs)} problems")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
