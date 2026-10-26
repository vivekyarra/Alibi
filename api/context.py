"""Runtime context for the API and worker: local adapters (default) or AWS adapters (GRIDPRINT_MODE=aws)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from gridprint_engine.adapters import (
    GridLogAdapter,
    JobStoreAdapter,
    LocalGridLog,
    LocalJobStore,
    LocalStorage,
    StorageAdapter,
)

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Context:
    mode: str
    config: dict[str, Any]
    workdir: Path
    store_root: Path
    gridlog_root: Path
    storage: StorageAdapter
    store: JobStoreAdapter
    gridlog: GridLogAdapter
    reviewer_token: str | None
    queue_url: str | None = None

    @classmethod
    def from_env(cls, root: Path | None = None) -> Context:
        cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
        mode = os.environ.get("GRIDPRINT_MODE", "local")
        base = Path(root) if root else Path(os.environ.get("GRIDPRINT_HOME", str(REPO / "work")))
        work = base / "jobs"
        store_root = base / "store"
        grid_root = Path(os.environ.get("GRIDPRINT_GRIDLOG", REPO / "data" / "gridlog"))
        if mode == "aws":  # pragma: no cover - needs AWS
            from api.aws_adapters import DynamoJobStore, S3Storage
            from node.ingest.aws_gridlog import DynamoGridLog

            storage: StorageAdapter = S3Storage(os.environ["RESULTS_BUCKET"], os.environ["UPLOADS_BUCKET"],
                                                cfg["aws"]["region"], cfg["limits"]["presign_expiry_s"])
            store: JobStoreAdapter = DynamoJobStore(cfg["aws"]["region"])
            gridlog: GridLogAdapter = DynamoGridLog(table_name=os.environ["GRIDLOG_TABLE"], region=cfg["aws"]["region"])
        else:
            storage = LocalStorage(base / "files")
            store = LocalJobStore(store_root)
            gridlog = LocalGridLog(grid_root)
        return cls(mode=mode, config=cfg, workdir=work, store_root=store_root, gridlog_root=grid_root,
                   storage=storage, store=store, gridlog=gridlog,
                   reviewer_token=os.environ.get("GRIDPRINT_REVIEWER_TOKEN"),
                   queue_url=os.environ.get("JOBS_QUEUE_URL"))
