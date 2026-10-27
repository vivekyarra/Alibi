"""Agent policies enforced in code, not only in the prompt (SPEC 9.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANALYSIS_TOOLS = {"probe_video", "estimate_readout", "analyze_motion", "propose_patches", "extract_flicker",
                  "match_reference", "check_continuity", "face_region_check"}
POST_VERDICT_TOOLS = {"request_human_review", "render_report", "request_user_input"}
ALL_TOOLS = ANALYSIS_TOOLS | POST_VERDICT_TOOLS | {"compute_verdict"}
# arguments the agent may pass per tool; anything else (e.g. thresholds, verdicts) is dropped
ALLOWED_ARGS = {
    "probe_video": set(), "estimate_readout": {"method"}, "analyze_motion": {"strictness"},
    "propose_patches": {"strategy"}, "extract_flicker": {"patch_ids", "axis", "nominal_hz", "frame_subset"},
    "match_reference": {"track_id", "zone", "window"}, "check_continuity": {"track_id"},
    "face_region_check": {"track_id"}, "compute_verdict": set(), "request_user_input": {"kind", "message"},
    "request_human_review": set(), "render_report": {"final"},
}


def _zones() -> set[str]:
    try:
        from pathlib import Path

        import yaml

        p = Path(__file__).resolve().parents[1] / "config" / "zones.yaml"
        return {z["id"] for z in yaml.safe_load(p.read_text())["zones"]}
    except Exception:  # config missing: accept no zone argument
        return set()


# allowed values per argument; a value outside the set is dropped (the engine default applies)
ALLOWED_VALUES: dict[str, Any] = {
    "method": {"auto", "sidecar", "profile", "blind"}, "strictness": {"normal", "strict"},
    "strategy": {"all", "top", "coherent", "bright"}, "axis": {"rows+", "rows-", "cols+", "cols-"},
    "nominal_hz": {50, 60}, "kind": {"original_file", "camera_model", "claimed_time", "longer_clip"},
    "final": {True, False}, "zone": _zones(),
}


def _valid(k: str, v: Any) -> bool:
    if k in ALLOWED_VALUES:
        try:
            return v in ALLOWED_VALUES[k]
        except TypeError:
            return False
    if k == "patch_ids":
        return isinstance(v, list) and all(isinstance(i, int) for i in v)
    if k == "frame_subset":
        return v == "low_motion" or (isinstance(v, list) and all(isinstance(i, int) for i in v))
    return isinstance(v, str | int | float) or v is None


@dataclass
class Action:
    tool: str | None  # None = planner wants to stop
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class PolicyState:
    max_iterations: int
    max_tool_calls: int
    tool_calls: int = 0
    iterations: int = 0  # extract_flicker calls
    verdict: str | None = None
    verdict_done: bool = False
    review_requested: bool = False
    report_done: bool = False
    budget_exhausted: bool = False


def enforce(a: Action, st: PolicyState) -> tuple[Action, str | None]:
    """Return the action to execute and a note when the policy changed it."""
    if a.tool is None:
        if not st.verdict_done:
            return Action("compute_verdict", {}, "policy: compute_verdict is required before stopping"), \
                "stop before verdict"
        if st.verdict == "CONTRADICTED" and not st.review_requested:
            return Action("request_human_review", {}, "policy: CONTRADICTED requires human review (B6)"), \
                "review required"
        if not st.report_done:
            return Action("render_report", {"final": st.verdict != "CONTRADICTED"},
                          "policy: report must be rendered"), "report required"
        return a, None
    if a.tool not in ALL_TOOLS:
        if st.verdict_done:
            nxt, _ = enforce(Action(None, {}, ""), st)
            nxt.reason = f"policy: unknown tool {a.tool} rejected; " + (nxt.reason or "job complete")
            return nxt, f"unknown tool {a.tool}"
        return Action("compute_verdict", {}, "policy: unknown tool rejected"), f"unknown tool {a.tool}"
    note = None
    args = {k: v for k, v in a.args.items() if k in ALLOWED_ARGS[a.tool] and _valid(k, v)}
    if args != {k: v for k, v in a.args.items() if k != "job_id"}:
        note = "policy: disallowed arguments removed"
    a = Action(a.tool, args, a.reason)
    if st.tool_calls >= st.max_tool_calls - 3 and not st.verdict_done:
        st.budget_exhausted = True
        return Action("compute_verdict", {}, "policy: tool-call budget exhausted (B5)"), "budget exhausted"
    if a.tool == "extract_flicker" and st.iterations >= st.max_iterations:
        st.budget_exhausted = True
        return Action("compute_verdict", {}, "policy: iteration budget exhausted (B5)"), "iteration budget"
    if st.verdict_done and a.tool in ANALYSIS_TOOLS | {"compute_verdict"}:
        nxt, _ = enforce(Action(None, {}, ""), st)  # finish the job: review if needed, then the report
        nxt.reason = f"policy: {a.tool} after the verdict is not allowed; " + (nxt.reason or "job complete")
        return nxt, f"{a.tool} after verdict blocked"
    if a.tool == "render_report":
        if not st.verdict_done:
            return Action("compute_verdict", {}, "policy: verdict before report"), "report before verdict"
        if st.verdict == "CONTRADICTED":
            if not st.review_requested:
                return Action("request_human_review", {}, "policy: CONTRADICTED requires human review (B6)"), \
                    "review before report"
            if a.args.get("final", True):
                return Action("render_report", {"final": False}, a.reason), "FINAL blocked for PENDING_REVIEW"
    if a.tool == "request_human_review" and st.verdict != "CONTRADICTED":
        return Action(None, {}, "policy: review only for CONTRADICTED"), "review blocked"
    return a, note


def record(a: Action, result: Any, st: PolicyState) -> None:
    st.tool_calls += 1
    if a.tool == "extract_flicker":
        st.iterations += 1
    if a.tool == "compute_verdict" and isinstance(result, dict):
        st.verdict_done = True
        st.verdict = result.get("verdict")
    if a.tool == "request_human_review":
        st.review_requested = True
    if a.tool == "render_report":
        st.report_done = True
