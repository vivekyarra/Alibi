"""Task runner behind `make <target>` (DECISIONS D-002)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PY_DIRS = ["engine", "agent", "mcp_server", "api", "eval", "bench", "scripts", "node/ingest",
           "calibration_rig", "infra", "capture-android"]


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})})
    if r.returncode != 0:
        sys.exit(r.returncode)


def npm() -> str:
    return shutil.which("npm") or "npm"


def setup() -> None:
    run(["uv", "sync", "--all-groups"])
    run([PY, "scripts/fetch_models.py"])
    if (ROOT / "web" / "package.json").exists():
        run([npm(), "ci"], cwd=ROOT / "web")


def lint() -> None:
    dirs = [d for d in PY_DIRS if (ROOT / d).exists()]
    run([PY, "-m", "ruff", "check", *dirs, *(["tests"] if (ROOT / "tests").exists() else [])])
    typed = [d for d in ["engine/gridprint_engine", "agent", "mcp_server", "api", "eval", "scripts"]
             if (ROOT / d).exists() and any((ROOT / d).rglob("*.py"))]
    run([PY, "-m", "mypy", *typed])
    run([PY, "scripts/claims_lint.py"])
    run([PY, "scripts/check_numbers_sourced.py"])


def test() -> None:
    run([PY, "-m", "pytest", "-q"])
    if (ROOT / "web" / "node_modules").exists():
        run([npm(), "test", "--", "--run"], cwd=ROOT / "web")


def local() -> None:
    run([PY, "-m", "api.local"])


def deploy() -> None:
    run([PY, "scripts/verify_aws.py"])
    run(["npx", "aws-cdk@2", "deploy", "--all", "--require-approval", "never", "--profile", "gridprint"],
        cwd=ROOT / "infra")


def destroy() -> None:
    run(["npx", "aws-cdk@2", "destroy", "--all", "--force", "--profile", "gridprint"], cwd=ROOT / "infra")


def eval_() -> None:
    run([PY, "-m", "eval.run_eval", "--suite", "synthetic"])
    run([PY, "-m", "eval.make_report"])


def bench() -> None:
    run([PY, "-m", "bench.run_bench", "--config", os.environ.get("BENCH_CONFIG", "local")])


def final_check() -> None:
    run([PY, "scripts/final_check.py"])


def verify_aws() -> None:
    run([PY, "scripts/verify_aws.py"])


def validate_dataset() -> None:
    run([PY, "-m", "eval.validate_dataset", "data/dataset/manifest.json"])


def calibrate() -> None:
    run([PY, "calibration_rig/fit_readout.py", "--all", "data/calibration"])


def node_quality() -> None:
    run([PY, "node/ingest/data_quality.py", "--zone", os.environ.get("ZONE", "IN"),
         "--hours", os.environ.get("HOURS", "24")])


TARGETS = {
    "setup": setup, "lint": lint, "test": test, "local": local, "deploy": deploy, "destroy": destroy,
    "eval": eval_, "bench": bench, "final-check": final_check, "verify-aws": verify_aws,
    "validate-dataset": validate_dataset, "calibrate": calibrate, "node-quality": node_quality,
}

if __name__ == "__main__":
    names = sys.argv[1:] or ["test"]
    for n in names:
        if "=" in n:
            k, v = n.split("=", 1)
            os.environ[k] = v
            continue
        if n not in TARGETS:
            sys.exit(f"unknown target {n}; known: {', '.join(TARGETS)}")
        TARGETS[n]()
