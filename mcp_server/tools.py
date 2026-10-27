"""Engine tools exposed by the `gridprint-engine` MCP server (SPEC 9.2).

Each tool takes a job_id. A job is defined by a spec file `<workdir>/<job_id>/job.json` written by the
worker before analysis (video path, optional sidecar, claim, zone hint, device model). Job state
stays in this server process for the job's lifetime.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gridprint_engine.adapters import GridLogAdapter, JobStoreAdapter, LocalGridLog, LocalJobStore
from gridprint_engine.pipeline import Job
from gridprint_engine.schemas import Claim, Reason

REPO = Path(__file__).resolve().parents[1]
USER_INPUT_KINDS = {"original_file", "camera_model", "claimed_time", "longer_clip"}


class EngineTools:
    def __init__(self, workdir: Path, gridlog: GridLogAdapter, store: JobStoreAdapter):
        self.workdir = Path(workdir)
        self.gridlog = gridlog
        self.store = store
        self.jobs: dict[str, Job] = {}
        self.extra_reasons: dict[str, set[Reason]] = {}

    @classmethod
    def from_env(cls) -> EngineTools:
        work = Path(os.environ.get("GRIDPRINT_WORKDIR", REPO / "work"))
        if os.environ.get("GRIDPRINT_MODE") == "aws":  # same adapters as the API and worker (SPEC 5)
            from api.aws_adapters import DynamoJobStore
            from node.ingest.aws_gridlog import DynamoGridLog

            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
            return cls(work, DynamoGridLog(table_name=os.environ["GRIDLOG_TABLE"], region=region),
                       DynamoJobStore(region))
        grid = Path(os.environ.get("GRIDPRINT_GRIDLOG", REPO / "data" / "gridlog"))
        store = Path(os.environ.get("GRIDPRINT_STORE", REPO / "work" / "store"))
        return cls(work, LocalGridLog(grid), LocalJobStore(store))

    # -------------------------------------------------------------- job lookup
    def job(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            spec_path = self.workdir / job_id / "job.json"
            if not spec_path.exists():
                raise KeyError(f"unknown job {job_id}")
            spec = json.loads(spec_path.read_text())
            self.jobs[job_id] = Job(
                Path(spec["video"]), self.workdir, self.gridlog, job_id=job_id,
                sidecar=Path(spec["sidecar"]) if spec.get("sidecar") else None,
                claim=Claim(**(spec.get("claim") or {})), device_model=spec.get("device_model"))
        return self.jobs[job_id]

    # -------------------------------------------------------------- tools (SPEC 9.2)
    def probe_video(self, job_id: str) -> dict[str, Any]:
        return self.job(job_id).probe_video()

    def estimate_readout(self, job_id: str, method: str = "auto") -> dict[str, Any]:
        return self.job(job_id).estimate_readout(method)

    def analyze_motion(self, job_id: str, strictness: str = "normal") -> dict[str, Any]:
        return self.job(job_id).analyze_motion(strictness)

    def propose_patches(self, job_id: str, strategy: str = "all") -> dict[str, Any]:
        return self.job(job_id).propose_patches(strategy)

    def extract_flicker(self, job_id: str, patch_ids: list[int] | None = None, axis: str | None = None,
                        nominal_hz: float | None = None, frame_subset: list[int] | str | None = None
                        ) -> dict[str, Any]:
        return self.job(job_id).extract_flicker(patch_ids, axis, nominal_hz, frame_subset)

    def match_reference(self, job_id: str, track_id: str | None = None, zone: str | None = None,
                        window: list[float] | None = None) -> dict[str, Any]:
        w = (float(window[0]), float(window[1])) if window else None
        return self.job(job_id).match_reference(track_id, zone, w)

    def check_continuity(self, job_id: str, track_id: str | None = None) -> dict[str, Any]:
        return self.job(job_id).check_continuity(track_id)

    def face_region_check(self, job_id: str, track_id: str | None = None) -> dict[str, Any]:
        return self.job(job_id).face_region_check(track_id)

    def compute_verdict(self, job_id: str, budget_exhausted: bool = False) -> dict[str, Any]:
        extra = set(self.extra_reasons.get(job_id, set()))
        if budget_exhausted:
            extra.add(Reason.BUDGET_EXHAUSTED)
        return self.job(job_id).compute_verdict(sorted(extra, key=lambda r: list(Reason).index(r)))

    def request_user_input(self, job_id: str, kind: str, message: str) -> dict[str, Any]:
        if kind not in USER_INPUT_KINDS:
            raise ValueError(f"kind must be one of {sorted(USER_INPUT_KINDS)}")
        self.extra_reasons.setdefault(job_id, set()).add(Reason.USER_INPUT_REQUESTED)
        req = {"job_id": job_id, "kind": kind, "message": message, "status": "open",
               "created": datetime.now(tz=UTC).isoformat()}
        key = f"{job_id}:{kind}"
        self.store.put("UserRequests", key, req)
        return {"request_id": key, "status": "open"}

    def request_human_review(self, job_id: str) -> dict[str, Any]:
        job = self.job(job_id)
        if job.result is None:
            raise ValueError("compute_verdict must run first")
        if job.result.verdict.value != "CONTRADICTED":
            raise ValueError("human review applies to CONTRADICTED verdicts only")
        review = {"review_id": job_id, "job_id": job_id, "verdict": job.result.verdict.value,
                  "reasons": [r.value for r in job.result.reasons], "status": "open",
                  "created": datetime.now(tz=UTC).isoformat()}
        self.store.put("Reviews", job_id, review)
        return {"review_id": job_id, "status": "open"}

    def render_report(self, job_id: str, final: bool = True) -> dict[str, Any]:
        return self.job(job_id).render_report(final)


TOOL_NAMES = ["probe_video", "estimate_readout", "analyze_motion", "propose_patches", "extract_flicker",
              "match_reference", "check_continuity", "face_region_check", "compute_verdict",
              "request_user_input", "request_human_review", "render_report"]
