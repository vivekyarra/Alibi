"""Agent trace (SPEC 9.5, R10): every step records tool, inputs, outputs summary, reason, timestamps."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _summary(x: Any, limit: int = 600) -> str:
    s = json.dumps(x, default=str, separators=(",", ":"))
    return s if len(s) <= limit else s[: limit - 3] + "..."


@dataclass
class TraceStep:
    index: int
    t_start: str
    t_end: str
    planner: str  # "bedrock" | "fallback"
    model_id: str | None
    tool: str
    input_summary: str
    output_summary: str
    decision_reason: str
    duration_s: float
    error: str | None = None
    policy_note: str | None = None


@dataclass
class Trace:
    job_id: str
    steps: list[TraceStep] = field(default_factory=list)

    def add(self, planner: str, model_id: str | None, tool: str, args: dict[str, Any], result: Any,
            reason: str, t0: datetime, t1: datetime, error: str | None = None,
            policy_note: str | None = None) -> TraceStep:
        st = TraceStep(index=len(self.steps), t_start=t0.isoformat(), t_end=t1.isoformat(), planner=planner,
                       model_id=model_id, tool=tool, input_summary=_summary(args),
                       output_summary=_summary(result) if error is None else "", decision_reason=reason,
                       duration_s=round((t1 - t0).total_seconds(), 4), error=error, policy_note=policy_note)
        self.steps.append(st)
        return st

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "steps": [asdict(s) for s in self.steps]}

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return path


def now() -> datetime:
    return datetime.now(tz=UTC)
