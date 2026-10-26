"""GridLog data-quality report (SPEC 10.4, H2 validation).

Reports per UTC day: coverage, gaps, GPS lock ratio and outliers. Prints overall coverage % and GPS
lock %. Exit code 1 when coverage < 99 % or GPS lock < 99 % (the H2 acceptance line).

Local mode (`--root`) reads LocalGridLog CSV files. Without `--root` it reads DynamoDB `GridLog`.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo and engine importable
    _ROOT = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(_ROOT), str(_ROOT / "engine")]

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PASS_COVERAGE_PCT = 99.0
PASS_GPS_LOCK_PCT = 99.0
# Outlier rules (engineering constants, see docs/agent_notes/node_calibration.md):
OUTLIER_ABS_HZ = 1.0     # |f - nominal| above this
OUTLIER_LOCAL_HZ = 0.05  # |f - running median over 61 s| above this
MEDIAN_WIN_S = 61


def read_local_rows(root: Path, zone: str, t0: int, t1: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    d = t0 - t0 % 86400
    while d <= t1:
        p = Path(root) / zone / f"{datetime.fromtimestamp(d, tz=UTC):%Y%m%d}.csv"
        if p.exists():
            with p.open() as fh:
                for r in csv.DictReader(fh):
                    t = int(r["t_utc_s"])
                    if t0 <= t <= t1:
                        rows.append({"t_utc_s": t, "freq_hz": float(r["freq_hz"]), "quality": r["quality"],
                                     "source": r["source"], "node": r["node"]})
        d += 86400
    return rows


def _running_median(f: np.ndarray, win: int) -> np.ndarray:
    h = win // 2
    pad = np.pad(f, h, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(pad, win)
    return np.median(view, axis=1)


def analyze(rows: list[dict[str, Any]], t0: int, t1: int, nominal: float) -> dict[str, Any]:
    """Pure function: rows (one per second per node) -> report dict."""
    span = t1 - t0 + 1
    per_sec: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        per_sec.setdefault(int(r["t_utc_s"]), []).append(r)
    ts = np.array(sorted(per_sec), dtype=np.int64)
    fs = np.array([float(np.median([x["freq_hz"] for x in per_sec[int(t)]])) for t in ts], np.float64)
    gps_rows = sum(1 for r in rows if r["quality"] == "gps")
    outlier = np.zeros(len(ts), bool)
    if len(ts):
        outlier |= np.abs(fs - nominal) > OUTLIER_ABS_HZ
        if len(ts) >= MEDIAN_WIN_S:
            outlier |= np.abs(fs - _running_median(fs, MEDIAN_WIN_S)) > OUTLIER_LOCAL_HZ
    present = np.zeros(span, bool)
    present[ts - t0] = True
    gaps = []
    i = 0
    while i < span:
        if not present[i]:
            j = i
            while j < span and not present[j]:
                j += 1
            gaps.append({"start_utc_s": t0 + i, "length_s": j - i})
            i = j
        else:
            i += 1
    days: dict[str, dict[str, Any]] = {}
    d = t0 - t0 % 86400
    while d <= t1:
        a, b = max(t0, d), min(t1, d + 86399)
        m = (ts >= a) & (ts <= b)
        drows = [r for r in rows if a <= r["t_utc_s"] <= b]
        dgaps = [g for g in gaps if a <= g["start_utc_s"] <= b]
        days[f"{datetime.fromtimestamp(d, tz=UTC):%Y-%m-%d}"] = {
            "seconds_expected": b - a + 1, "seconds_present": int(m.sum()),
            "coverage_pct": 100.0 * float(m.sum()) / (b - a + 1),
            "gps_lock_pct": 100.0 * sum(r["quality"] == "gps" for r in drows) / len(drows) if drows else 0.0,
            "gaps": len(dgaps), "longest_gap_s": max((g["length_s"] for g in dgaps), default=0),
            "outliers": int(outlier[m].sum()),
        }
        d += 86400
    return {
        "t0_utc_s": t0, "t1_utc_s": t1, "seconds_expected": span, "seconds_present": int(len(ts)),
        "coverage_pct": 100.0 * len(ts) / span,
        "gps_lock_pct": 100.0 * gps_rows / len(rows) if rows else 0.0,
        "nodes": sorted({r["node"] for r in rows}), "gaps": gaps, "outliers": int(outlier.sum()),
        "outlier_times_utc_s": [int(t) for t in ts[outlier][:100]], "days": days,
    }


def nominal_for(zone: str) -> float:
    for z in yaml.safe_load((ROOT / "config" / "zones.yaml").read_text())["zones"]:
        if z["id"] == zone:
            return float(z["nominal_hz"])
    raise SystemExit(f"unknown zone {zone}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--hours", type=float, required=True)
    ap.add_argument("--end", type=int, default=None, help="last UTC epoch second (default: now - 1)")
    ap.add_argument("--root", type=Path, default=None, help="LocalGridLog root (local mode)")
    ap.add_argument("--node", default=None, help="only rows from this node id")
    ap.add_argument("--json", type=Path, default=None, help="also write the full report here")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--table", default=None, help="default: gridprint-GridLog")
    a = ap.parse_args(argv)
    t1 = a.end if a.end is not None else int(time.time()) - 1
    t0 = t1 - int(round(a.hours * 3600)) + 1
    if a.root is not None:
        rows = read_local_rows(a.root, a.zone, t0, t1)
    else:
        from node.ingest.aws_gridlog import DEFAULT_TABLE, DynamoGridLog

        cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text())["aws"]
        log = DynamoGridLog(table_name=a.table or DEFAULT_TABLE, profile=a.profile or cfg["profile"],
                            region=a.region or cfg["region"])
        rows = log.read_detail(a.zone, t0, t1)
    if a.node:
        rows = [r for r in rows if r["node"] == a.node]
    rep = analyze(rows, t0, t1, nominal_for(a.zone))
    rep["zone"] = a.zone
    for day, s in rep["days"].items():
        print(f"{day}  coverage={s['coverage_pct']:.3f}%  gps_lock={s['gps_lock_pct']:.3f}%  "
              f"gaps={s['gaps']}  longest_gap_s={s['longest_gap_s']}  outliers={s['outliers']}")
    print(f"zone={a.zone} nodes={','.join(rep['nodes']) or '-'} window_s={rep['seconds_expected']}")
    print(f"coverage_pct={rep['coverage_pct']:.3f}")
    print(f"gps_lock_pct={rep['gps_lock_pct']:.3f}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(rep, indent=1))
    ok = rep["coverage_pct"] >= PASS_COVERAGE_PCT and rep["gps_lock_pct"] >= PASS_GPS_LOCK_PCT
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
