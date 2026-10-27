"""GridLogAdapter on DynamoDB table `GridLog` (SPEC 5, 10.4). Same interface as `LocalGridLog`.

Item layout is documented in `node/ingest/handler.py`. Several nodes per second -> median of `readings`.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from gridprint_engine.adapters import GridLogAdapter
from node.ingest.handler import DynamoWriter, day_key

DAY_S = 86400
DEFAULT_TABLE = os.environ.get("GRIDLOG_TABLE") or os.environ.get("GRIDPRINT_GRIDLOG_TABLE") or "gridprint-GridLog"


def _query_all(table: Any, **kw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        r = table.query(**kw)
        items.extend(r.get("Items", []))
        lek = r.get("LastEvaluatedKey")
        if not lek:
            return items
        kw["ExclusiveStartKey"] = lek


class DynamoGridLog(GridLogAdapter):
    def __init__(self, table: Any = None, table_name: str = DEFAULT_TABLE, profile: str | None = None,
                 region: str | None = None):
        if table is None:
            import boto3

            table = boto3.Session(profile_name=profile, region_name=region).resource("dynamodb").Table(
                table_name)
        self.table = table

    def _items(self, zone: str, t0: int, t1: int, limit_desc: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        d = t0 - t0 % DAY_S
        while d <= t1:
            kw: dict[str, Any] = {
                "KeyConditionExpression": "#pk = :pk AND #t BETWEEN :a AND :b",
                "ExpressionAttributeNames": {"#pk": "pk", "#t": "t"},
                "ExpressionAttributeValues": {":pk": day_key(zone, d), ":a": max(t0, d),
                                              ":b": min(t1, d + DAY_S - 1)},
            }
            if limit_desc:
                kw.update(ScanIndexForward=False, Limit=limit_desc)
                r = self.table.query(**kw)
                out.extend(r.get("Items", []))
            else:
                out.extend(_query_all(self.table, **kw))
            d += DAY_S
        return out

    def read_detail(self, zone: str, t0_utc: float, t1_utc: float) -> list[dict[str, Any]]:
        """One row per (second, node): t_utc_s, freq_hz, quality, source, node."""
        rows = []
        for it in self._items(zone, int(np.ceil(t0_utc)), int(np.floor(t1_utc))):
            for node, r in (it.get("readings") or {}).items():
                rows.append({"t_utc_s": int(it["t"]), "freq_hz": float(r["freq"]),
                             "quality": str(r["quality"]), "source": str(r["source"]), "node": node})
        return rows

    def read(self, zone: str, t0_utc: float, t1_utc: float) -> tuple[np.ndarray, np.ndarray]:
        vals: dict[int, list[float]] = {}
        for row in self.read_detail(zone, t0_utc, t1_utc):
            vals.setdefault(row["t_utc_s"], []).append(row["freq_hz"])
        if not vals:
            return np.zeros(0, np.int64), np.zeros(0, np.float64)
        ts = np.array(sorted(vals), dtype=np.int64)
        fs = np.array([float(np.median(vals[int(t)])) for t in ts], dtype=np.float64)
        return ts, fs

    def write(self, zone: str, t_utc_s: np.ndarray, freq_hz: np.ndarray, source: str, node: str,
              quality: str = "gps") -> None:
        w = DynamoWriter(self.table)
        for t, f in zip(np.asarray(t_utc_s, np.int64), np.asarray(freq_hz, np.float64), strict=True):
            w.upsert(zone, int(t), node, float(f), quality, source)

    def latest(self, zone: str, lookback_days: int = 7, now_s: float | None = None) -> int | None:
        now = int(time.time() if now_s is None else now_s)
        d = now - now % DAY_S
        for _ in range(lookback_days + 1):
            items = self._items(zone, d, d + DAY_S - 1, limit_desc=1)
            if items:
                return int(items[0]["t"])
            d -= DAY_S
        return None
