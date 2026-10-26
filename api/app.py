"""GRIDPRINT API (FastAPI; SPEC 10.1). Local mode uses filesystem adapters; AWS mode uses S3/DynamoDB/SQS."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from gridprint_engine.schemas import AnalysisResult, CaptureSidecar, Claim
from pydantic import BaseModel, ValidationError

from api.context import Context

REPO = Path(__file__).resolve().parents[1]


class StartBody(BaseModel):
    claim: Claim | None = None
    sidecar: dict[str, Any] | None = None


class InputBody(BaseModel):
    kind: str
    value: str


class DecisionBody(BaseModel):
    approve: bool
    note: str
    reviewer: str


def create_app(ctx: Context | None = None, start_job: Any = None) -> FastAPI:
    ctx = ctx or Context.from_env()
    if start_job is None:
        from api.worker import start_local

        def start_job(job_id: str) -> None:
            if ctx.mode == "aws":  # pragma: no cover - needs AWS
                import boto3

                boto3.client("sqs", region_name=ctx.config["aws"]["region"]).send_message(
                    QueueUrl=ctx.queue_url, MessageBody=json.dumps({"job_id": job_id}))
            else:
                start_local(ctx, job_id)

    app = FastAPI(title="GRIDPRINT API", version=ctx.config["engine"]["version"])
    limits = ctx.config["limits"]

    def require_reviewer(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "reviewer login required")
        token = authorization.split(" ", 1)[1]
        if ctx.mode == "aws":  # pragma: no cover - needs Cognito
            from api.auth import verify_cognito_reviewer

            return verify_cognito_reviewer(token)
        if not ctx.reviewer_token or token != ctx.reviewer_token:
            raise HTTPException(403, "not a reviewer")
        return "local-reviewer"

    def get_job(job_id: str) -> dict[str, Any]:
        job = ctx.store.get("Jobs", job_id)
        if job is None:
            raise HTTPException(404, "unknown job")
        return job

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "mode": ctx.mode, "engine_version": ctx.config["engine"]["version"]}

    @app.post("/v1/jobs")
    def create_job(request: Request) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        key = f"uploads/{job_id}/input.mp4"
        ctx.store.put("Jobs", job_id, {"job_id": job_id, "status": "created", "upload_key": key,
                                       "created": datetime.now(tz=UTC).isoformat(), "user_requests": []})
        if ctx.mode == "aws":  # pragma: no cover - needs AWS
            url = ctx.storage.presign_put(key)  # type: ignore[attr-defined]
        else:
            url = str(request.url_for("upload", job_id=job_id))
        return {"job_id": job_id, "upload_url": url, "upload_method": "PUT", "expires_s": limits["presign_expiry_s"]}

    @app.put("/v1/uploads/{job_id}", name="upload")
    async def upload(job_id: str, request: Request) -> dict[str, Any]:
        job = get_job(job_id)
        if job["status"] not in ("created", "uploaded"):
            raise HTTPException(409, "job already started")
        dst = ctx.workdir / job_id / "upload.bin"
        dst.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with dst.open("wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limits["max_file_bytes"]:
                    fh.close()
                    dst.unlink(missing_ok=True)
                    raise HTTPException(413, "file too large")
                fh.write(chunk)
        validate_container(dst)
        ctx.storage.put_file(job["upload_key"], dst)
        job.update({"status": "uploaded", "size_bytes": size})
        ctx.store.put("Jobs", job_id, job)
        return {"job_id": job_id, "status": "uploaded"}

    @app.post("/v1/jobs/{job_id}/start")
    def start(job_id: str, body: StartBody) -> dict[str, Any]:
        job = get_job(job_id)
        if job["status"] not in ("uploaded", "done", "failed"):
            raise HTTPException(409, f"job status is {job['status']}")
        if body.sidecar is not None:
            try:
                CaptureSidecar.model_validate(body.sidecar)
            except ValidationError as e:
                raise HTTPException(422, f"invalid sidecar: {e.error_count()} errors") from e
        job.update({"status": "queued", "claim": body.claim.model_dump() if body.claim else {},
                    "sidecar": body.sidecar, "queued": datetime.now(tz=UTC).isoformat()})
        ctx.store.put("Jobs", job_id, job)
        start_job(job_id)
        return {"job_id": job_id, "status": "queued"}

    @app.get("/v1/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = get_job(job_id)
        out = {k: job.get(k) for k in ("job_id", "status", "error", "lifecycle_state", "verdict", "reasons",
                                       "time_estimate_iso", "time_uncertainty_s", "zone")}
        out["user_requests"] = [r for r in ctx.store.scan("UserRequests") if r.get("job_id") == job_id]
        out["artifacts"] = artifacts(job_id) if job.get("status") == "done" else {}
        res = ctx.workdir / job_id / "result.json"
        out["result"] = json.loads(res.read_text(encoding="utf-8")) if res.exists() else None
        return out

    def artifacts(job_id: str) -> dict[str, Any]:
        names = {"overlay_mp4": "overlay.mp4", "report_html": "report.html", "report_pdf": "report.pdf",
                 "report_json": "result.json"}
        d = ctx.workdir / job_id
        out: dict[str, Any] = {k: ctx.storage.url(f"jobs/{job_id}/{v}") for k, v in names.items() if (d / v).exists()}
        out["plots"] = {p.stem: ctx.storage.url(f"jobs/{job_id}/{p.name}") for p in sorted(d.glob("*.png"))}
        return out

    @app.get("/v1/jobs/{job_id}/trace")
    def trace(job_id: str) -> dict[str, Any]:
        get_job(job_id)
        p = ctx.workdir / job_id / "trace.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"job_id": job_id, "steps": []}

    @app.post("/v1/jobs/{job_id}/input")
    def user_input(job_id: str, body: InputBody) -> dict[str, Any]:
        job = get_job(job_id)
        inputs = job.get("inputs") or {}
        inputs[body.kind] = body.value
        job["inputs"] = inputs
        if body.kind == "claimed_time":
            job["claim"] = {**(job.get("claim") or {}), "claimed_time_utc": body.value}
        key = f"{job_id}:{body.kind}"
        req = ctx.store.get("UserRequests", key)
        if req:
            req.update({"status": "answered", "answered": datetime.now(tz=UTC).isoformat()})
            ctx.store.put("UserRequests", key, req)
        ctx.store.put("Jobs", job_id, job)
        return {"job_id": job_id, "accepted": body.kind}

    @app.get("/v1/reviews")
    def reviews(_: str = Depends(require_reviewer)) -> list[dict[str, Any]]:
        return [r for r in ctx.store.scan("Reviews") if r.get("status") == "open"]

    @app.post("/v1/reviews/{review_id}/decision")
    def decide(review_id: str, body: DecisionBody, who: str = Depends(require_reviewer)) -> dict[str, Any]:
        from gridprint_engine.report import rerender
        from gridprint_engine.verdict import apply_review

        rv = ctx.store.get("Reviews", review_id)
        if rv is None or rv.get("status") != "open":
            raise HTTPException(404, "no open review")
        d = ctx.workdir / rv["job_id"]
        result = AnalysisResult.model_validate_json((d / "result.json").read_text(encoding="utf-8"))
        v, st, reasons = apply_review(result.verdict, result.lifecycle_state, body.approve, result.reasons)
        result.verdict, result.lifecycle_state, result.reasons = v, st, reasons
        result.reviewer = {"name": body.reviewer, "account": who, "time_utc": datetime.now(tz=UTC).isoformat(),
                           "note": body.note, "decision": "approve" if body.approve else "reject"}
        rerender(d, result)
        publish = __import__("api.worker", fromlist=["publish_artifacts"]).publish_artifacts
        publish(ctx, rv["job_id"], d)
        rv.update({"status": "decided", "decision": result.reviewer})
        ctx.store.put("Reviews", review_id, rv)
        ctx.store.put("AuditLog", f"{review_id}-{int(time.time())}", {"review_id": review_id, **result.reviewer})
        job = get_job(rv["job_id"])
        job.update({"verdict": v.value, "lifecycle_state": st.value, "reasons": [r.value for r in reasons]})
        ctx.store.put("Jobs", rv["job_id"], job)
        return {"review_id": review_id, "verdict": v.value, "lifecycle_state": st.value}

    def demo_available(c: dict[str, Any]) -> bool:
        if ctx.mode == "aws":  # demo inputs are seeded to the results bucket by scripts/seed_aws.py
            return bool(c.get("seeded", True))
        return (REPO / c["video"]).exists()

    def demo_input(c: dict[str, Any], field: str, job_id: str) -> Path | None:
        rel = c.get(field)
        if not rel:
            return None
        if ctx.mode == "aws":
            dst = ctx.workdir / job_id / Path(rel).name
            return ctx.storage.get_file(f"demo/{Path(rel).name}", dst)
        return REPO / rel

    @app.get("/v1/demo-cases")
    def demo_cases() -> list[dict[str, Any]]:
        return [{k: c[k] for k in ("id", "title", "description", "expected_verdict")} for c in load_demo_cases()
                if demo_available(c)]

    @app.post("/v1/demo-cases/{case_id}/run")
    def run_demo(case_id: str) -> dict[str, Any]:
        case = next((c for c in load_demo_cases() if c["id"] == case_id), None)
        if case is None or not demo_available(case):
            raise HTTPException(404, "unknown demo case")
        job_id = uuid.uuid4().hex[:12]
        key = f"uploads/{job_id}/input.mp4"
        try:
            video = demo_input(case, "video", job_id)
            side_p = demo_input(case, "sidecar", job_id)
        except Exception as e:
            raise HTTPException(404, "demo input not available") from e
        assert video is not None
        ctx.storage.put_file(key, video)
        sidecar = json.loads(side_p.read_text()) if side_p else None
        ctx.store.put("Jobs", job_id, {"job_id": job_id, "status": "queued", "upload_key": key,
                                       "claim": case.get("claim") or {}, "sidecar": sidecar, "demo_case": case_id,
                                       "created": datetime.now(tz=UTC).isoformat()})
        start_job(job_id)
        return {"job_id": job_id}

    @app.get("/v1/grid/{zone}/live")
    def grid_live(zone: str) -> dict[str, Any]:
        latest = getattr(ctx.gridlog, "latest", None)
        t1 = latest(zone) if callable(latest) else None
        if t1 is None:
            return {"zone": zone, "samples": []}
        n = ctx.config["grid"]["live_samples"]
        t, f = ctx.gridlog.read(zone, t1 - n, t1)
        return {"zone": zone, "samples": [{"t_utc_s": int(a), "freq_hz": float(b)} for a, b in zip(t, f, strict=True)]}

    if ctx.mode == "local":
        @app.get("/files/{path:path}")
        def files(path: str) -> FileResponse:
            root = (ctx.workdir.parent / "files").resolve()
            p = (root / path).resolve()
            if not str(p).startswith(str(root)) or not p.exists():
                raise HTTPException(404, "not found")
            return FileResponse(p)

    return app


def load_demo_cases() -> list[dict[str, Any]]:
    p = REPO / "config" / "demo_cases.yaml"
    return (yaml.safe_load(p.read_text()) or {}).get("cases", []) if p.exists() else []


def validate_container(path: Path) -> None:
    """Container whitelist (MP4/MOV, ISO-BMFF 'ftyp' box). SPEC 13 input validation."""
    with path.open("rb") as fh:
        head = fh.read(12)
    if len(head) < 12 or head[4:8] != b"ftyp":
        path.unlink(missing_ok=True)
        raise HTTPException(415, "only MP4/MOV files are accepted")
