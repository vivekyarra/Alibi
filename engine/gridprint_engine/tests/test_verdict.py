"""S13 verdict rules and R1–R3, R9 (SPEC 8.14, Part 2)."""

from __future__ import annotations

import pytest
from gridprint_engine.schemas import LifecycleState, Reason, Verdict
from gridprint_engine.verdict import VerdictInputs, apply_review, decide, finalize_without_review


def test_r1_exactly_three_verdicts():
    assert {v.value for v in Verdict} == {"VERIFIED", "CONTRADICTED", "INCONCLUSIVE"}


@pytest.mark.parametrize("stop", [Reason.HDR_UNSUPPORTED, Reason.READOUT_UNKNOWN, Reason.SIGNAL_ABSENT])
def test_rule1_stop_reasons_inconclusive(stop):
    out = decide(VerdictInputs(reasons={stop, Reason.SEGMENT_OFFSET_INCONSISTENT}, match_passes=True,
                               significant_edit=True))
    assert out.verdict == Verdict.INCONCLUSIVE and out.rule == "S13.1"


def test_r2_absence_never_contradicted():
    for extra in [set(), {Reason.EDIT_CANDIDATE}, {Reason.SEGMENT_OFFSET_INCONSISTENT}]:
        out = decide(VerdictInputs(reasons={Reason.SIGNAL_ABSENT} | extra, significant_edit=True,
                                   claim_present=True, claim_within_tolerance=False, match_passes=True))
        assert out.verdict != Verdict.CONTRADICTED


def test_rule2_edit_with_strong_signal():
    out = decide(VerdictInputs(reasons={Reason.EDIT_CANDIDATE}, significant_edit=True))
    assert out.verdict == Verdict.CONTRADICTED and out.state == LifecycleState.PENDING_REVIEW and out.rule == "S13.2"
    out = decide(VerdictInputs(reasons={Reason.SEGMENT_OFFSET_INCONSISTENT}, match_passes=True))
    assert out.verdict == Verdict.CONTRADICTED


def test_rule2_needs_strong_signal():
    out = decide(VerdictInputs(reasons={Reason.SIGNAL_WEAK, Reason.EDIT_CANDIDATE}, significant_edit=True))
    assert out.verdict == Verdict.INCONCLUSIVE


def test_rule3_claim_mismatch():
    out = decide(VerdictInputs(reasons={Reason.MATCH_OK}, match_passes=True, claim_present=True,
                               claim_within_tolerance=False))
    assert out.verdict == Verdict.CONTRADICTED and Reason.CLAIM_TIME_MISMATCH in out.reasons
    assert out.rule == "S13.3" and out.state == LifecycleState.PENDING_REVIEW


def test_rule4_verified():
    out = decide(VerdictInputs(reasons={Reason.MATCH_OK}, match_passes=True))
    assert out.verdict == Verdict.VERIFIED and out.rule == "S13.4"
    out = decide(VerdictInputs(reasons={Reason.MATCH_OK, Reason.DROPPED_FRAMES_EXPLAINED}, match_passes=True,
                               claim_present=True, claim_within_tolerance=True))
    assert out.verdict == Verdict.VERIFIED and Reason.CLAIM_TIME_MATCH in out.reasons


def test_rule5_everything_else():
    out = decide(VerdictInputs(reasons={Reason.NO_UNIQUE_MATCH}))
    assert out.verdict == Verdict.INCONCLUSIVE and out.rule == "S13.5"


def test_r9_face_anomaly_alone_never_contradicted():
    out = decide(VerdictInputs(reasons={Reason.MATCH_OK}, match_passes=True, face_anomaly=True))
    assert out.verdict == Verdict.VERIFIED
    assert Reason.FACE_REGION_ANOMALY_EXPERIMENTAL in out.reasons
    out = decide(VerdictInputs(reasons=set(), face_anomaly=True))
    assert out.verdict == Verdict.INCONCLUSIVE


def test_r3_contradicted_needs_review_before_final():
    out = decide(VerdictInputs(reasons={Reason.EDIT_CANDIDATE}, significant_edit=True))
    assert finalize_without_review(out.verdict, out.state) == LifecycleState.PENDING_REVIEW
    v, st, rs = apply_review(out.verdict, out.state, True, out.reasons)
    assert (v, st) == (Verdict.CONTRADICTED, LifecycleState.FINAL) and Reason.REVIEWER_APPROVED in rs
    v, st, rs = apply_review(out.verdict, out.state, False, out.reasons)
    assert (v, st) == (Verdict.INCONCLUSIVE, LifecycleState.FINAL) and Reason.REVIEWER_REJECTED in rs


def test_review_only_for_pending_contradicted():
    with pytest.raises(ValueError):
        apply_review(Verdict.VERIFIED, LifecycleState.DRAFT, True, [])


def test_verified_goes_final_without_review():
    assert finalize_without_review(Verdict.VERIFIED, LifecycleState.DRAFT) == LifecycleState.FINAL


def test_r4_schema_has_no_location_beyond_zone():
    from gridprint_engine.schemas import AnalysisResult, CaptureSidecar

    fields = set(AnalysisResult.model_fields) | set(CaptureSidecar.model_fields)
    for bad in ("lat", "lon", "latitude", "longitude", "gps", "location", "city", "address"):
        assert not any(bad in f for f in fields)
