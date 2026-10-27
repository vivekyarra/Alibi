"""Run the GRIDPRINT engine (run_default, render=True) on one clip for the submission video.

Usage (from repo root):
    PYTHONPATH=".;engine" python video/run_engine.py <name> <video> [--sidecar PATH] [--gridlog ROOT]

Outputs go to results/video/engine_runs/<name>/ (overlay.mp4, plots, report, result.json)
plus run_meta.json with the inputs used. Nothing here writes a verdict: the engine does.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "video" / "engine_runs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("video")
    ap.add_argument("--sidecar", default=None)
    ap.add_argument("--gridlog", default="D:/Open-cv/data/gridlog")
    a = ap.parse_args()

    from gridprint_engine.adapters import LocalGridLog
    from gridprint_engine.pipeline import run_default

    wd = RUNS / a.name
    wd.mkdir(parents=True, exist_ok=True)
    meta = {"name": a.name, "video": a.video, "sidecar": a.sidecar, "gridlog_root": a.gridlog,
            "started": datetime.now(tz=UTC).isoformat(), "ok": False}
    t0 = time.perf_counter()
    try:
        job = run_default(Path(a.video), wd, LocalGridLog(Path(a.gridlog)),
                          sidecar=Path(a.sidecar) if a.sidecar else None, render=True, job_id=a.name)
        res = job.result
        if res is not None:
            (wd / "video_result.json").write_text(res.model_dump_json(indent=1))
            meta["verdict"] = res.verdict.value
            meta["lifecycle_state"] = res.lifecycle_state.value
            meta["reasons"] = [r.value if hasattr(r, "value") else str(r) for r in res.reasons]
        meta["ok"] = True
    except Exception as e:  # noqa: BLE001 - record the failure honestly; the video shows it
        meta["error"] = f"{type(e).__name__}: {e}"
        meta["traceback"] = traceback.format_exc()
    meta["wall_s"] = round(time.perf_counter() - t0, 2)
    meta["finished"] = datetime.now(tz=UTC).isoformat()
    (wd / "run_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "traceback"}))
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
