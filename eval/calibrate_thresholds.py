"""Choose verdict thresholds on the calibration split (SPEC 11.4, R8).

Rule: among candidate thresholds whose false-CONTRADICTED rate on authentic calibration clips is at or below
the target (DECISIONS D-019) and whose VERIFIED results have no wrong time (|error| > 2 s), pick the one
with the highest VERIFIED coverage on mains-lit clips; ties → higher edit detection, then stricter values.
Writes config/thresholds.yaml with provenance (data hash, date, script version).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from eval.replay import replay

REPO = Path(__file__).resolve().parents[1]
SCRIPT_VERSION = "1.0"
GRID: dict[str, list[float]] = {
    "snr_absent_db": [0.0, 1.5, 3.0, 4.5],
    "snr_weak_db": [4.0, 6.0, 8.0],
    "min_track_s": [20, 30],
    "rho1_min": [0.80, 0.85, 0.90, 0.95],
    "margin_min": [0.01, 0.02, 0.04, 0.08],
    "edit_significance_sigma": [5.0, 6.0, 8.0, 10.0],
    "edit_min_rad": [0.1, 0.15, 0.25, 0.4],
}


def thresholds_from(c: dict[str, float]) -> dict[str, Any]:
    return {"signal": {"snr_absent_db": c["snr_absent_db"], "snr_weak_db": c["snr_weak_db"]},
            "match": {"min_track_s": c["min_track_s"], "rho1_min": c["rho1_min"], "margin_min": c["margin_min"]},
            "continuity": {"edit_significance_sigma": c["edit_significance_sigma"],
                           "edit_min_rad": c["edit_min_rad"]},
            "facecheck": {"ratio_anomaly": 0.5}}


def evaluate(recs: list[dict[str, Any]], thr: dict[str, Any], seg_tol: float) -> dict[str, float]:
    auth = mains = fc = ver = wrong_time = edited = det = 0
    for r in recs:
        if "raw" not in r:
            continue
        v, _ = replay(r["raw"], thr, seg_tol)
        cls = r["class"]
        if cls.startswith("authentic"):
            auth += 1
            fc += v == "CONTRADICTED"
        if cls == "authentic-with-mains-light":
            mains += 1
            ver += v == "VERIFIED"
        off = (r["raw"].get("match") or {}).get("best_offset_utc")
        truth = r.get("truth_start_utc")
        if v == "VERIFIED" and off is not None and truth is not None and abs(off - truth) > 2.0:
            wrong_time += 1
        if cls == "edited":
            edited += 1
            det += v == "CONTRADICTED"
    return {"false_contradicted": fc / auth if auth else 0.0, "coverage": ver / mains if mains else 0.0,
            "wrong_time": wrong_time, "edit_detection": det / edited if edited else 0.0, "n_auth": auth}


def calibrate(recs: list[dict[str, Any]], target: float, seg_tol: float) -> tuple[dict[str, Any], dict[str, Any]]:
    best: tuple[tuple[float, ...], dict[str, Any], dict[str, Any]] | None = None
    keys = list(GRID)
    grids: list[list[float]] = [list(GRID[k]) for k in keys]
    for vals in itertools.product(*grids):
        c: dict[str, float] = dict(zip(keys, vals, strict=True))
        if c["snr_weak_db"] <= c["snr_absent_db"]:
            continue
        thr = thresholds_from(c)
        ev = evaluate(recs, thr, seg_tol)
        if ev["false_contradicted"] > target or ev["wrong_time"] > 0:
            continue
        score = (ev["coverage"], ev["edit_detection"], c["rho1_min"], c["margin_min"], c["edit_significance_sigma"])
        if best is None or score > best[0]:
            best = (score, thr, ev)
    if best is None:
        raise SystemExit("no threshold set meets the false-CONTRADICTED target on the calibration data")
    return best[1], best[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="results/eval/<date>/<suite>-<planner> containing clips/*.json")
    ap.add_argument("--out", default=str(REPO / "config" / "thresholds.yaml"))
    a = ap.parse_args()
    cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
    target = float(cfg["evaluation"]["target_false_contradicted_rate"])
    run = Path(a.run_dir)
    meta = json.loads((run / "run_meta.json").read_text())
    files = sorted((run / "clips").glob("*.json"))
    recs = [json.loads(f.read_text()) for f in files]
    recs = [r for r in recs if r.get("split") == "calibration"]
    data_hash = hashlib.sha256(b"".join(f.read_bytes() for f in files if json.loads(f.read_text()).get("split")
                                        == "calibration")).hexdigest()
    thr, ev = calibrate(recs, target, cfg["engine"]["match"]["segment_offset_tolerance_s"])
    status = "CALIBRATED" if meta.get("label") == "REAL" else "PROVISIONAL"
    thr["provenance"] = {
        "status": status,
        "note": ("calibrated on REAL calibration split" if status == "CALIBRATED" else
                 "PROVISIONAL: calibrated on SYNTHETIC data only; recalibrate on the real dataset (M9, H5)"),
        "generated_by": f"eval/calibrate_thresholds.py v{SCRIPT_VERSION}",
        "date": datetime.now(tz=UTC).isoformat(), "run_dir": str(run.relative_to(REPO)) if run.is_absolute()
        and REPO in run.parents else str(run), "calibration_clips": len(recs), "data_sha256": data_hash,
        "target_false_contradicted_rate": target, "calibration_fit": ev,
    }
    Path(a.out).write_text(yaml.safe_dump(thr, sort_keys=False))
    print(json.dumps(thr, indent=1))


if __name__ == "__main__":
    main()
