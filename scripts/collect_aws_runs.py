"""Copy finished AWS job evidence (result, trace, report, plots) from the results bucket into results/aws/<job_id>/
and write results/aws/index.json. Uses the `gridprint` profile only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
import yaml

REPO = Path(__file__).resolve().parents[1]
KEEP = (".json", ".html", ".pdf", ".png")


def main(prefixes: list[str]) -> int:
    cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
    s = boto3.Session(profile_name=cfg["aws"]["profile"], region_name=cfg["aws"]["region"])
    bucket = next(b["Name"] for b in s.client("s3").list_buckets()["Buckets"] if "results" in b["Name"]
                  and b["Name"].startswith(cfg["aws"].get("resource_prefix", "gridprint")))
    s3 = s.client("s3")
    out = REPO / "results" / "aws"
    index = []
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="jobs/")
    keys = [o["Key"] for p in pages for o in p.get("Contents", [])]
    jobs = sorted({k.split("/")[1] for k in keys if any(k.split("/")[1].startswith(x) for x in prefixes)})
    for j in jobs:
        d = out / j
        d.mkdir(parents=True, exist_ok=True)
        for k in keys:
            if k.startswith(f"jobs/{j}/") and k.endswith(KEEP) and not k.endswith("sidecar.json"):
                s3.download_file(bucket, k, str(d / Path(k).name))
        r = json.loads((d / "result.json").read_text()) if (d / "result.json").exists() else {}
        index.append({"job_id": j, "verdict": r.get("verdict"), "lifecycle_state": r.get("lifecycle_state"),
                      "reasons": r.get("reasons"), "time_estimate_iso": r.get("time_estimate_iso"),
                      "band_snr_db": (r.get("quality") or {}).get("band_snr_db"),
                      "stage_timings_s": r.get("stage_timings_s")})
    (out / "index.json").write_text(json.dumps(index, indent=1))
    print(json.dumps(index, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["aws3-", "aws4-"]))
