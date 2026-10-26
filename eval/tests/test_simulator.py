"""Simulator (SPEC 11.1): every factor produces a video plus ground truth, labeled SYNTHETIC."""

from __future__ import annotations

import json
from pathlib import Path

import av
import numpy as np

from eval.simulator.enf_model import GridSignal, ou_track
from eval.simulator.render import SimConfig, simulate
from gridprint_engine.adapters import LocalGridLog

TINY = dict(width=64, height=48, duration_s=3.0, ref_margin_s=20)


def test_grid_signal_integral_and_reference():
    g = GridSignal(1000, np.array([50.0, 50.1, 50.1, 49.9]))
    assert g.grid_cycles(np.array([1000.0]))[0] == 0.0
    assert g.grid_cycles(np.array([1001.0]))[0] == np.float64(50.05)
    t, f = g.reference_log()
    assert list(t) == [1000, 1001, 1002] and np.allclose(f, [50.05, 50.1, 50.0])


def test_ou_track_is_deterministic_and_near_nominal():
    a = ou_track(3600, 50.0, np.random.default_rng(1))
    b = ou_track(3600, 50.0, np.random.default_rng(1))
    assert np.array_equal(a, b) and abs(a.mean() - 50.0) < 0.05 and a.dtype == np.float64


def test_every_factor_renders_with_ground_truth(tmp_path: Path):
    factors = {
        "depth": {"flicker_depth": 0.05}, "readout": {"readout_s": 0.015}, "exposure": {"exposure_s": 0.004},
        "jitter": {"jitter_ms": 1.0}, "dropped": {"drop_frames": [(20, 3)]}, "motion": {"camera_motion_px": 2.0},
        "objects": {"moving_objects": 1}, "noise": {"noise_sigma": 3.0}, "compression": {"compression": "messaging"},
        "cut": {"edits": [{"type": "cut", "at_s": 1.0, "dur_s": 0.5}]},
        "insert": {"edits": [{"type": "insert", "at_s": 1.0, "dur_s": 0.5, "from_offset_s": -10.0}]},
        "reorder": {"edits": [{"type": "reorder", "a_s": 0.2, "b_s": 1.6, "dur_s": 0.6}]},
        "axis": {"sensor_axis": "cols"}, "rotation": {"rotation_deg": 90}, "hdr": {"transfer": "hlg"},
        "sidecar": {"sidecar": True}, "clock": {"clock_ppm": 50.0},
    }
    for name, kw in factors.items():
        tr = simulate(SimConfig(seed=3, **{**TINY, **kw}), tmp_path, name)
        assert tr["label"] == "SYNTHETIC"
        with av.open(str(tmp_path / tr["video"])) as c:
            n = sum(1 for _ in c.decode(video=0))
        assert n == len(tr["frame_pts_s"]) == len(tr["frame_capture_t_s"])
        assert json.loads((tmp_path / f"{name}.truth.json").read_text())["video_sha256"] == tr["video_sha256"]
        t, f = LocalGridLog(tmp_path / tr["gridlog_root"]).read("SIM50", tr["start_utc"] - 5, tr["start_utc"] + 5)
        assert len(t) == 11 and np.all(np.abs(f - 50) < 0.5)
    cut = json.loads((tmp_path / "cut.truth.json").read_text())
    assert cut["edits"][0]["frames_removed"] == 15 and cut["expected_class"] == "edited"
    assert np.allclose(np.diff(cut["frame_pts_s"]), 1 / 30)  # re-timed: looks continuous
    dropped = json.loads((tmp_path / "dropped.truth.json").read_text())
    assert max(np.diff(dropped["frame_pts_s"])) > 0.1  # original timestamps kept
    assert (tmp_path / "sidecar.sidecar.json").exists()
