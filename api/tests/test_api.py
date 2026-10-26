"""API tests (SPEC 10.1) with local adapters. Job execution is replaced by a recorder (test double)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from gridprint_engine.adapters import LocalGridLog
from gridprint_engine.schemas import AnalysisResult, LifecycleState, Reason, Verdict

from api.app import create_app
from api.context import Context

MP4_HEAD = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRIDPRINT_REVIEWER_TOKEN", "test-token")
    monkeypatch.setenv("GRIDPRINT_GRIDLOG", str(tmp_path / "gridlog"))
    ctx = Context.from_env(tmp_path)
    started: list[str] = []
    client = TestClient(create_app(ctx, start_job=started.append))
    return ctx, client, started


def test_health(env):
    _, c, _ = env
    assert c.get("/v1/health").json()["status"] == "ok"


def test_create_upload_start(env):
    ctx, c, started = env
    r = c.post("/v1/jobs").json()
    assert r["upload_method"] == "PUT" and r["job_id"]
    up = c.put(r["upload_url"], content=MP4_HEAD)
    assert up.status_code == 200
    s = c.post(f"/v1/jobs/{r['job_id']}/start", json={"claim": {"claimed_zone": "IN"}})
    assert s.json()["status"] == "queued" and started == [r["job_id"]]
    st = c.get(f"/v1/jobs/{r['job_id']}").json()
    assert st["status"] == "queued" and st["verdict"] is None


def test_container_whitelist(env):
    _, c, _ = env
    r = c.post("/v1/jobs").json()
    assert c.put(r["upload_url"], content=b"not a video at all").status_code == 415


def test_start_requires_upload_and_valid_sidecar(env):
    _, c, _ = env
    r = c.post("/v1/jobs").json()
    assert c.post(f"/v1/jobs/{r['job_id']}/start", json={}).status_code == 409
    c.put(r["upload_url"], content=MP4_HEAD)
    bad = c.post(f"/v1/jobs/{r['job_id']}/start", json={"sidecar": {"device_model": "x", "lat": 1}})
    assert bad.status_code == 422


def test_reviewer_endpoints_need_login(env):
    _, c, _ = env
    assert c.get("/v1/reviews").status_code == 401
    assert c.get("/v1/reviews", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert c.get("/v1/reviews", headers={"Authorization": "Bearer test-token"}).json() == []


def _pending(ctx: Context, job_id: str) -> None:
    d = ctx.workdir / job_id
    d.mkdir(parents=True, exist_ok=True)
    res = AnalysisResult(job_id=job_id, file_sha256="0" * 64, engine_version="t", config_hash="c",
                         thresholds_hash="t", verdict=Verdict.CONTRADICTED,
                         lifecycle_state=LifecycleState.PENDING_REVIEW,
                         reasons=[Reason.EDIT_CANDIDATE])
    (d / "result.json").write_text(res.model_dump_json())
    ctx.store.put("Jobs", job_id, {"job_id": job_id, "status": "done", "upload_key": "x"})
    ctx.store.put("Reviews", job_id, {"review_id": job_id, "job_id": job_id, "status": "open"})


@pytest.mark.parametrize("approve,verdict", [(True, "CONTRADICTED"), (False, "INCONCLUSIVE")])
def test_review_decision_gates_contradicted(env, approve, verdict):
    ctx, c, _ = env
    _pending(ctx, "j1")
    h = {"Authorization": "Bearer test-token"}
    assert [r["job_id"] for r in c.get("/v1/reviews", headers=h).json()] == ["j1"]
    out = c.post("/v1/reviews/j1/decision", headers=h, json={"approve": approve, "note": "checked", "reviewer": "R"})
    assert out.status_code == 200
    assert out.json() == {"review_id": "j1", "verdict": verdict, "lifecycle_state": "FINAL"}
    res = json.loads((ctx.workdir / "j1" / "result.json").read_text())
    assert res["reviewer"]["note"] == "checked"
    assert ("REVIEWER_APPROVED" if approve else "REVIEWER_REJECTED") in res["reasons"]
    assert (ctx.workdir / "j1" / "report.html").exists()
    assert c.post("/v1/reviews/j1/decision", headers=h, json={"approve": True, "note": "", "reviewer": "R"}
                  ).status_code == 404  # decided once
    assert ctx.store.scan("AuditLog")


def test_user_input_and_trace(env):
    ctx, c, _ = env
    r = c.post("/v1/jobs").json()
    ctx.store.put("UserRequests", f"{r['job_id']}:camera_model", {"job_id": r["job_id"], "kind": "camera_model",
                                                                  "status": "open"})
    c.post(f"/v1/jobs/{r['job_id']}/input", json={"kind": "camera_model", "value": "Pixel 8"})
    st = c.get(f"/v1/jobs/{r['job_id']}").json()
    assert st["user_requests"][0]["status"] == "answered"
    assert c.get(f"/v1/jobs/{r['job_id']}/trace").json()["steps"] == []


def test_grid_live(env):
    ctx, c, _ = env
    t = np.arange(1_700_000_000, 1_700_000_300)
    LocalGridLog(ctx.gridlog_root).write("IN", t, np.full(len(t), 50.01), source="test", node="n1")
    s = c.get("/v1/grid/IN/live").json()["samples"]
    assert len(s) == ctx.config["grid"]["live_samples"] + 1 and s[-1]["freq_hz"] == pytest.approx(50.01)
    assert c.get("/v1/grid/XX/live").json()["samples"] == []
