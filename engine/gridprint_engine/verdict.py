"""Stage S13 — deterministic verdict logic (SPEC 8.14, R1–R3, R9).

The agent cannot call anything here except through `compute_verdict` (MCP tool), and it cannot
change the result. Only a reviewer decision changes the lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gridprint_engine.schemas import LifecycleState, Reason, Verdict

STOP_REASONS = {Reason.HDR_UNSUPPORTED, Reason.READOUT_UNKNOWN, Reason.SIGNAL_ABSENT}


@dataclass
class VerdictInputs:
    reasons: set[Reason]
    match_passes: bool = False
    claim_present: bool = False
    claim_within_tolerance: bool | None = None
    significant_edit: bool = False  # EDIT_CANDIDATE with significance above threshold
    face_anomaly: bool = False  # experimental; never used for CONTRADICTED (R9)
    extra_notes: list[str] = field(default_factory=list)


@dataclass
class VerdictOutput:
    verdict: Verdict
    state: LifecycleState
    reasons: list[Reason]
    rule: str


def decide(inp: VerdictInputs) -> VerdictOutput:
    r = set(inp.reasons)
    if inp.claim_present and inp.match_passes and inp.claim_within_tolerance is not None:
        r.add(Reason.CLAIM_TIME_MATCH if inp.claim_within_tolerance else Reason.CLAIM_TIME_MISMATCH)
    if inp.face_anomaly:
        r.add(Reason.FACE_REGION_ANOMALY_EXPERIMENTAL)
    ordered = sorted(r, key=lambda x: list(Reason).index(x))

    # Rule 1
    if r & STOP_REASONS:
        return VerdictOutput(Verdict.INCONCLUSIVE, LifecycleState.DRAFT, ordered, "S13.1")
    strong = Reason.SIGNAL_WEAK not in r
    # Rule 2 — face-region evidence is deliberately not an input here (R9)
    if strong and (inp.significant_edit or Reason.SEGMENT_OFFSET_INCONSISTENT in r):
        return VerdictOutput(Verdict.CONTRADICTED, LifecycleState.PENDING_REVIEW, ordered, "S13.2")
    # Rule 3
    if inp.claim_present and inp.match_passes and inp.claim_within_tolerance is False:
        return VerdictOutput(Verdict.CONTRADICTED, LifecycleState.PENDING_REVIEW, ordered, "S13.3")
    # Rule 4
    claim_ok = (not inp.claim_present) or (Reason.CLAIM_TIME_MATCH in r)
    if inp.match_passes and not inp.significant_edit and claim_ok:
        return VerdictOutput(Verdict.VERIFIED, LifecycleState.DRAFT, ordered, "S13.4")
    # Rule 5
    return VerdictOutput(Verdict.INCONCLUSIVE, LifecycleState.DRAFT, ordered, "S13.5")


def apply_review(verdict: Verdict, state: LifecycleState, approve: bool,
                 reasons: list[Reason]) -> tuple[Verdict, LifecycleState, list[Reason]]:
    """Reviewer decision on a PENDING_REVIEW report (SPEC 1.5)."""
    if state != LifecycleState.PENDING_REVIEW or verdict != Verdict.CONTRADICTED:
        raise ValueError("only a CONTRADICTED report in PENDING_REVIEW can be reviewed")
    if approve:
        return Verdict.CONTRADICTED, LifecycleState.FINAL, [*reasons, Reason.REVIEWER_APPROVED]
    return Verdict.INCONCLUSIVE, LifecycleState.FINAL, [*reasons, Reason.REVIEWER_REJECTED]


def finalize_without_review(verdict: Verdict, state: LifecycleState) -> LifecycleState:
    """VERIFIED / INCONCLUSIVE reports go DRAFT → FINAL. CONTRADICTED never does (R3)."""
    if verdict == Verdict.CONTRADICTED:
        return state
    return LifecycleState.FINAL
