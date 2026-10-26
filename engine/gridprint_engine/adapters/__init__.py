"""Adapter interfaces (SPEC Part 5). The engine has no AWS imports; AWS versions live in `aws.py`."""

from __future__ import annotations

import csv
import json
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


class StorageAdapter(ABC):
    @abstractmethod
    def put_file(self, key: str, local_path: Path) -> str: ...

    @abstractmethod
    def get_file(self, key: str, local_path: Path) -> Path: ...

    @abstractmethod
    def url(self, key: str) -> str: ...


class GridLogAdapter(ABC):
    @abstractmethod
    def read(self, zone: str, t0_utc: float, t1_utc: float) -> tuple[np.ndarray, np.ndarray]:
        """Return (t_utc_s int64, freq_hz float64) for whole UTC seconds in [t0, t1]."""

    @abstractmethod
    def write(self, zone: str, t_utc_s: np.ndarray, freq_hz: np.ndarray, source: str, node: str,
              quality: str = "gps") -> None: ...


class JobStoreAdapter(ABC):
    @abstractmethod
    def put(self, table: str, key: str, item: dict[str, Any]) -> None: ...

    @abstractmethod
    def get(self, table: str, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def scan(self, table: str) -> list[dict[str, Any]]: ...


class LocalStorage(StorageAdapter):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_file(self, key: str, local_path: Path) -> str:
        dst = self.root / key
        dst.parent.mkdir(parents=True, exist_ok=True)
        if Path(local_path).resolve() != dst.resolve():
            shutil.copyfile(local_path, dst)
        return key

    def get_file(self, key: str, local_path: Path) -> Path:
        src = self.root / key
        if Path(local_path).resolve() != src.resolve():
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, local_path)
        return Path(local_path)

    def url(self, key: str) -> str:
        return f"/files/{key}"


def _day(t: float) -> str:
    return datetime.fromtimestamp(int(t), tz=UTC).strftime("%Y%m%d")


class LocalGridLog(GridLogAdapter):
    """CSV per zone and UTC day: <root>/<zone>/<YYYYMMDD>.csv with t_utc_s,freq_hz,quality,source,node.

    Multiple rows for one second (several nodes) are reduced to the median (SPEC 10.4).
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def write(self, zone: str, t_utc_s: np.ndarray, freq_hz: np.ndarray, source: str, node: str,
              quality: str = "gps") -> None:
        t = np.asarray(t_utc_s, dtype=np.int64)
        f = np.asarray(freq_hz, dtype=np.float64)
        days: dict[str, list[int]] = {}
        for i, ti in enumerate(t):
            days.setdefault(_day(float(ti)), []).append(i)
        for day, idx in days.items():
            p = self.root / zone / f"{day}.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            new = not p.exists()
            with p.open("a", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["t_utc_s", "freq_hz", "quality", "source", "node"])
                for i in idx:
                    w.writerow([int(t[i]), f"{f[i]:.6f}", quality, source, node])

    def read(self, zone: str, t0_utc: float, t1_utc: float) -> tuple[np.ndarray, np.ndarray]:
        vals: dict[int, list[float]] = {}
        d = int(t0_utc) - int(t0_utc) % 86400
        while d <= t1_utc:
            p = self.root / zone / f"{_day(d)}.csv"
            if p.exists():
                with p.open() as fh:
                    for row in csv.DictReader(fh):
                        t = int(row["t_utc_s"])
                        if t0_utc <= t <= t1_utc:
                            vals.setdefault(t, []).append(float(row["freq_hz"]))
            d += 86400
        if not vals:
            return np.zeros(0, np.int64), np.zeros(0, np.float64)
        ts = np.array(sorted(vals), dtype=np.int64)
        fs = np.array([float(np.median(vals[int(t)])) for t in ts], dtype=np.float64)
        return ts, fs


    def latest(self, zone: str) -> int | None:
        files = sorted((self.root / zone).glob("*.csv"))
        if not files:
            return None
        with files[-1].open() as fh:
            ts = [int(r["t_utc_s"]) for r in csv.DictReader(fh)]
        return max(ts) if ts else None


class LocalJobStore(JobStoreAdapter):
    """JSON file per item (DECISIONS D-013)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _p(self, table: str, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self.root / table / f"{safe}.json"

    def put(self, table: str, key: str, item: dict[str, Any]) -> None:
        p = self._p(table, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(item, default=str, indent=1))
        tmp.replace(p)

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        p = self._p(table, key)
        return json.loads(p.read_text()) if p.exists() else None

    def scan(self, table: str) -> list[dict[str, Any]]:
        d = self.root / table
        return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []
