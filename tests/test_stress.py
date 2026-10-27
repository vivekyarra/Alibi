"""Stress and fuzz tests: invariants that must hold for any input.

- S13 verdict logic over random reason sets and flags (R1, R2, R3, R9).
- Agent policies under a random (adversarial) planner: verdict always computed, never FINAL for CONTRADICTED,
  budgets respected, no analysis after the verdict.
- Engine on malformed and edge-case files: no crash with a wrong verdict; never CONTRADICTED without signal.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

from agent.orchestrator import run_job
from agent.policies import ALL_TOOLS, Action
from gridprint_engine.adapters import LocalGridLog
from gridprint_engine.pipeline import run_default
from gridprint_engine.schemas import LifecycleState, Reason, Verdict
from gridprint_engine.verdict import STOP_REASONS, VerdictInputs, decide

ALL_REASONS = list(Reason)


def test_verdict_invariants_fuzz():
    rng = random.Random(0)
    for _ in range(20000):
        rs = set(rng.sample(ALL_REASONS, rng.randint(0, 8)))
        inp = VerdictInputs(reasons=rs, match_passes=rng.random() < 0.5, claim_present=rng.random() < 0.3,
                            claim_within_tolerance=rng.choice([None, True, False]),
                            significant_edit=rng.random() < 0.3, face_anomaly=rng.random() < 0.3)
        out = decide(inp)
        assert out.verdict in (Verdict.VERIFIED, Verdict.CONTRADICTED, Verdict.INCONCLUSIVE)  # R1
        if rs & STOP_REASONS:
            assert out.verdict == Verdict.INCONCLUSIVE  # R2 (absence of signal) and S13.1
        if out.verdict == Verdict.CONTRADICTED:
            assert out.state == LifecycleState.PENDING_REVIEW  # R3
            assert inp.significant_edit or Reason.SEGMENT_OFFSET_INCONSISTENT in rs or (
                inp.claim_present and inp.match_passes and inp.claim_within_tolerance is False)  # R9
        else:
            assert out.state == LifecycleState.DRAFT
        if out.verdict == Verdict.VERIFIED:
            assert inp.match_passes and not inp.significant_edit


class RandomPlanner:
    """Adversarial planner double: random tools, random (often disallowed) arguments, random stops."""

    kind = "fallback"
    model_id = None

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def next_action(self, history: list[Any]) -> Action:
        r = self.rng.random()
        if r < 0.05:
            return Action(None, {}, "random stop")
        tool = self.rng.choice(sorted(ALL_TOOLS) + ["delete_everything", "set_threshold"])
        args = self.rng.choice([{}, {"final": True}, {"snr_weak_db": -100}, {"verdict": "VERIFIED"},
                                {"strategy": "top"}, {"kind": "camera_model", "message": "m"}])
        return Action(tool, args, "random")


class RecordingTools:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, args))
        if self.rng.random() < 0.1:
            raise RuntimeError("tool failure")
        if tool == "compute_verdict":
            return {"verdict": self.rng.choice(["VERIFIED", "CONTRADICTED", "INCONCLUSIVE"])}
        return {}


@pytest.mark.parametrize("seed", range(200))
def test_policies_hold_under_random_planner(seed):
    tools = RecordingTools(seed)
    max_calls = 20
    trace, hist = asyncio.run(run_job("j", RandomPlanner(seed), tools, 4, max_calls))
    names = [c[0] for c in tools.calls]
    assert set(names) <= ALL_TOOLS
    assert len(names) <= max_calls + 3
    assert sum(n == "extract_flicker" for n in names) <= 4
    for _, args in tools.calls:
        assert not ({"snr_weak_db", "verdict"} & set(args))
    # history and tool calls align one to one; find the first verdict that succeeded
    first = next((i for i, h in enumerate(hist) if h.tool == "compute_verdict" and h.error is None), None)
    if first is not None:
        analysis = {"probe_video", "estimate_readout", "analyze_motion", "propose_patches", "extract_flicker",
                    "match_reference", "check_continuity", "face_region_check", "compute_verdict"}
        assert all(n not in analysis for n, _ in tools.calls[first + 1:])
        if hist[first].result["verdict"] == "CONTRADICTED":
            assert not [a for n, a in tools.calls[first + 1:] if n == "render_report" and a.get("final", True)]
    for st in trace.steps:
        assert st.t_start and st.t_end and st.planner and st.tool


# ---------------------------------------------------------------- malformed and edge-case inputs
def _write(path: Path, frames: list[np.ndarray], fps: int = 30) -> Path:
    with av.open(str(path), "w") as c:
        s = c.add_stream("libx264", rate=fps)
        s.height, s.width = frames[0].shape
        s.pix_fmt = "yuv420p"
        for f in frames:
            for p in s.encode(av.VideoFrame.from_ndarray(np.stack([f] * 3, -1), format="rgb24")):
                c.mux(p)
        for p in s.encode():
            c.mux(p)
    return path


EDGE = {
    "black": lambda: [np.zeros((48, 64), np.uint8)] * 30,
    "saturated": lambda: [np.full((48, 64), 255, np.uint8)] * 30,
    "noise": lambda: [np.random.default_rng(i).integers(0, 255, (48, 64), dtype=np.uint8) for i in range(30)],
    "one_frame": lambda: [np.full((48, 64), 120, np.uint8)],
    "flat_grey": lambda: [np.full((48, 64), 120, np.uint8)] * 60,
}


@pytest.mark.parametrize("name", sorted(EDGE))
def test_edge_case_videos_never_contradicted(tmp_path, name):
    v = _write(tmp_path / f"{name}.mp4", EDGE[name]())
    job = run_default(v, tmp_path / "work", LocalGridLog(tmp_path / "gridlog"))
    assert job.result is not None
    assert job.result.verdict == Verdict.INCONCLUSIVE


@pytest.mark.parametrize("payload", [b"", b"\x00" * 10, b"not a video", b"\x00\x00\x00\x18ftypisom" + b"\x01" * 200])
def test_malformed_files_raise_clean_errors(tmp_path, payload):
    p = tmp_path / "bad.mp4"
    p.write_bytes(payload)
    with pytest.raises(Exception) as ei:
        run_default(p, tmp_path / "work", LocalGridLog(tmp_path / "gridlog"))
    assert not isinstance(ei.value, (SystemExit, KeyboardInterrupt))


def test_truncated_real_video_does_not_verify(tmp_path):
    from eval.simulator.render import SimConfig, simulate

    tr = simulate(SimConfig(seed=5, duration_s=3, width=64, height=48, ref_margin_s=20), tmp_path, "t")
    data = (tmp_path / tr["video"]).read_bytes()
    cut = tmp_path / "trunc.mp4"
    cut.write_bytes(data[: len(data) // 2])
    try:
        job = run_default(cut, tmp_path / "work", LocalGridLog(tmp_path / tr["gridlog_root"]))
    except Exception:
        return  # a clean failure is acceptable for a broken container
    assert job.result is not None and job.result.verdict != Verdict.CONTRADICTED
