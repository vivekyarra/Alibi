"""Synthetic evaluation suites (SPEC 11.1). Every clip is labeled SYNTHETIC.

The split is by seed ("session"): even seeds → calibration, odd seeds → test (SPEC 11.4 analogue).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np

from eval.simulator.render import SimConfig, simulate

BASE = SimConfig(duration_s=36.0, width=320, height=240, compression="high", flicker_depth=0.08,
                 noise_sigma=1.0, sidecar=True)


def _start(seed: int) -> float:
    # spread recording times over several days and times of day (deterministic per seed)
    rng = np.random.default_rng(seed + 31337)
    return float(1768471200 + int(rng.integers(0, 6)) * 86400 + int(rng.integers(0, 86400)))


def suite_v1() -> list[tuple[str, SimConfig, str]]:
    """(name, config, condition) — ~2 clips per condition per split."""
    conds: list[tuple[str, dict[str, Any]]] = [
        ("clean", {}),
        ("no_sidecar", {"sidecar": False}),
        ("weak_flicker", {"flicker_depth": 0.02}),
        ("short_readout_long_expo", {"readout_s": 0.012, "exposure_s": 0.004}),
        ("jitter", {"jitter_ms": 1.0, "sidecar": False}),
        ("dropped_frames", {"drop_frames": [(400, 4), (700, 7)]}),
        ("camera_motion", {"camera_motion_px": 3.0}),
        ("moving_objects", {"moving_objects": 2}),
        ("noisy", {"noise_sigma": 3.0}),
        ("web_compression", {"compression": "web"}),
        ("messaging_compression", {"compression": "messaging"}),
        ("clock_ppm", {"clock_ppm": 30.0, "sidecar": False}),
        ("cols_axis", {"sensor_axis": "cols", "sidecar": False}),
        ("rotation_meta", {"rotation_deg": 90, "sidecar": False}),
        ("no_mains_light", {"flicker_depth": 0.0}),
        ("daylight_partial", {"daylight_region": True, "daylight_region_noise": 6.0, "flicker_depth": 0.03,
                              "sidecar": False}),
        ("cut_0p5s", {"edits": [{"type": "cut", "at_s": 15.3, "dur_s": 0.5}]}),
        ("cut_1s", {"edits": [{"type": "cut", "at_s": 17.1, "dur_s": 1.0}]}),
        ("cut_2s", {"edits": [{"type": "cut", "at_s": 12.7, "dur_s": 2.0}]}),
        ("insert_other_time", {"duration_s": 70.0, "edits": [{"type": "insert", "at_s": 30.0, "dur_s": 32.0,
                                                               "from_offset_s": -1500.0}]}),
        ("reorder", {"duration_s": 70.0, "edits": [{"type": "reorder", "a_s": 3.0, "b_s": 36.0, "dur_s": 30.0}]}),
        ("hdr", {"transfer": "hlg", "duration_s": 6.0}),
    ]
    out = []
    for ci, (cond, kw) in enumerate(conds):
        for rep in range(2):
            seed = 1000 + ci * 10 + rep  # rep 0 → even → calibration, rep 1 → odd → test
            cfg = replace(BASE, seed=seed, start_utc=_start(seed), **kw)
            out.append((f"{cond}__s{seed}", cfg, cond))
    return out


def split_of(seed: int) -> str:
    return "calibration" if seed % 2 == 0 else "test"


def generate(out_dir: Path, names: list[str] | None = None) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, cfg, cond in suite_v1():
        if names and name not in names and cond not in names:
            continue
        truth_p = out_dir / f"{name}.truth.json"
        tr = json.loads(truth_p.read_text()) if truth_p.exists() else simulate(cfg, out_dir, name)
        manifest.append({"name": name, "condition": cond, "split": split_of(cfg.seed), "label": "SYNTHETIC",
                         "video": f"{name}.mp4", "truth": truth_p.name, "class": tr["expected_class"],
                         "sidecar": tr.get("sidecar"), "config": asdict(cfg)})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the SYNTHETIC evaluation suite")
    ap.add_argument("--out", default="data/synthetic/v1")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    m = generate(Path(a.out), a.only)
    print(f"{len(m)} clips in {a.out}")
