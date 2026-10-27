"""Read deployment settings from config/default.yaml (SPEC 10.6: region pinned in config)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO / "config"

# Engineering constants for infrastructure (documented in docs/agent_notes/infra.md).
DEFAULT_WORKER_INSTANCE_TYPE = "c8g.2xlarge"
DEFAULT_WORKER_MAX_INSTANCES = 4
DEFAULT_WAF_RATE_LIMIT_5MIN = 300          # all requests per client IP per 5 minutes
DEFAULT_WAF_JOB_CREATE_LIMIT_5MIN = 20     # POST /v1/jobs (anonymous upload start) per IP per 5 minutes
DEFAULT_COOL_HOST_PATHS = ("/opt/cool", "/opt/ffmpeg")
# Path from the COOL Graviton4 Marketplace listing pattern `/opt/cool/python_3.12/site-packages/`,
# changed to 3.11 to match the project Python. NOT verified on an instance (docs/agent_notes/infra.md).
DEFAULT_COOL_PYTHONPATH = "/opt/cool/python_3.11/site-packages"
DEFAULT_COOL_LD_LIBRARY_PATH = "/opt/cool/cpp_sdk/lib"
DEFAULT_NODE_ZONES = ("IN",)
DEFAULT_RESOURCE_PREFIX = "gridprint"


def upload_retention_days(hours: float) -> int:
    """S3 lifecycle expiration works in whole days; round the configured hours up (minimum 1 day)."""
    return max(1, math.ceil(hours / 24.0))


@dataclass(frozen=True)
class InfraConfig:
    region: str
    profile: str
    bedrock_model_id: str
    upload_retention_hours: float
    results_retention_days: int
    presign_expiry_s: int
    max_file_bytes: int
    freshness_limit_s: int
    cool_ami_id: str | None
    worker_instance_type: str
    worker_max_instances: int
    waf_rate_limit_5min: int
    waf_job_create_limit_5min: int
    node_zones: tuple[str, ...]
    cool_pythonpath: str
    cool_ld_library_path: str
    resource_prefix: str = DEFAULT_RESOURCE_PREFIX
    bedrock_role_arn: str | None = None
    cool_host_paths: tuple[str, ...] = field(default=DEFAULT_COOL_HOST_PATHS)

    @property
    def upload_retention_days(self) -> int:
        return upload_retention_days(self.upload_retention_hours)


def load(config_dir: Path = CONFIG_DIR) -> InfraConfig:
    with open(config_dir / "default.yaml", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    aws = raw.get("aws", {}) or {}
    limits = raw["limits"]
    grid = raw.get("grid", {}) or {}
    cool_ami = aws.get("cool_ami_id") or None
    return InfraConfig(
        region=aws["region"],
        profile=aws["profile"],
        # in-account Claude model kept for the AI stack policy (planner model may live in another account, D-026)
        bedrock_model_id=raw["bedrock"].get("in_account_model_id", raw["bedrock"]["model_id"]),
        upload_retention_hours=float(limits["upload_retention_hours"]),
        results_retention_days=int(limits["results_retention_days"]),
        presign_expiry_s=int(limits["presign_expiry_s"]),
        max_file_bytes=int(limits["max_file_bytes"]),
        freshness_limit_s=int(grid["freshness_limit_s"]),
        cool_ami_id=str(cool_ami) if cool_ami else None,
        worker_instance_type=str(aws.get("worker_instance_type", DEFAULT_WORKER_INSTANCE_TYPE)),
        worker_max_instances=int(aws.get("worker_max_instances", DEFAULT_WORKER_MAX_INSTANCES)),
        waf_rate_limit_5min=int(aws.get("waf_rate_limit_5min", DEFAULT_WAF_RATE_LIMIT_5MIN)),
        waf_job_create_limit_5min=int(aws.get("waf_job_create_limit_5min",
                                              DEFAULT_WAF_JOB_CREATE_LIMIT_5MIN)),
        node_zones=tuple(grid.get("node_zones", DEFAULT_NODE_ZONES)),
        resource_prefix=str(aws.get("resource_prefix", DEFAULT_RESOURCE_PREFIX)),
        bedrock_role_arn=(raw.get("bedrock") or {}).get("role_arn"),
        cool_pythonpath=str(aws.get("cool_pythonpath", DEFAULT_COOL_PYTHONPATH)),
        cool_ld_library_path=str(aws.get("cool_ld_library_path", DEFAULT_COOL_LD_LIBRARY_PATH)),
    )


def foundation_model_id(model_or_profile_id: str) -> str:
    """Strip a cross-Region inference profile prefix (`global.`, `us.`, `eu.`, `apac.`, ...).

    `global.anthropic.claude-sonnet-4-6` -> `anthropic.claude-sonnet-4-6`. A plain model ID is returned as is.
    """
    head, _, rest = model_or_profile_id.partition(".")
    if rest and head in {"global", "us", "eu", "apac", "jp", "au", "ca", "us-gov"}:
        return rest
    return model_or_profile_id


# Prefix for every physical resource name (stacks, tables, IoT names, dashboard, KMS alias); `aws.resource_prefix`.
PREFIX = load().resource_prefix


def prebuilt_image(key: str) -> str | None:
    """ECR image URI built by infra/build_images.py (no local Docker needed), or None to build locally."""
    import json

    f = REPO / "infra" / "image_uris.json"
    return json.loads(f.read_text()).get(key) if f.exists() else None
