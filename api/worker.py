"""Job worker: runs the agent orchestrator (MCP over stdio) for one job and stores results (SPEC 5, 9).

Local mode runs jobs in a background thread. AWS mode polls the SQS jobs queue (`python -m api.worker --sqs`).
"""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from agent.fallback_planner import FallbackPlanner
from agent.orchestrator import run_sync
from api.context import Context

REPO = Path(__file__).resolve().parents[1]


def make_planner(ctx: Context) -> Any:
    cfg = ctx.config
    if cfg["agent"]["planner"] == "bedrock" and cfg["bedrock"]["enabled"]:
        from agent.planner_bedrock import BedrockPlanner, make_client

        b = cfg["bedrock"]
        profile = cfg["aws"]["profile"] if ctx.mode == "local" else None
        client = make_client(profile, b.get("region", cfg["aws"]["region"]), b.get("role_arn"), b.get("external_id"))
        return BedrockPlanner(client, cfg["bedrock"]["model_id"], cfg["bedrock"]["max_tokens"])
    return FallbackPlanner()


def process_job(ctx: Context, job_id: str) -> None:
    job = ctx.store.get("Jobs", job_id)
    if job is None:
        return
    job["status"] = "running"
    ctx.store.put("Jobs", job_id, job)
    jobdir = ctx.workdir / job_id
    jobdir.mkdir(parents=True, exist_ok=True)
    try:
        video = jobdir / "input.mp4"
        ctx.storage.get_file(job["upload_key"], video)
        sidecar = None
        if job.get("sidecar"):
            sidecar = jobdir / "sidecar.json"
            sidecar.write_text(json.dumps(job["sidecar"]))
        spec = {"video": str(video), "sidecar": str(sidecar) if sidecar else None, "claim": job.get("claim") or {},
                "device_model": (job.get("inputs") or {}).get("camera_model")}
        (jobdir / "job.json").write_text(json.dumps(spec))
        planner = make_planner(ctx)
        env = {"GRIDPRINT_WORKDIR": str(ctx.workdir), "GRIDPRINT_GRIDLOG": str(ctx.gridlog_root),
               "GRIDPRINT_STORE": str(ctx.store_root)}
        trace, _ = run_sync(job_id, planner, ctx.config["agent"]["max_iterations"],
                            ctx.config["agent"]["max_tool_calls"], env, jobdir / "trace.json")
        ctx.store.put("TraceIndex", job_id, {"job_id": job_id, "steps": len(trace.steps),
                                             "planner": planner.kind, "trace_key": f"jobs/{job_id}/trace.json"})
        res_path = jobdir / "result.json"
        job = ctx.store.get("Jobs", job_id) or job
        if res_path.exists():
            result = json.loads(res_path.read_text(encoding="utf-8"))
            job.update({"status": "done", "verdict": result["verdict"], "lifecycle_state": result["lifecycle_state"],
                        "reasons": result["reasons"], "time_estimate_iso": result.get("time_estimate_iso"),
                        "time_uncertainty_s": result.get("time_uncertainty_s"), "zone": result.get("zone")})
            publish_artifacts(ctx, job_id, jobdir)
        else:
            job.update({"status": "failed", "error": "no result produced; see trace"})
            publish_artifacts(ctx, job_id, jobdir)  # the trace explains the failure
        job["user_requests"] = [r for r in ctx.store.scan("UserRequests") if r.get("job_id") == job_id]
        ctx.store.put("Jobs", job_id, job)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        (jobdir / "error.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)  # also to CloudWatch
        ctx.store.put("Jobs", job_id, job)
        try:
            ctx.storage.put_file(f"jobs/{job_id}/error.txt", jobdir / "error.txt")
            if (jobdir / "trace.json").exists():
                ctx.storage.put_file(f"jobs/{job_id}/trace.json", jobdir / "trace.json")
        except Exception:
            pass


def publish_artifacts(ctx: Context, job_id: str, jobdir: Path) -> None:
    for f in jobdir.iterdir():
        if f.suffix in {".html", ".pdf", ".json", ".png", ".svg", ".mp4"} and f.name not in {"input.mp4", "job.json"}:
            ctx.storage.put_file(f"jobs/{job_id}/{f.name}", f)


def start_local(ctx: Context, job_id: str) -> None:
    threading.Thread(target=process_job, args=(ctx, job_id), daemon=True).start()


def sqs_loop(ctx: Context) -> None:  # pragma: no cover - needs AWS
    import boto3

    sqs = boto3.client("sqs", region_name=ctx.config["aws"]["region"])
    url = ctx.queue_url
    while True:
        r = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=1, WaitTimeSeconds=20, VisibilityTimeout=1800)
        for m in r.get("Messages", []):
            process_job(ctx, json.loads(m["Body"])["job_id"])
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            shutil.rmtree(ctx.workdir / json.loads(m["Body"])["job_id"], ignore_errors=True)
        time.sleep(0.1)


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqs", action="store_true")
    a = ap.parse_args()
    c = Context.from_env()
    if a.sqs:
        sqs_loop(c)
    print(yaml.safe_dump({"mode": c.mode}))
