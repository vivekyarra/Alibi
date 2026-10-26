"""Pure-Python tests for infra configuration helpers (no aws_cdk needed)."""

from __future__ import annotations

import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))

from gridprint_infra import config as cfgmod  # noqa: E402


def test_upload_retention_rounds_up_to_whole_days() -> None:
    assert cfgmod.upload_retention_days(24) == 1
    assert cfgmod.upload_retention_days(1) == 1
    assert cfgmod.upload_retention_days(25) == 2
    assert cfgmod.upload_retention_days(48) == 2


def test_foundation_model_id_strips_inference_profile_prefix() -> None:
    assert cfgmod.foundation_model_id("global.anthropic.claude-sonnet-4-6") == "anthropic.claude-sonnet-4-6"
    assert cfgmod.foundation_model_id("us.anthropic.claude-x") == "anthropic.claude-x"
    assert cfgmod.foundation_model_id("anthropic.claude-x") == "anthropic.claude-x"


def test_load_reads_repo_config() -> None:
    c = cfgmod.load()
    assert c.region == "us-east-1"
    assert c.profile == "gridprint"
    assert c.upload_retention_days >= 1
    assert c.results_retention_days > 0
    assert c.freshness_limit_s > 0


def test_cool_ami_is_optional(tmp_path: Path) -> None:
    src = (cfgmod.CONFIG_DIR / "default.yaml").read_text(encoding="utf-8")
    patched = src.replace("aws:\n", "aws:\n  cool_ami_id: ami-0123456789abcdef0\n", 1)
    (tmp_path / "default.yaml").write_text(patched, encoding="utf-8")
    assert cfgmod.load().cool_ami_id is None or cfgmod.load().cool_ami_id.startswith("ami-")
    assert cfgmod.load(tmp_path).cool_ami_id == "ami-0123456789abcdef0"
