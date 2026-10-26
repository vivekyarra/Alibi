"""Run the evaluation: every clip goes through the real agent (fallback or Bedrock planner) and engine.

Outputs per clip JSON (verdict, reasons, errors vs ground truth, raw statistics for calibration, agent
metrics, stage timings) under results/eval/<date>/<suite>/<split>/. SPEC 11.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]

EXPECTED = {
    "authentic-with-mains-light": "VERIFIED",
    "authentic-without-mains-light": "INCONCLUSIVE",
    "edited": "CONTRADICTED",
    "synthetic": "INCONCLUSIVE",
}


def _agent_metrics(history: list[Any], trace: Any) -> dict[str, Any]:
    extracts = [s for s in history if s.tool == "extract_flicker" and s.result]
    first_weak = bool(extracts) and any(r in extracts[0].result.get("reasons", []) for r in
                                        ("SIGNAL_WEAK", "SIGNAL_ABSENT"))
    later_ok = any(not any(r in s.result.get("reasons", []) for r in ("SIGNAL_WEAK", "SIGNAL_ABSENT"))
                   for s in extracts[1:])
    seen: set[str] = set()
    repeated = 0
    for s in history:
        key = json.dumps([s.tool, s.args], sort_keys=True, default=str)
        repeated += key in seen
        seen.add(key)
    errors = sum(1 for s in history if s.error)
    blocked = sum(1 for st in trace.steps if st.policy_note)
    return {"tool_calls": len(history), "extractions": len(extracts), "first_extraction_weak": first_weak,
            "recovered_signal": bool(first_weak and later_ok), "unnecessary_calls": repeated + errors,
            "policy_interventions": blocked,
            "budget_exhausted": any("budget" in (st.decision_reason or "") for st in trace.steps),
            "user_input_requested": [s.args.get("kind") for s in history if s.tool == "request_user_input"],
            "review_requested": any(s.tool == "request_human_review" for s in history)}


def run_clip(item: dict[str, Any], data_dir: str, out_dir: str, planner_kind: str,
             threads: int = 0) -> dict[str, Any]:
    import sys

    import cv2

    if threads:
        cv2.setNumThreads(threads)  # avoid oversubscription when several clips run in parallel
    sys.path[:0] = [str(REPO), str(REPO / "engine")]
    from agent.fallback_planner import FallbackPlanner
    from agent.orchestrator import run_in_process
    from eval.replay import raw_from_job
    from gridprint_engine.adapters import LocalGridLog, LocalJobStore
    from gridprint_engine.config import settings
    from mcp_server.tools import EngineTools

    cfg = settings().default
    d = Path(data_dir)
    truth = json.loads((d / item["truth"]).read_text())
    work = Path(out_dir) / "work"
    job_id = item["name"]
    jd = work / job_id
    shutil.rmtree(jd, ignore_errors=True)
    jd.mkdir(parents=True)
    spec = {"video": str(d / item["video"]), "sidecar": str(d / item["sidecar"]) if item.get("sidecar") else None,
            "claim": item.get("claim") or {}}
    (jd / "job.json").write_text(json.dumps(spec))
    tools = EngineTools(work, LocalGridLog(d / truth.get("gridlog_root", "gridlog")), LocalJobStore(work / "store"))
    if planner_kind == "bedrock":
        from agent.planner_bedrock import BedrockPlanner, make_client

        planner: Any = BedrockPlanner(make_client(cfg["aws"]["profile"], cfg["aws"]["region"]),
                                      cfg["bedrock"]["model_id"], cfg["bedrock"]["max_tokens"])
    else:
        planner = FallbackPlanner()
    t0 = time.perf_counter()
    trace, history = run_in_process(job_id, planner, tools, cfg["agent"]["max_iterations"],
                                    cfg["agent"]["max_tool_calls"], jd / "trace.json")
    wall = time.perf_counter() - t0
    job = tools.jobs.get(job_id)
    res = job.result if job is not None else None
    rec: dict[str, Any] = {"name": job_id, "condition": item["condition"], "split": item["split"],
                           "label": item.get("label", ""), "class": item["class"],
                           "expected_verdict": EXPECTED[item["class"]], "planner": planner_kind,
                           "wall_s": wall, "truth_start_utc": truth["start_utc"],
                           "video_s": float(truth["frame_pts_s"][-1]) if truth.get("frame_pts_s") else None}
    if res is None:
        rec.update({"verdict": None, "error": "no result"})
        return rec
    rec.update({"verdict": res.verdict.value, "lifecycle_state": res.lifecycle_state.value,
                "reasons": [r.value for r in res.reasons], "stage_timings_s": res.stage_timings_s,
                "band_snr_db": res.quality.get("band_snr_db"), "agent": _agent_metrics(history, trace),
                "raw": raw_from_job(job), "artifacts": res.artifacts,
                "time_error_s": (res.time_estimate_utc - truth["start_utc"]) if res.time_estimate_utc else None,
                "time_uncertainty_s": res.time_uncertainty_s, "zone": res.zone})
    # ENF track error against ground truth (synthetic only)
    tr = job.primary_track() if job is not None else None
    if tr is not None and truth.get("enf_clip_hz") and len(tr.track.tau_s) and not truth.get("edits"):
        gt = np.asarray(truth["enf_clip_hz"])
        tau = tr.track.tau_s
        idx = np.clip(np.floor(tau).astype(int), 0, len(gt) - 1)
        e = (tr.track.enf_hz - tr.track.enf_hz.mean()) - (gt[idx] - gt[idx].mean())
        rec["enf_rmse_mhz"] = float(np.sqrt(np.mean(e ** 2)) * 1000)
    # edit detection and localization
    edit_times = [e.get("output_t_s") for e in truth.get("edits", []) if e.get("output_t_s") is not None]
    events = [e for e in (res.continuity_events or []) if e.kind == "EDIT_CANDIDATE"]
    rec["edits_true_t_s"] = edit_times
    rec["edit_events_t_s"] = [e.t_s for e in events]
    if edit_times:
        errs = [min(abs(t - e.t_s) for e in events) for t in edit_times] if events else []
        rec["edit_localization_error_s"] = errs
        rec["edit_detected"] = bool(res.verdict.value == "CONTRADICTED")
    rec["dropped_false_alarm"] = bool(truth.get("dropped") and not truth.get("edits")
                                      and any(e.kind == "EDIT_CANDIDATE" for e in res.continuity_events))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="synthetic")
    ap.add_argument("--data", default="data/synthetic/v1")
    ap.add_argument("--split", default="all", choices=["calibration", "test", "all"])
    ap.add_argument("--planner", default="fallback", choices=["fallback", "bedrock"])
    ap.add_argument("--date", default=datetime.now(tz=UTC).strftime("%Y-%m-%d"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 4))
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    data = REPO / a.data
    manifest = json.loads((data / "manifest.json").read_text())
    items = [m for m in manifest if (a.split == "all" or m["split"] == a.split)
             and (not a.only or m["name"] in a.only or m["condition"] in a.only)]
    out = REPO / "results" / "eval" / a.date / f"{a.suite}-{a.planner}"
    clips = out / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    todo = [m for m in items if not (clips / f"{m['name']}.json").exists()]
    print(f"{len(items)} clips selected, {len(todo)} to run, {a.workers} workers")
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        threads = max(1, (os.cpu_count() or 1) // a.workers)
        futs = {ex.submit(run_clip, m, str(data), str(out), a.planner, threads): m for m in todo}
        for f in as_completed(futs):
            m = futs[f]
            try:
                rec = f.result()
            except Exception as e:  # recorded as a failure case, not hidden
                rec = {"name": m["name"], "condition": m["condition"], "split": m["split"], "class": m["class"],
                       "expected_verdict": EXPECTED[m["class"]], "verdict": None,
                       "error": f"{type(e).__name__}: {e}"}
            (clips / f"{m['name']}.json").write_text(json.dumps(rec, indent=1, default=str))
            print(f"{m['name']}: {rec.get('verdict')} (expected {rec['expected_verdict']})", flush=True)
    meta = {"suite": a.suite, "data": a.data, "planner": a.planner, "split": a.split, "date": a.date,
            "label": "SYNTHETIC" if a.suite.startswith("synthetic") else "REAL",
            "thresholds_hash": __import__("gridprint_engine.config", fromlist=["settings"]).settings().thresholds_hash}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
