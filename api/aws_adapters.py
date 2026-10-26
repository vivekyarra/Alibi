"""AWS implementations of the storage and job-store adapters (production only; SPEC 5)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
from gridprint_engine.adapters import JobStoreAdapter, StorageAdapter

TABLES = {"Jobs": "JOBS_TABLE", "Reviews": "REVIEWS_TABLE", "TraceIndex": "TRACE_TABLE"}


class S3Storage(StorageAdapter):
    def __init__(self, results_bucket: str, uploads_bucket: str, region: str, expiry_s: int):
        self.s3 = boto3.client("s3", region_name=region)
        self.results, self.uploads, self.expiry = results_bucket, uploads_bucket, expiry_s

    def _bucket(self, key: str) -> str:
        return self.uploads if key.startswith("uploads/") else self.results

    def put_file(self, key: str, local_path: Path) -> str:
        self.s3.upload_file(str(local_path), self._bucket(key), key)
        return key

    def get_file(self, key: str, local_path: Path) -> Path:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self.s3.download_file(self._bucket(key), key, str(local_path))
        return Path(local_path)

    def url(self, key: str) -> str:
        return str(self.s3.generate_presigned_url("get_object", Params={"Bucket": self._bucket(key), "Key": key},
                                                  ExpiresIn=self.expiry))

    def presign_put(self, key: str) -> str:
        return str(self.s3.generate_presigned_url("put_object", Params={"Bucket": self.uploads, "Key": key,
                                                                        "ContentType": "video/mp4"},
                                                  ExpiresIn=self.expiry))


class DynamoJobStore(JobStoreAdapter):
    """Items are stored as {pk, data(JSON string)}; tables other than Jobs/Reviews/TraceIndex go to Jobs with a
    prefixed key (UserRequests, AuditLog)."""

    def __init__(self, region: str):
        import os

        self.db = boto3.resource("dynamodb", region_name=region)
        self.names = {t: os.environ[e] for t, e in TABLES.items()}

    def _t(self, table: str) -> tuple[Any, str]:
        if table in self.names:
            return self.db.Table(self.names[table]), ""
        return self.db.Table(self.names["Jobs"]), f"{table}#"

    def put(self, table: str, key: str, item: dict[str, Any]) -> None:
        t, pre = self._t(table)
        t.put_item(Item={"pk": pre + key, "data": json.dumps(item, default=str)})

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        t, pre = self._t(table)
        r = t.get_item(Key={"pk": pre + key}).get("Item")
        return json.loads(r["data"]) if r else None

    def scan(self, table: str) -> list[dict[str, Any]]:
        t, pre = self._t(table)
        out: list[dict[str, Any]] = []
        kw: dict[str, Any] = {}
        while True:
            r = t.scan(**kw)
            out += [json.loads(i["data"]) for i in r.get("Items", []) if str(i["pk"]).startswith(pre)
                    and (pre or "#" not in str(i["pk"]))]
            if "LastEvaluatedKey" not in r:
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


__all__ = ["S3Storage", "DynamoJobStore", "Decimal"]
