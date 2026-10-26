"""Evaluation metrics with 95 % confidence intervals (SPEC 11.5, 9.7)."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

import numpy as np

VERDICTS = ["VERIFIED", "CONTRADICTED", "INCONCLUSIVE", None]
CLASSES = ["authentic-with-mains-light", "authentic-without-mains-light", "edited", "synthetic"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    """Proportion with Wilson score 95 % interval."""
    if n == 0:
        return None, None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def rate(k: int, n: int) -> dict[str, Any]:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "ci95": [lo, hi]}


def confusion(recs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = {c: {str(v): 0 for v in VERDICTS} for c in CLASSES}
    for r in recs:
        m.setdefault(r["class"], {str(v): 0 for v in VERDICTS})[str(r.get("verdict"))] += 1
    return m


def summarize(recs: list[dict[str, Any]]) -> dict[str, Any]:
    auth = [r for r in recs if r["class"].startswith("authentic")]
    mains = [r for r in recs if r["class"] == "authentic-with-mains-light"]
    edited = [r for r in recs if r["class"] == "edited"]
    out: dict[str, Any] = {"n_clips": len(recs), "confusion": confusion(recs)}
    out["false_contradicted_rate"] = rate(sum(r.get("verdict") == "CONTRADICTED" for r in auth), len(auth))
    out["verified_coverage_mains"] = rate(sum(r.get("verdict") == "VERIFIED" for r in mains), len(mains))
    by_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        by_cond[r["condition"]].append(r)
    out["per_condition"] = {c: {"n": len(v), "verified": rate(sum(x.get("verdict") == "VERIFIED" for x in v), len(v)),
                                "inconclusive": rate(sum(x.get("verdict") == "INCONCLUSIVE" for x in v), len(v)),
                                "contradicted": rate(sum(x.get("verdict") == "CONTRADICTED" for x in v), len(v)),
                                "task_success": rate(sum(x.get("verdict") == x["expected_verdict"] for x in v), len(v))}
                            for c, v in sorted(by_cond.items())}
    te = [abs(r["time_error_s"]) for r in recs if r.get("verdict") == "VERIFIED" and r.get("time_error_s") is not None]
    out["time_error_verified_s"] = _dist(te)
    out["enf_rmse_mhz"] = _dist([r["enf_rmse_mhz"] for r in recs if r.get("enf_rmse_mhz") is not None])
    out["edit_detection"] = rate(sum(bool(r.get("edit_detected")) for r in edited), len(edited))
    loc = [e for r in edited for e in (r.get("edit_localization_error_s") or [])]
    out["edit_localization_error_s"] = _dist(loc)
    dropped = [r for r in recs if r["condition"] == "dropped_frames"]
    out["dropped_frame_false_alarm"] = rate(sum(bool(r.get("dropped_false_alarm")) for r in dropped), len(dropped))
    contra = [r for r in recs if r.get("verdict") == "CONTRADICTED"]
    ag = [r["agent"] for r in recs if r.get("agent")]
    first_weak = [a for a in ag if a["first_extraction_weak"]]
    out["agent"] = {
        "task_success": rate(sum(r.get("verdict") == r["expected_verdict"] for r in recs), len(recs)),
        "recovery_rate": rate(sum(a["recovered_signal"] for a in first_weak), len(first_weak)),
        "tool_calls_per_job": _dist([a["tool_calls"] for a in ag]),
        "unnecessary_call_rate": rate(sum(a["unnecessary_calls"] for a in ag), sum(a["tool_calls"] for a in ag)),
        "human_review_precision": rate(sum(r["class"] == "edited" for r in contra), len(contra)),
        "budget_exhaustion_rate": rate(sum(a["budget_exhausted"] for a in ag), len(ag)),
        "user_input_requests": dict(Counter(k for a in ag for k in a["user_input_requested"])),
    }
    stages: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        for k, v in (r.get("stage_timings_s") or {}).items():
            stages[k].append(float(v))
    out["runtime_per_stage_s"] = {k: _dist(v) for k, v in sorted(stages.items())}
    out["errors"] = [{"name": r["name"], "error": r["error"]} for r in recs if r.get("error")]
    return out


def _dist(x: list[float]) -> dict[str, Any]:
    if not x:
        return {"n": 0}
    a = np.asarray(x, dtype=np.float64)
    return {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)),
            "p95": float(np.percentile(a, 95)), "max": float(a.max())}
