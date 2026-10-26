"""Write bench/inputs.txt (pinned benchmark inputs with SHA-256) from a set of local clips.

The same files must be copied to every benchmark machine; run_bench refuses inputs whose hash differs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(names: list[str]) -> None:
    d = REPO / "data" / "synthetic" / "v1"
    lines = ["# sha256 video sidecar gridlog-root   (SYNTHETIC clips from eval/simulator/suites.py)"]
    for n in names:
        tr = json.loads((d / f"{n}.truth.json").read_text())
        v = d / f"{n}.mp4"
        sc = f"data/synthetic/v1/{tr['sidecar']}" if tr.get("sidecar") else "-"
        h = hashlib.sha256(v.read_bytes()).hexdigest()
        lines.append(f"{h} data/synthetic/v1/{n}.mp4 {sc} data/synthetic/v1/{tr['gridlog_root']}")
    (REPO / "bench" / "inputs.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:] or ["clean__s1000", "camera_motion__s1060", "moving_objects__s1070"])
