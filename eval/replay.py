"""Re-derive S13 inputs from raw per-clip statistics under candidate thresholds.

Used by `calibrate_thresholds.py` so threshold search does not re-run the engine. `tests` check that a
replay with the thresholds used in the run reproduces the engine verdict.
"""

from __future__ import annotations

from typing import Any

from gridprint_engine.schemas import Reason
from gridprint_engine.verdict import VerdictInputs, decide


def raw_from_job(job: Any) -> dict[str, Any]:
    """Collect the threshold-independent statistics of a finished job."""
    tr = job.primary_track()
    raw: dict[str, Any] = {"persistent_reasons": sorted(r.value for r in job.reasons)}
    if tr is None:
        return raw
    raw["band_snr_db"] = tr.snr_db
    raw["axis_ambiguous"] = Reason.AXIS_AMBIGUOUS in tr.reasons
    m = job.matches.get(tr.id)
    if m is not None:
        ms, reasons, _ = m
        raw["match"] = {"rho1": ms.rho1, "rho2": ms.rho2, "margin": ms.margin, "length_s": ms.track_length_s,
                        "best_offset_utc": ms.best_offset_utc, "coverage": Reason.NO_REFERENCE_COVERAGE not in reasons,
                        "segment_stats": [{"rho1": s.rho1, "offset": s.offset_s, "margin": s.margin}
                                          for s in ms.segments]}
    c = job.continuity.get(tr.id)
    if c is not None:
        raw["boundaries"] = c.boundaries
    return raw


def replay(raw: dict[str, Any], thr: dict[str, Any], seg_tolerance_s: float, claim: dict[str, Any] | None = None,
           claim_tol_default_s: float = 60.0) -> tuple[str, list[str]]:
    reasons = {Reason(r) for r in raw.get("persistent_reasons", [])}
    if "band_snr_db" not in raw:
        out = decide(VerdictInputs(reasons=reasons))
        return out.verdict.value, [r.value for r in out.reasons]
    snr = raw["band_snr_db"]
    if snr < thr["signal"]["snr_absent_db"]:
        reasons.add(Reason.SIGNAL_ABSENT)
    elif snr < thr["signal"]["snr_weak_db"]:
        reasons.add(Reason.SIGNAL_WEAK)
    if raw.get("axis_ambiguous"):
        reasons.add(Reason.AXIS_AMBIGUOUS)
    match_passes = False
    within = None
    m = raw.get("match")
    if m is not None and Reason.SIGNAL_ABSENT not in reasons:
        if not m.get("coverage", True):
            reasons.add(Reason.NO_REFERENCE_COVERAGE)
        elif m.get("rho1") is not None:
            mt = thr["match"]
            margin = m["margin"]
            if m["length_s"] < mt["min_track_s"]:
                reasons.add(Reason.TRACK_TOO_SHORT)
            elif m["rho1"] < mt["rho1_min"] or margin < mt["margin_min"]:
                reasons.add(Reason.NO_UNIQUE_MATCH)
            else:
                match_passes = True
                reasons.add(Reason.MATCH_OK)
            segs = [s for s in m.get("segment_stats", []) if s.get("rho1") is not None
                    and s["rho1"] >= mt["rho1_min"] and (s.get("margin") or 0) >= mt["margin_min"]
                    and s.get("offset") is not None]
            if len(segs) >= 2:
                offs = [s["offset"] for s in segs]
                if max(offs) - min(offs) > seg_tolerance_s:
                    reasons.add(Reason.SEGMENT_OFFSET_INCONSISTENT)
            if claim and claim.get("claimed_time_utc") is not None and m.get("best_offset_utc") is not None:
                tol = claim.get("claimed_time_tolerance_s") or claim_tol_default_s
                within = abs(m["best_offset_utc"] - claim["claimed_time_utc"]) <= tol
    ct = thr["continuity"]
    sig_edit = False
    explained = False
    for b in raw.get("boundaries", []):
        significant = b["z"] > ct["edit_significance_sigma"] and b["rad"] >= ct["edit_min_rad"]
        if significant:
            sig_edit = True
        elif b["gap"]:
            explained = True
    if sig_edit:
        reasons.add(Reason.EDIT_CANDIDATE)
    if explained:
        reasons.add(Reason.DROPPED_FRAMES_EXPLAINED)
    out = decide(VerdictInputs(reasons=reasons, match_passes=match_passes,
                               claim_present=bool(claim and claim.get("claimed_time_utc") is not None),
                               claim_within_tolerance=within, significant_edit=sig_edit))
    return out.verdict.value, [r.value for r in out.reasons]
