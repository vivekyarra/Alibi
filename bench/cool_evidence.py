"""Collect runtime evidence of which OpenCV build is loaded (SPEC Part 4 V5, Part 12 step 6).

Writes to `results/bench/<date>/evidence/<label>/`:
- `build_information.txt`  cv2.getBuildInformation() text
- `versions.json`          cv2 version, cv2.__file__, Python, platform, NumPy
- `loaded_libraries.txt`   shared objects mapped into this process (/proc/self/maps, Linux only)
- `perf_record.txt`, `perf_report.txt`  only when `--cmd` is given and `perf` exists
- `manifest.json`          what was collected, what was skipped and why

This script records facts. It does not decide whether COOL is in use. A person reads the files
(build information, library paths, profiler symbols) and writes the claim with source tags.

Usage:
    python -m bench.cool_evidence --label C [--cmd "python -m bench.run_bench --config C"]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MAPS = Path("/proc/self/maps")
# Substrings searched (case-insensitive) in build info, library paths and perf output.
# A hit is a fact to look at, not a claim.
MARKERS = ("kleidicv", "kleidi", "cool", "opencv")


def loaded_libraries(maps_path: Path = MAPS) -> list[str] | None:
    """Unique file paths of shared objects mapped into this process, or None if maps is absent."""
    if not maps_path.exists():
        return None
    libs: set[str] = set()
    for line in maps_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith("/") and ".so" in parts[5]:
            libs.add(parts[5].strip())
    return sorted(libs)


def marker_hits(text: str) -> dict[str, int]:
    low = text.lower()
    return {m: low.count(m) for m in MARKERS}


def run_perf(cmd: str, out_dir: Path, timeout_s: int) -> dict[str, Any]:
    perf = shutil.which("perf")
    if perf is None:
        return {"status": "skipped", "reason": "perf not found on PATH"}
    data = out_dir / "perf.data"
    rec = subprocess.run([perf, "record", "-g", "-o", str(data), "--", *shlex.split(cmd)],
                         capture_output=True, text=True, timeout=timeout_s)
    (out_dir / "perf_record.txt").write_text(rec.stdout + "\n--- stderr ---\n" + rec.stderr, encoding="utf-8")
    if rec.returncode != 0:
        return {"status": "failed", "step": "record", "returncode": rec.returncode}
    rep = subprocess.run([perf, "report", "--stdio", "--sort", "dso,symbol", "-i", str(data)],
                         capture_output=True, text=True, timeout=timeout_s)
    (out_dir / "perf_report.txt").write_text(rep.stdout + "\n--- stderr ---\n" + rep.stderr, encoding="utf-8")
    return {"status": "ok" if rep.returncode == 0 else "failed", "step": "report",
            "returncode": rep.returncode, "marker_hits": marker_hits(rep.stdout)}


def collect(out_dir: Path, cmd: str | None = None, timeout_s: int = 3600,
            maps_path: Path = MAPS) -> dict[str, Any]:
    import cv2
    import numpy as np

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"collected_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                                "files": {}}

    build = cv2.getBuildInformation()
    (out_dir / "build_information.txt").write_text(build, encoding="utf-8")
    manifest["files"]["build_information.txt"] = {"marker_hits": marker_hits(build)}

    versions = {
        "cv2_version": cv2.__version__,
        "cv2_file": str(Path(cv2.__file__).resolve()) if cv2.__file__ else None,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
    }
    (out_dir / "versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
    manifest["files"]["versions.json"] = {}

    libs = loaded_libraries(maps_path)
    if libs is None:
        manifest["files"]["loaded_libraries.txt"] = {"status": "skipped",
                                                     "reason": f"{maps_path} not available on this OS"}
    else:
        (out_dir / "loaded_libraries.txt").write_text("\n".join(libs) + "\n", encoding="utf-8")
        manifest["files"]["loaded_libraries.txt"] = {"count": len(libs),
                                                     "marker_hits": marker_hits("\n".join(libs))}

    manifest["perf"] = run_perf(cmd, out_dir, timeout_s) if cmd else {"status": "skipped",
                                                                      "reason": "no --cmd given"}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect OpenCV/COOL runtime evidence.")
    ap.add_argument("--label", required=True, help="configuration label, for example A, B or C")
    ap.add_argument("--cmd", default=None, help="command to profile with perf record")
    ap.add_argument("--timeout-s", type=int, default=3600)
    ap.add_argument("--results", type=Path, default=REPO / "results")
    args = ap.parse_args(argv)
    day = dt.datetime.now(dt.UTC).date().isoformat()
    out = args.results / "bench" / day / "evidence" / args.label
    manifest = collect(out, args.cmd, args.timeout_s)
    print(json.dumps({"out_dir": str(out), "perf": manifest["perf"].get("status")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
