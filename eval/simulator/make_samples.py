"""Write the small committed sample set (SPEC M1) to results/synthetic_samples/. All clips are SYNTHETIC."""

from __future__ import annotations

import json
from pathlib import Path

from eval.simulator.render import SimConfig, simulate

REPO = Path(__file__).resolve().parents[2]
BASE = dict(width=160, height=120, duration_s=6.0, ref_margin_s=60, seed=21)
SAMPLES = {
    "clean_with_sidecar": {"sidecar": True},
    "cut_0p5s": {"edits": [{"type": "cut", "at_s": 3.1, "dur_s": 0.5}]},
    "dropped_frames": {"drop_frames": [(90, 4)]},
    "no_mains_light": {"flicker_depth": 0.0},
    "camera_motion": {"camera_motion_px": 2.0, "moving_objects": 1},
    "cols_axis_messaging": {"sensor_axis": "cols", "compression": "messaging"},
}


def main() -> None:
    out = REPO / "results" / "synthetic_samples"
    index = []
    for name, kw in SAMPLES.items():
        tr = simulate(SimConfig(**{**BASE, **kw}), out, name)
        index.append({"name": name, "video": tr["video"], "truth": f"{name}.truth.json", "label": tr["label"],
                      "expected_class": tr["expected_class"], "video_sha256": tr["video_sha256"]})
    (out / "index.json").write_text(json.dumps(index, indent=1))
    print(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
