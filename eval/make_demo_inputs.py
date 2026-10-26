"""Render SYNTHETIC stand-in inputs for the demo cases marked `source: synthetic` (config/demo_cases.yaml).

The reference logs go to the GridLog root used by `make local` (data/gridlog), zone SIM50.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

from eval.simulator.render import SimConfig, simulate

REPO = Path(__file__).resolve().parents[1]
BASE = SimConfig(seed=7001, duration_s=70.0, width=320, height=240, flicker_depth=0.08, noise_sigma=1.0,
                 start_utc=1768903200.0)  # 2026-01-20T10:00:00Z
CASES = {
    "capture-verified": replace(BASE, sidecar=True),
    "cut-1s": replace(BASE, edits=[{"type": "cut", "at_s": 31.2, "dur_s": 1.0}]),
    "insertion": replace(BASE, edits=[{"type": "insert", "at_s": 30.0, "dur_s": 32.0, "from_offset_s": -1500.0}]),
    "dropped-frames": replace(BASE, sidecar=True, drop_frames=[(600, 6), (1300, 9)]),
    # other seeds use other days, so their reference spans (±1 h) never overlap in zone SIM50
    "daylight-only": replace(BASE, seed=7002, start_utc=BASE.start_utc + 86400, flicker_depth=0.0,
                             daylight_level=0.6, duration_s=30.0),
    "agent-recovery": replace(BASE, seed=7003, start_utc=BASE.start_utc + 2 * 86400, daylight_region=True,
                              daylight_region_noise=6.0, flicker_depth=0.03),
}


def main() -> None:
    out = REPO / "data" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    grid_root = REPO / "data" / "gridlog"
    for name, cfg in CASES.items():
        truth = simulate(cfg, out, name)
        # copy this clip's reference into the local GridLog. Clips with the same seed have the same
        # reference; different seeds cover different days, so no second is written twice.
        src = out / truth["gridlog_root"]
        for f in src.rglob("*.csv"):
            dst = grid_root / f.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copyfile(f, dst)
        print(json.dumps({"case": name, "video": truth["video"], "label": truth["label"]}))


if __name__ == "__main__":
    main()
