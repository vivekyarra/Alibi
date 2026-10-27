"""Video-level integration tests on SYNTHETIC clips (M2/M3 acceptance).

Covers VFR timestamps, gaps, sensor-row axis, rotation metadata, HDR, linear light, ENF recovery and time
offset, estimator agreement, cuts, dropped frames, and report generation. Thresholds come from a test file
(the production file stays the only source for real verdicts, R8).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from eval.simulator.render import SimConfig, simulate
from gridprint_engine import io
from gridprint_engine.adapters import LocalGridLog
from gridprint_engine.config import CONFIG_DIR, load_settings
from gridprint_engine.pipeline import Job, run_default
from gridprint_engine.schemas import Reason, Verdict

SMALL = dict(width=160, height=120, ref_margin_s=300, flicker_depth=0.1, noise_sigma=0.8)
TEST_THR = {"signal": {"snr_absent_db": 3.0, "snr_weak_db": 6.0},
            "match": {"min_track_s": 20, "rho1_min": 0.8, "margin_min": 0.02},
            "continuity": {"edit_significance_sigma": 6.0, "edit_min_rad": 0.15},
            "facecheck": {"ratio_anomaly": 0.5}}


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Path, dict]]:
    d = tmp_path_factory.mktemp("clips")
    cfgs = {
        "clean": SimConfig(seed=11, duration_s=40, sidecar=True, **SMALL),
        "cut": SimConfig(seed=11, duration_s=40, edits=[{"type": "cut", "at_s": 17.3, "dur_s": 1.0}], **SMALL),
        "dropped": SimConfig(seed=11, duration_s=40, drop_frames=[(300, 5), (800, 7)], **SMALL),
        "cols": SimConfig(seed=12, duration_s=6, sensor_axis="cols", **SMALL),
        "rot": SimConfig(seed=13, duration_s=3, rotation_deg=90, **SMALL),
        "vfr": SimConfig(seed=14, duration_s=4, jitter_ms=2.0, drop_frames=[(50, 3)], **SMALL),
        "hdr": SimConfig(seed=15, duration_s=1, transfer="hlg", **SMALL),
        "nomains": SimConfig(seed=16, duration_s=6, **{**SMALL, "flicker_depth": 0.0}),
    }
    out = {}
    for name, cfg in cfgs.items():
        tr = simulate(cfg, d, name)
        out[name] = (d, tr)
    thr = d / "thresholds.yaml"
    thr.write_text(yaml.safe_dump(TEST_THR))
    out["_settings"] = load_settings(CONFIG_DIR, thr)  # type: ignore[assignment]
    return out


def _job(clips, name, **kw) -> Job:
    d, tr = clips[name]
    side = d / tr["sidecar"] if tr.get("sidecar") else None
    return run_default(d / tr["video"], d / "work", LocalGridLog(d / tr["gridlog_root"]), sidecar=side,
                       cfg=clips["_settings"], job_id=name, **kw)


def test_vfr_timestamps_gaps_and_jitter(clips):
    d, tr = clips["vfr"]
    pts = io.read_pts(d / tr["video"])
    assert np.allclose(pts - pts[0], np.array(tr["frame_pts_s"]) - tr["frame_pts_s"][0], atol=2e-5)
    tm = io.compute_timing(pts, None, 1.5)
    assert any(g.frame_index == 50 for g in tm.gaps)
    assert tm.jitter_p95_ms > 1.0  # 2 ms jitter was injected
    assert np.allclose(io.read_pts_ffprobe(d / tr["video"]), pts, atol=1e-5)  # V9 fallback agrees


def test_rotation_metadata_is_recorded_but_not_applied(clips):
    d, tr = clips["rot"]
    pr = io.probe_video(d / tr["video"])
    assert abs(pr.rotation) == 90
    fs = io.decode_frames(d / tr["video"], "bt709", 240, 320, 0.98, 0.02)
    assert (fs.n_rows, fs.n_cols) == (120, 160)  # coded (sensor) orientation kept
    assert fs.lin.dtype == np.float32  # R6


def test_sensor_axis_columns_detected(clips):
    d, tr = clips["cols"]
    j = Job(d / tr["video"], d / "work", LocalGridLog(d / tr["gridlog_root"]), cfg=clips["_settings"])
    j.probe_video()
    j.estimate_readout("blind")
    out = j.extract_flicker()
    assert out["axis"] == "cols+"
    assert j.readout is not None and j.readout.readout_s == pytest.approx(0.025, rel=0.1)


def test_hdr_stops_with_inconclusive(clips):
    j = _job(clips, "hdr")
    assert j.result is not None
    assert j.result.verdict == Verdict.INCONCLUSIVE and Reason.HDR_UNSUPPORTED in j.result.reasons


def test_no_mains_light_is_inconclusive_never_contradicted(clips):
    j = _job(clips, "nomains")
    assert j.result is not None
    assert j.result.verdict == Verdict.INCONCLUSIVE
    assert Reason.SIGNAL_ABSENT in j.result.reasons


def test_clean_clip_verified_with_time_and_report(clips):
    j = _job(clips, "clean", render=True)
    r = j.result
    assert r is not None
    _, tr = clips["clean"]
    assert r.verdict == Verdict.VERIFIED, r.reasons
    assert abs(r.time_estimate_utc - tr["start_utc"]) < 1.0
    assert r.quality["estimators_agree"] is True
    # ENF track recovered: compare with the ground-truth grid frequency
    track = j.primary_track().track
    gt = np.array(tr["enf_clip_hz"])[np.floor(track.tau_s).astype(int)]
    err = (track.enf_hz - track.enf_hz.mean()) - (gt - gt.mean())
    assert np.sqrt(np.mean(err ** 2)) < 0.003
    for k in ("report_html", "report_pdf", "report_json", "overlay_mp4"):
        assert Path(r.artifacts[k]).exists() and Path(r.artifacts[k]).stat().st_size > 0
    assert json.loads(Path(r.artifacts["report_json"]).read_text())["lifecycle_state"] == "FINAL"
    html = Path(r.artifacts["report_html"]).read_text(encoding="utf-8")
    from scripts.claims_lint import scan_text

    assert scan_text(html) == []
    assert "Limitations" in html and "alt=" in html


def test_cut_is_contradicted_and_localized(clips):
    j = _job(clips, "cut", render=True)
    r = j.result
    assert r is not None
    assert r.verdict == Verdict.CONTRADICTED and r.lifecycle_state.value == "PENDING_REVIEW"
    edits = [e for e in r.continuity_events if e.kind == "EDIT_CANDIDATE"]
    assert edits and min(abs(e.t_s - 17.3) for e in edits) < 0.2
    with pytest.raises(Exception, match="FINAL report blocked"):
        j.render_report(final=True)


def test_dropped_frames_with_true_timestamps_not_flagged(clips):
    j = _job(clips, "dropped")
    r = j.result
    assert r is not None
    assert not any(e.kind == "EDIT_CANDIDATE" for e in r.continuity_events)
    assert Reason.DROPPED_FRAMES_EXPLAINED in r.reasons
    assert r.verdict != Verdict.CONTRADICTED
