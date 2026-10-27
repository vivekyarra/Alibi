"""Agent behaviors B1–B6, policies and trace (SPEC 9.3–9.5, R10). Tool outputs come from a scripted test
double; the real engine path is covered by engine and integration tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agent import policies
from agent.fallback_planner import FallbackPlanner
from agent.orchestrator import run_job
from agent.planner_bedrock import BedrockPlanner, tool_config
from agent.policies import Action, PolicyState

WEAK = {"track_id": "t1", "band_snr_db": 5.0, "reasons": ["SIGNAL_WEAK"], "axis": "rows+",
        "nominal_flicker_hz": 100.0}
GOOD = {"track_id": "t2", "band_snr_db": 14.0, "reasons": [], "axis": "rows+", "nominal_flicker_hz": 100.0}
ABSENT = {"track_id": "t1", "band_snr_db": -12.0, "reasons": ["SIGNAL_ABSENT"], "axis": "rows+",
          "nominal_flicker_hz": 100.0}


class ScriptedTools:
    """Test double for the MCP tool server."""

    def __init__(self, **over: Any):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.over = over
        self.extracts = 0

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, args))
        o = self.over
        if tool == "probe_video":
            return o.get("probe", {"hdr": False, "high_compression": False})
        if tool == "estimate_readout":
            return o.get("readout", {"source": "READOUT_FROM_SIDECAR", "readout_s": 0.025, "low_confidence": False})
        if tool == "analyze_motion":
            if args.get("strictness") == "strict":
                return {"high_motion": False, "motion_level": 0.4}
            return o.get("motion", {"high_motion": False, "motion_level": 0.1})
        if tool == "propose_patches":
            return {"selected": [1, 2, 3] if args.get("strategy") == "top" else list(range(20))}
        if tool == "extract_flicker":
            self.extracts += 1
            seq = o.get("extracts", [GOOD])
            return seq[min(self.extracts - 1, len(seq) - 1)]
        if tool == "match_reference":
            return {"passes": True}
        if tool == "check_continuity":
            return {"events": []}
        if tool == "face_region_check":
            return {"status": "no_faces"}
        if tool == "compute_verdict":
            return {"verdict": o.get("verdict", "VERIFIED"), "reasons": []}
        if tool in ("request_user_input", "request_human_review", "render_report"):
            return {"ok": True}
        raise AssertionError(tool)


def run(tools: ScriptedTools, planner: Any = None, max_iter: int = 6, max_calls: int = 30):
    return asyncio.run(run_job("j1", planner or FallbackPlanner(), tools, max_iter, max_calls))


def tools_called(t: ScriptedTools) -> list[str]:
    return [c[0] for c in t.calls]


def test_happy_path_order_and_trace():
    t = ScriptedTools()
    trace, _ = run(t)
    names = tools_called(t)
    assert names[:3] == ["probe_video", "estimate_readout", "analyze_motion"]
    assert names.index("compute_verdict") > names.index("check_continuity")
    assert names[-1] == "render_report" and t.calls[-1][1]["final"] is True
    for st in trace.steps:  # R10: every step traced
        assert st.tool and st.t_start and st.t_end and st.decision_reason and st.planner == "fallback"
        json.loads(st.input_summary)


def test_b1_weak_signal_reselects_patches_and_reextracts():
    t = ScriptedTools(extracts=[WEAK, GOOD])
    trace, _ = run(t)
    names = tools_called(t)
    i = names.index("propose_patches", names.index("extract_flicker"))
    assert t.calls[i][1]["strategy"] == "top"
    assert names.count("extract_flicker") == 2
    assert t.calls[names.index("extract_flicker", i)][1]["patch_ids"] == [1, 2, 3]
    assert any("B1" in s.decision_reason for s in trace.steps)
    # the later match uses the new (stronger) track
    assert t.calls[names.index("match_reference")][1]["track_id"] == "t2"


def test_b1_tries_other_nominal_and_axis_then_b5():
    t = ScriptedTools(extracts=[ABSENT], verdict="INCONCLUSIVE")
    trace, _ = run(t)
    ex = [c[1] for c in t.calls if c[0] == "extract_flicker"]
    assert any(e.get("nominal_hz") == 60.0 for e in ex)
    assert any(e.get("axis") == "cols+" for e in ex)
    assert "match_reference" not in tools_called(t)
    assert any("B5" in s.decision_reason for s in trace.steps)
    assert tools_called(t)[-2:] == ["compute_verdict", "render_report"]


def test_b2_unknown_readout_requests_camera_model():
    t = ScriptedTools(readout={"source": "READOUT_UNKNOWN", "readout_s": None}, verdict="INCONCLUSIVE")
    run(t)
    req = [c[1] for c in t.calls if c[0] == "request_user_input"]
    assert req and req[0]["kind"] == "camera_model"
    assert "extract_flicker" not in tools_called(t)


def test_b2_low_confidence_requests_camera_model_and_continues():
    t = ScriptedTools(readout={"source": "READOUT_ESTIMATED", "readout_s": 0.02, "low_confidence": True,
                               "confidence": 0.2})
    run(t)
    assert any(c[0] == "request_user_input" and c[1]["kind"] == "camera_model" for c in t.calls)
    assert "extract_flicker" in tools_called(t)


def test_b3_high_motion_strict_and_low_motion_frames():
    t = ScriptedTools(motion={"high_motion": True, "motion_level": 2.0})
    run(t)
    assert ("analyze_motion", {"job_id": "j1", "strictness": "strict"}) in t.calls
    ex = next(c[1] for c in t.calls if c[0] == "extract_flicker")
    assert ex["frame_subset"] == "low_motion"


def test_b4_high_compression_weak_requests_original():
    t = ScriptedTools(probe={"hdr": False, "high_compression": True}, extracts=[WEAK, GOOD])
    run(t)
    assert any(c[0] == "request_user_input" and c[1]["kind"] == "original_file" for c in t.calls)


def test_b6_contradicted_requests_review_and_no_final_report():
    t = ScriptedTools(verdict="CONTRADICTED")
    run(t)
    names = tools_called(t)
    assert names.index("request_human_review") > names.index("compute_verdict")
    assert t.calls[-1] == ("render_report", {"job_id": "j1", "final": False})


def test_policy_blocks_final_report_for_contradicted_and_analysis_after_verdict():
    st = PolicyState(max_iterations=6, max_tool_calls=30, verdict_done=True, verdict="CONTRADICTED")
    a, note = policies.enforce(Action("render_report", {"final": True}, "x"), st)
    assert a.tool == "request_human_review"
    st.review_requested = True
    a, note = policies.enforce(Action("render_report", {"final": True}, "x"), st)
    assert a.tool == "render_report" and a.args["final"] is False and note
    a, _ = policies.enforce(Action("extract_flicker", {}, "x"), st)
    assert a.tool == "render_report" and a.args["final"] is False  # no analysis after the verdict


def test_policy_strips_threshold_arguments():
    st = PolicyState(max_iterations=6, max_tool_calls=30)
    a, note = policies.enforce(Action("extract_flicker", {"snr_weak_db": -50, "axis": "rows+"}, "x"), st)
    assert a.args == {"axis": "rows+"} and note


def test_budget_exhausted():
    t = ScriptedTools(extracts=[ABSENT], verdict="INCONCLUSIVE")
    trace, _ = run(t, max_iter=2)
    assert sum(1 for c in t.calls if c[0] == "extract_flicker") == 2
    cv = next(c for c in t.calls if c[0] == "compute_verdict")
    assert cv[1].get("budget_exhausted") is True
    assert any("budget" in s.decision_reason for s in trace.steps)


class FakeBedrock:
    """Test double for the bedrock-runtime client."""

    def __init__(self, script: list[dict[str, Any]]):
        self.script = script
        self.requests: list[dict[str, Any]] = []

    def converse(self, **kw: Any) -> dict[str, Any]:
        self.requests.append(kw)
        step = self.script[min(len(self.requests) - 1, len(self.script) - 1)]
        return {"output": {"message": {"content": [{"text": step.get("why", "")},
                                                   {"toolUse": {"toolUseId": "x", "name": step["tool"],
                                                                "input": step.get("input", {})}}]}}}


def test_bedrock_planner_is_policed():
    script = [{"tool": "probe_video"}, {"tool": "compute_verdict", "why": "skip ahead"},
              {"tool": "render_report", "input": {"final": True}}, {"tool": "stop"}]
    client = FakeBedrock(script)
    t = ScriptedTools(verdict="CONTRADICTED")
    trace, _ = run(t, BedrockPlanner(client, "test-model"))
    assert tools_called(t) == ["probe_video", "compute_verdict", "request_human_review", "render_report"]
    assert t.calls[-1][1]["final"] is False
    assert all(s.planner == "bedrock" and s.model_id == "test-model" for s in trace.steps)
    req = client.requests[0]
    assert req["modelId"] == "test-model" and "toolConfig" in req
    assert "guaranteed" in req["system"][0]["text"]  # forbidden-claims list is in the prompt (9.4)


def test_tool_config_lists_all_tools():
    names = {t["toolSpec"]["name"] for t in tool_config()["tools"]}
    assert policies.ALL_TOOLS <= names


class FailingProbeTools(ScriptedTools):
    """probe_video fails once, then succeeds."""

    def __init__(self) -> None:
        super().__init__()
        self.probe_failed = False

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool == "probe_video" and not self.probe_failed:
            self.calls.append((tool, args))
            self.probe_failed = True
            raise RuntimeError("Unable to allocate memory")
        return await super().call(tool, args)


def test_llm_guard_replaces_repeated_failures_and_out_of_order_calls():
    # an LLM that ignores errors: always asks for motion analysis
    client = FakeBedrock([{"tool": "analyze_motion", "input": {"strictness": "normal"}}])
    t = FailingProbeTools()
    trace, _ = run(t, BedrockPlanner(client, "test-model"))
    names = tools_called(t)
    assert names[0] == "probe_video" and names[1] == "compute_verdict"  # guard: unreadable input ends the job
    assert any("guard:" in s.decision_reason for s in trace.steps)
    assert names.count("analyze_motion") <= 2  # the repeated call is not retried endlessly
    assert names[-1] == "render_report"  # the job always ends with a report


def test_llm_guard_blocks_premature_overrides_and_identical_repeats():
    script = [{"tool": "probe_video"}, {"tool": "estimate_readout", "input": {"method": "auto"}},
              {"tool": "analyze_motion", "input": {"strictness": "normal"}},
              {"tool": "propose_patches", "input": {"strategy": "top"}},
              {"tool": "extract_flicker", "input": {"nominal_hz": 60}},
              {"tool": "propose_patches", "input": {"strategy": "top"}}]
    client = FakeBedrock(script)
    t = ScriptedTools()
    trace, _ = run(t, BedrockPlanner(client, "test-model"))
    ex = [a for n, a in t.calls if n == "extract_flicker"]
    assert ex and "nominal_hz" not in ex[0]  # the first extraction used the zone default
    assert sum(1 for n, a in t.calls if n == "propose_patches" and a.get("strategy") == "top") <= 1
    assert any("frequency or axis override" in s.decision_reason for s in trace.steps)
    assert t.calls[-1][0] == "render_report"


def test_policy_after_verdict_finishes_with_report():
    st = PolicyState(max_iterations=6, max_tool_calls=30, verdict_done=True, verdict="INCONCLUSIVE")
    a, note = policies.enforce(Action("compute_verdict", {}, "again"), st)
    assert a.tool == "render_report" and a.args["final"] is True and note
    st2 = PolicyState(max_iterations=6, max_tool_calls=30, verdict_done=True, verdict="CONTRADICTED")
    a, _ = policies.enforce(Action("match_reference", {}, "late"), st2)
    assert a.tool == "request_human_review"


def test_policy_drops_invalid_argument_values():
    st = PolicyState(max_iterations=6, max_tool_calls=30)
    a, note = policies.enforce(Action("match_reference", {"track_id": "t1", "zone": "global"}, "x"), st)
    assert a.args == {"track_id": "t1"} and note
    a, _ = policies.enforce(Action("extract_flicker", {"nominal_hz": 55, "axis": "diagonal"}, "x"), st)
    assert a.args == {}
    a, _ = policies.enforce(Action("match_reference", {"zone": "SIM50"}, "x"), st)
    assert a.args == {"zone": "SIM50"}
    st.verdict_done, st.verdict = True, "INCONCLUSIVE"
    a, _ = policies.enforce(Action("render", {}, "x"), st)
    assert a.tool == "render_report"


def test_restarting_caller_restarts_lost_server_and_retries_once():
    import asyncio

    from agent.orchestrator import ConnectionLost, RestartingMcpCaller

    class Dead:
        async def call(self, tool, args):
            raise ConnectionLost("Connection closed")

    class Alive:
        async def call(self, tool, args):
            return {"tool": tool}

    servers = [Dead(), Alive()]
    c = RestartingMcpCaller(params=None)  # type: ignore[arg-type]

    async def start():
        c.caller = servers.pop(0)
        return c.caller

    c._start = start  # type: ignore[method-assign]
    assert asyncio.run(c.call("analyze_motion", {"job_id": "j"})) == {"tool": "analyze_motion"}
    assert c.restarts == 1

    servers[:] = [Dead(), Dead()]
    c.caller = None
    try:
        asyncio.run(c.call("analyze_motion", {"job_id": "j"}))
        raise AssertionError("expected ConnectionLost")
    except ConnectionLost:
        pass
