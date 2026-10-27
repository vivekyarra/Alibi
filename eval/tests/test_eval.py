"""Evaluation harness tests: metrics, replay consistency with S13, calibration and dataset validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval import calibrate_thresholds as cal
from eval import metrics, validate_dataset
from eval.replay import replay

THR = {"signal": {"snr_absent_db": 3.0, "snr_weak_db": 8.0},
       "match": {"min_track_s": 20, "rho1_min": 0.9, "margin_min": 0.05},
       "continuity": {"edit_significance_sigma": 6.0, "edit_min_rad": 0.15}, "facecheck": {"ratio_anomaly": 0.5}}


def raw(snr=15.0, rho1=0.97, margin=0.1, length=35.0, boundaries=(), segs=()):
    return {"persistent_reasons": ["READOUT_FROM_SIDECAR"], "band_snr_db": snr,
            "match": {"rho1": rho1, "rho2": rho1 - margin, "margin": margin, "length_s": length,
                      "best_offset_utc": 1000.0, "coverage": True, "segment_stats": list(segs)},
            "boundaries": list(boundaries)}


def test_wilson_interval():
    p, lo, hi = metrics.wilson(0, 20)
    assert p == 0 and lo == 0 and 0.1 < hi < 0.2
    assert metrics.wilson(0, 0) == (None, None, None)


def test_replay_rules():
    assert replay(raw(), THR, 3)[0] == "VERIFIED"
    assert replay(raw(snr=1.0), THR, 3)[0] == "INCONCLUSIVE"
    assert replay(raw(margin=0.01), THR, 3)[0] == "INCONCLUSIVE"
    assert replay(raw(length=10), THR, 3)[0] == "INCONCLUSIVE"
    cut = [{"t_s": 12.0, "z": 20.0, "rad": 0.7, "gap": False}]
    assert replay(raw(boundaries=cut), THR, 3)[0] == "CONTRADICTED"
    assert replay(raw(snr=5.0, boundaries=cut), THR, 3)[0] == "INCONCLUSIVE"  # weak signal → never rule 2
    dropped = [{"t_s": 12.0, "z": 1.0, "rad": 0.02, "gap": True}]
    v, rs = replay(raw(boundaries=dropped), THR, 3)
    assert v == "VERIFIED" and "DROPPED_FRAMES_EXPLAINED" in rs
    segs = [{"rho1": 0.97, "offset": 1000.0, "margin": 0.2}, {"rho1": 0.96, "offset": 2500.0, "margin": 0.2}]
    assert replay(raw(segs=segs), THR, 3)[0] == "CONTRADICTED"
    claim = {"claimed_time_utc": 5000.0, "claimed_time_tolerance_s": 60}
    v, rs = replay(raw(), THR, 3, claim)
    assert v == "CONTRADICTED" and "CLAIM_TIME_MISMATCH" in rs


def test_calibration_respects_target_and_picks_coverage():
    recs = []
    for i in range(10):  # authentic, mains-lit: correct time
        recs.append({"class": "authentic-with-mains-light", "truth_start_utc": 1000.0, "time_error_s": 0.1,
                     "raw": raw(rho1=0.93 + 0.005 * i, margin=0.03 + 0.01 * i)})
    for _ in range(4):  # edited
        recs.append({"class": "edited", "raw": raw(boundaries=[{"t_s": 5, "z": 30, "rad": 0.8, "gap": False}])})
    # an authentic clip with a mild phase glitch must not become CONTRADICTED (target 0)
    recs.append({"class": "authentic-with-mains-light", "truth_start_utc": 1000.0,
                 "raw": raw(boundaries=[{"t_s": 5, "z": 7.0, "rad": 0.2, "gap": False}])})
    thr, ev = cal.calibrate(recs, 0.0, 3)
    assert ev["false_contradicted"] == 0.0
    assert ev["edit_detection"] == 1.0
    assert ev["coverage"] > 0.5
    assert thr["continuity"]["edit_significance_sigma"] >= 8.0 or thr["continuity"]["edit_min_rad"] > 0.2


def test_edit_detection_counts_contradicted_edits_without_truth_time():
    base = {"class": "edited", "condition": "x", "expected_verdict": "CONTRADICTED"}
    recs = [
        # insert: truth time present, localized
        {**base, "name": "a", "verdict": "CONTRADICTED", "reasons": ["EDIT_CANDIDATE"], "edits_true_t_s": [30.0],
         "edit_localization_error_s": [0.5]},
        # reorder: no truth time, still a correct detection; no localization entry
        {**base, "name": "b", "verdict": "CONTRADICTED", "reasons": ["SEGMENT_OFFSET_INCONSISTENT"],
         "edits_true_t_s": []},
        # CONTRADICTED only by a claimed-time mismatch is not an edit detection
        {**base, "name": "c", "verdict": "CONTRADICTED", "reasons": ["CLAIM_TIME_MISMATCH"], "edits_true_t_s": [5.0],
         "edit_localization_error_s": []},
        {**base, "name": "d", "verdict": "VERIFIED", "reasons": ["MATCH_OK"], "edits_true_t_s": [5.0],
         "edit_localization_error_s": []},
    ]
    s = metrics.summarize(recs)
    assert (s["edit_detection"]["k"], s["edit_detection"]["n"]) == (2, 4)
    assert s["edit_localization_error_s"] == {"n": 1, "mean": 0.5, "median": 0.5, "p95": 0.5, "max": 0.5}


def test_dataset_validator_reports_problems(tmp_path: Path):
    m = {"dataset_version": "t", "clips": [{"clip_id": "a", "file": "a.mp4", "app": "nope", "people_present": True,
                                             "consent_ids": [], "gt_start_utc": "x"}]}
    errs = validate_dataset.check(m, tmp_path, verify_hashes=False)
    joined = "\n".join(errs)
    for needle in ("missing sha256", "app='nope'", "consent", "ISO 8601", "file not found", "originals: 0 < 300"):
        assert needle in joined


@pytest.mark.parametrize("cls,expected", [("authentic-with-mains-light", "VERIFIED"), ("edited", "CONTRADICTED"),
                                          ("authentic-without-mains-light", "INCONCLUSIVE")])
def test_expected_verdicts(cls, expected):
    from eval.run_eval import EXPECTED

    assert EXPECTED[cls] == expected
