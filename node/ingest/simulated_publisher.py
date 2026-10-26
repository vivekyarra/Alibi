"""Simulated Node publisher (SPEC 15 M4: "ingest tested with a simulated publisher").

Generates one message per second per node with an Ornstein-Uhlenbeck frequency around nominal
(DECISIONS D-010: theta = 0.02, sigma = 0.004 Hz). Messages carry `source="sim"`, so simulated data
can never be mistaken for Node data.

Modes:
  --local ROOT   feed the messages to the ingest handler, which writes through LocalGridLog.
  --iot          publish to AWS IoT Core topic gridprint/<zone>/<node_id> (needs AWS access, H1).
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo and engine importable
    _ROOT = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(_ROOT), str(_ROOT / "engine")]

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from gridprint_engine.adapters import LocalGridLog  # noqa: E402
from node.ingest.handler import handle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
THETA = 0.02
SIGMA_HZ = 0.004
NODE_NOISE_HZ = 0.0005  # per-node measurement noise; engineering constant (agent notes)


def nominal_hz(zone: str, zones_file: Path = ROOT / "config" / "zones.yaml") -> float:
    for z in yaml.safe_load(zones_file.read_text())["zones"]:
        if z["id"] == zone:
            return float(z["nominal_hz"])
    raise SystemExit(f"unknown zone {zone}")


def ou_track(n: int, f0: float, seed: int, theta: float = THETA, sigma: float = SIGMA_HZ) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.zeros(n, np.float64)
    for i in range(1, n):
        x[i] = x[i - 1] - theta * x[i - 1] + sigma * rng.standard_normal()
    return f0 + x


def messages(zone: str, nodes: list[str], t0: int, seconds: int, seed: int = 0,
             quality: str = "gps", drop_fraction: float = 0.0) -> Iterator[dict[str, Any]]:
    """Yield node messages in time order. `drop_fraction` removes random seconds (to test gap reports)."""
    f0 = nominal_hz(zone)
    track = ou_track(seconds, f0, seed)
    rng = np.random.default_rng(seed + 1)
    for i in range(seconds):
        if drop_fraction and rng.random() < drop_fraction:
            continue
        for node in nodes:
            yield {"zone": zone, "node_id": node, "t_utc_s": t0 + i,
                   "freq_hz": round(float(track[i] + NODE_NOISE_HZ * rng.standard_normal()), 6),
                   "quality": quality, "gps_lock": quality == "gps", "source": "sim"}


class LocalBatchWriter:
    """Writer for `handler.handle` that collects valid messages and writes them to LocalGridLog in
    groups (one file append per group instead of one per message)."""

    def __init__(self, root: Path):
        self.log = LocalGridLog(root)
        self.pending: list[dict[str, Any]] = []

    def __call__(self, m: dict[str, Any]) -> None:
        self.pending.append(m)

    def flush(self) -> None:
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for m in self.pending:
            groups.setdefault((m["zone"], m["node_id"], m["quality"], m["source"]), []).append(m)
        for (zone, node, quality, source), ms in groups.items():
            self.log.write(zone, np.array([m["t_utc_s"] for m in ms], np.int64),
                           np.array([m["freq_hz"] for m in ms], np.float64), source=source, node=node,
                           quality=quality)
        self.pending.clear()


def run_local(root: Path, msgs: Iterator[dict[str, Any]], batch: int = 600) -> dict[str, int]:
    """Feed messages through the real handler (validation included) into LocalGridLog."""
    write = LocalBatchWriter(root)
    written, rejected = 0, 0
    buf: list[dict[str, Any]] = []

    def send() -> None:
        nonlocal written, rejected
        r = handle(buf, write)
        write.flush()
        written, rejected = written + r["written"], rejected + len(r["rejected"])
        buf.clear()

    for m in msgs:
        buf.append(m)
        if len(buf) >= batch:
            send()
    if buf:
        send()
    return {"written": written, "rejected": rejected}


def run_iot(msgs: Iterator[dict[str, Any]], profile: str, region: str, realtime: bool) -> int:
    import boto3

    s = boto3.Session(profile_name=profile, region_name=region)
    ep = s.client("iot").describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    data = s.client("iot-data", endpoint_url=f"https://{ep}")
    n = 0
    for m in msgs:
        data.publish(topic=f"gridprint/{m['zone']}/{m['node_id']}", qos=1, payload=json.dumps(m).encode())
        n += 1
        if realtime:
            time.sleep(1.0)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zone", default="SIM50")
    ap.add_argument("--nodes", default="sim-node-01", help="comma-separated node ids")
    ap.add_argument("--seconds", type=int, default=3600)
    ap.add_argument("--start", type=int, default=None, help="first UTC epoch second (default: now - seconds)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quality", choices=["gps", "ntp"], default="gps")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", type=Path, help="LocalGridLog root, for example work/gridlog")
    g.add_argument("--iot", action="store_true", help="publish to AWS IoT Core")
    ap.add_argument("--profile", default="gridprint")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--realtime", action="store_true", help="IoT mode: one second per message")
    a = ap.parse_args(argv)
    t0 = a.start if a.start is not None else int(time.time()) - a.seconds
    msgs = messages(a.zone, a.nodes.split(","), t0, a.seconds, a.seed, a.quality)
    if a.local:
        print(json.dumps(run_local(a.local, msgs)))
    else:
        print(json.dumps({"published": run_iot(msgs, a.profile, a.region, a.realtime)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
