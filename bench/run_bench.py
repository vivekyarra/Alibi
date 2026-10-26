"""COOL benchmark runner (SPEC Part 12): same engine code, same pinned inputs, repeated runs per configuration.

Run on each machine (A, B, C — see bench/configs.yaml and bench/run_remote.md):
    python -m bench.run_bench --config B --runs 5
Then, with all three result folders in one place:
    python -m bench.run_bench --report results/bench/<date>
Outputs per configuration: runs.json (per input and run), tracks.npz (ENF tracks for parity), summary.json.
The report writes parity.json and cost.json. Every number comes from these files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]


def read_inputs(path: Path) -> list[dict[str, str]]:
    """inputs.txt lines: <sha256> <video path> [<sidecar path>] [<gridlog root>] — paths relative to repo."""
    out = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        out.append({"sha256": parts[0], "video": parts[1], "sidecar": parts[2] if len(parts) > 2 and parts[2] != "-"
                    else "", "gridlog": parts[3] if len(parts) > 3 else "data/gridlog"})
    return out


def _cpu_times() -> float:
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


def _peak_rss_mb() -> float | None:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)  # type: ignore[attr-defined,unused-ignore]
        return float(usage.ru_maxrss) / 1024.0  # Linux reports KiB
    except ImportError:  # Windows development host
        return None


def run_config(name: str, runs: int, inputs_file: Path, out: Path) -> dict[str, Any]:
    sys.path[:0] = [str(REPO), str(REPO / "engine")]
    import cv2

    from gridprint_engine.adapters import LocalGridLog
    from gridprint_engine.pipeline import run_default

    items = read_inputs(inputs_file)
    for it in items:
        h = hashlib.sha256((REPO / it["video"]).read_bytes()).hexdigest()
        if h != it["sha256"]:
            raise SystemExit(f"input hash mismatch for {it['video']}")
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    tracks: dict[str, np.ndarray] = {}
    for r in range(runs):
        for it in items:
            t0, c0 = time.perf_counter(), _cpu_times()
            job = run_default(REPO / it["video"], out / "work", LocalGridLog(REPO / it["gridlog"]),
                              sidecar=(REPO / it["sidecar"]) if it["sidecar"] else None, job_id=f"r{r}")
            wall, cpu = time.perf_counter() - t0, _cpu_times() - c0
            res = job.result
            assert res is not None and job.timing is not None
            video_s = float(job.timing.t_s[-1] + job.timing.median_dt_s)
            rows.append({"run": r, "input": it["video"], "wall_s": wall, "cpu_s": cpu, "video_s": video_s,
                         "cpu_util": cpu / wall / (os.cpu_count() or 1), "verdict": res.verdict.value,
                         "stage_timings_s": res.stage_timings_s, "peak_rss_mb": _peak_rss_mb()})
            tr = job.primary_track()
            if r == 0 and tr is not None:
                tracks[it["video"]] = np.stack([tr.track.tau_s, tr.track.enf_hz])
    (out / "runs.json").write_text(json.dumps(rows, indent=1))
    arrays: dict[str, Any] = {k.replace("/", "__"): v for k, v in tracks.items()}
    np.savez(out / "tracks.npz", **arrays)
    summary = summarize(rows)
    summary.update({"config": name, "machine": platform.machine(), "platform": platform.platform(),
                    "cpu_count": os.cpu_count(), "opencv_version": cv2.__version__, "date": datetime.now(tz=UTC)
                    .isoformat(), "inputs_file": str(inputs_file), "runs": runs})
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_run: dict[int, list[dict[str, Any]]] = {}
    for x in rows:
        by_run.setdefault(x["run"], []).append(x)
    # throughput = video-seconds processed per wall-second, one value per repeated run
    thr = [sum(x["video_s"] for x in v) / sum(x["wall_s"] for x in v) for v in by_run.values()]
    stages: dict[str, list[float]] = {}
    for x in rows:
        for k, v in x["stage_timings_s"].items():
            stages.setdefault(k, []).append(v)
    rss = [x["peak_rss_mb"] for x in rows if x["peak_rss_mb"] is not None]
    return {"throughput_video_s_per_wall_s": {"mean": float(np.mean(thr)), "std": float(np.std(thr, ddof=1))
                                              if len(thr) > 1 else 0.0, "per_run": thr},
            "stage_latency_s": {k: {"p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95))}
                                for k, v in sorted(stages.items())},
            "cpu_util_mean": float(np.mean([x["cpu_util"] for x in rows])),
            "peak_rss_mb_max": max(rss) if rss else None}


def report(date_dir: Path, tolerance_hz: float) -> None:
    cfgs = {p.name: p for p in sorted(date_dir.iterdir()) if (p / "summary.json").exists()}
    parity: dict[str, Any] = {"tolerance_hz": tolerance_hz, "pairs": []}
    loaded = {k: dict(np.load(v / "tracks.npz")) for k, v in cfgs.items()}
    verdicts = {k: {(x["input"]): x["verdict"] for x in json.loads((v / "runs.json").read_text()) if x["run"] == 0}
                for k, v in cfgs.items()}
    names = sorted(cfgs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diffs = []
            for key in loaded[a].keys() & loaded[b].keys():
                ta, tb = loaded[a][key], loaded[b][key]
                n = min(ta.shape[1], tb.shape[1])
                diffs.append(float(np.max(np.abs(ta[1, :n] - tb[1, :n]))) if n else float("nan"))
            same = all(verdicts[a].get(k) == verdicts[b].get(k) for k in verdicts[a])
            parity["pairs"].append({"a": a, "b": b, "max_abs_enf_diff_hz": max(diffs) if diffs else None,
                                    "within_tolerance": bool(diffs) and max(diffs) <= tolerance_hz,
                                    "verdicts_identical": same})
    (date_dir / "parity.json").write_text(json.dumps(parity, indent=1))
    prices_p = date_dir / "prices.json"
    cost: dict[str, Any] = {"formula": "cost_per_video_hour_usd = hourly_price_usd / throughput_video_s_per_wall_s",
                            "configs": {}}
    if prices_p.exists():
        prices = json.loads(prices_p.read_text())
        import yaml

        bc = yaml.safe_load((REPO / "bench" / "configs.yaml").read_text())["configs"]
        for k, v in cfgs.items():
            itype = bc.get(k, {}).get("instance_type")
            price = (prices.get("prices") or {}).get(itype, {}).get("usd_per_hour") if itype else None
            fee = (bc.get(k, {}) or {}).get("software_fee_usd_per_hour")
            thr = json.loads((v / "summary.json").read_text())["throughput_video_s_per_wall_s"]["mean"]
            total = (price or 0) + (fee or 0) if price is not None else None
            cost["configs"][k] = {"instance_type": itype, "ec2_usd_per_hour": price, "software_fee_usd_per_hour": fee,
                                  "throughput": thr, "cost_per_video_hour_usd": (total / thr) if total else None}
    (date_dir / "cost.json").write_text(json.dumps(cost, indent=1))
    print(json.dumps({"parity": parity, "cost": cost}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="local")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--inputs", default="bench/inputs.txt")
    ap.add_argument("--date", default=datetime.now(tz=UTC).strftime("%Y-%m-%d"))
    ap.add_argument("--report")
    ap.add_argument("--tolerance-hz", type=float, default=0.001)
    a = ap.parse_args()
    if a.report:
        report(Path(a.report), a.tolerance_hz)
        return
    s = run_config(a.config, a.runs, REPO / a.inputs, REPO / "results" / "bench" / a.date / a.config)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
