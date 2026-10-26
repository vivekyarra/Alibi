"""Import NESO (Great Britain) 1 s system frequency CSV files into GridLog (SPEC 10.4, V8).

Source: NESO data portal, "System Frequency" (see docs/VERIFICATION.md V8). The files are downloaded by
a human; this script never downloads. Rows are written with source="neso", node="neso",
quality="external" for zone GB.

Header detection is tolerant: the time column is the first column whose name contains "dtm", "date"
or "time"; the frequency column is the first column named "f", "freq", "frequency" or containing
"freq". Files without a header row are read as (time, frequency). Timestamps without an offset are
read as UTC (V8 says the data is in GMT). `.zip` files containing CSV files are also accepted.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo and engine importable
    _ROOT = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(_ROOT), str(_ROOT / "engine")]

import argparse  # noqa: E402
import csv  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import zipfile  # noqa: E402
from collections.abc import Iterable, Iterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402

from gridprint_engine.adapters import GridLogAdapter, LocalGridLog  # noqa: E402

SOURCE = "neso"
NODE = "neso"
QUALITY = "external"
ZONE = "GB"
FREQ_RANGE = (45.0, 55.0)  # plausibility band for a 50 Hz grid; rows outside are counted and skipped
_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
            "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")


def parse_time(s: str) -> float | None:
    s = s.strip().strip('"')
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in _FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _float(s: str) -> float | None:
    try:
        v = float(s.strip().strip('"'))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def detect_columns(first_row: list[str]) -> tuple[int, int, bool]:
    """Return (time_col, freq_col, has_header)."""
    names = [c.strip().strip('"').strip("﻿").lower() for c in first_row]
    t_col = next((i for i, n in enumerate(names) if any(k in n for k in ("dtm", "date", "time"))), None)
    f_col = next((i for i, n in enumerate(names) if n in ("f", "freq", "frequency")), None)
    if f_col is None:
        f_col = next((i for i, n in enumerate(names) if "freq" in n), None)
    if t_col is not None and f_col is not None:
        return t_col, f_col, True
    if len(first_row) >= 2 and parse_time(first_row[0]) is not None and _float(first_row[1]) is not None:
        return 0, 1, False
    raise ValueError(f"cannot find time and frequency columns in header {first_row!r}")


def parse_rows(lines: Iterable[str]) -> Iterator[tuple[float, float] | None]:
    """Yield (t_utc, f_hz) per data row, or None for a row that cannot be parsed."""
    reader = csv.reader(lines)
    for first in reader:
        if not any(c.strip() for c in first):
            continue
        t_col, f_col, has_header = detect_columns(first)
        rows: Iterable[list[str]] = reader if has_header else _chain([first], reader)
        for r in rows:
            if len(r) <= max(t_col, f_col):
                yield None
                continue
            t, f = parse_time(r[t_col]), _float(r[f_col])
            yield None if t is None or f is None else (t, f)
        return


def _chain(*its: Iterable[list[str]]) -> Iterator[list[str]]:
    for it in its:
        yield from it


def _open_texts(path: Path) -> Iterator[tuple[str, Iterable[str]]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    with z.open(name) as fh:
                        yield f"{path.name}:{name}", io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
    else:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            yield path.name, fh


def _flush(log: GridLogAdapter, zone: str, ts: list[int], fs: list[float], stats: dict[str, Any]) -> None:
    if ts:
        log.write(zone, np.array(ts, np.int64), np.array(fs, np.float64), source=SOURCE, node=NODE,
                  quality=QUALITY)
        stats["written"] += len(ts)
        ts.clear()
        fs.clear()


def import_file(path: Path, log: GridLogAdapter, zone: str = ZONE, chunk: int = 86400) -> dict[str, Any]:
    stats = {"file": str(path), "rows": 0, "written": 0, "bad_rows": 0, "out_of_range": 0,
             "non_integer_time": 0, "t_min": None, "t_max": None}
    for _, lines in _open_texts(Path(path)):
        ts: list[int] = []
        fs: list[float] = []
        for item in parse_rows(lines):
            stats["rows"] += 1
            if item is None:
                stats["bad_rows"] += 1
                continue
            t, f = item
            if not FREQ_RANGE[0] <= f <= FREQ_RANGE[1]:
                stats["out_of_range"] += 1
                continue
            ti = int(round(t))
            if abs(t - ti) > 1e-3:
                stats["non_integer_time"] += 1
            ts.append(ti)
            fs.append(f)
            stats["t_min"] = ti if stats["t_min"] is None else min(stats["t_min"], ti)
            stats["t_max"] = ti if stats["t_max"] is None else max(stats["t_max"], ti)
            if len(ts) >= chunk:
                _flush(log, zone, ts, fs, stats)
        _flush(log, zone, ts, fs, stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--zone", default=ZONE)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--root", type=Path, help="LocalGridLog root, for example work/gridlog")
    g.add_argument("--aws", action="store_true", help="write to DynamoDB GridLog (slow per-item upsert)")
    ap.add_argument("--profile", default="gridprint")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--table", default=None, help="default: gridprint-GridLog")
    a = ap.parse_args(argv)
    if a.aws:
        from node.ingest.aws_gridlog import DEFAULT_TABLE, DynamoGridLog

        log: GridLogAdapter = DynamoGridLog(table_name=a.table or DEFAULT_TABLE, profile=a.profile,
                                            region=a.region)
    else:
        log = LocalGridLog(a.root)
    print("Check the NESO data licence terms for each downloaded file before use (V8).", file=sys.stderr)
    for p in a.files:
        print(json.dumps(import_file(p, log, a.zone)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
