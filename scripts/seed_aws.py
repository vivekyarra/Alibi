"""Seed the deployed system: demo-case inputs to the results bucket (`demo/`) and reference GridLog data
from the local GridLog folder into the DynamoDB GridLog table. Uses the `gridprint` profile only.

    python scripts/seed_aws.py --results-bucket <name> --gridlog-table <name> [--zone SIM50]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3
import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "engine")]


def main() -> int:
    from gridprint_engine.adapters import LocalGridLog

    from node.ingest.aws_gridlog import DynamoGridLog

    ap = argparse.ArgumentParser()
    ap.add_argument("--results-bucket", required=True)
    ap.add_argument("--gridlog-table", required=True)
    ap.add_argument("--zone", default="SIM50")
    ap.add_argument("--gridlog-root", default=str(REPO / "data" / "gridlog"))
    a = ap.parse_args()
    cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
    s = boto3.Session(profile_name=cfg["aws"]["profile"], region_name=cfg["aws"]["region"])
    s3 = s.client("s3")
    cases = yaml.safe_load((REPO / "config" / "demo_cases.yaml").read_text())["cases"]
    for c in cases:
        for field in ("video", "sidecar"):
            rel = c.get(field)
            if rel and (REPO / rel).exists():
                s3.upload_file(str(REPO / rel), a.results_bucket, f"demo/{Path(rel).name}")
                print(f"uploaded demo/{Path(rel).name}")
    local = LocalGridLog(Path(a.gridlog_root))
    files = sorted((Path(a.gridlog_root) / a.zone).glob("*.csv"))
    remote = DynamoGridLog(table_name=a.gridlog_table, profile=cfg["aws"]["profile"], region=cfg["aws"]["region"])
    total = 0
    for f in files:
        day0 = int(np.datetime64(f"{f.stem[:4]}-{f.stem[4:6]}-{f.stem[6:]}").astype("datetime64[s]").astype(int))
        t, fr = local.read(a.zone, day0, day0 + 86399)
        if len(t):
            remote.write(a.zone, t, fr, source="simulator", node="seed")
            total += len(t)
    print(f"GridLog {a.zone}: {total} seconds written to {a.gridlog_table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
