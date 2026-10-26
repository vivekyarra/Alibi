"""Configuration loading and hashing. Verdict thresholds come only from config/thresholds.yaml (R8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO / "config"


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Settings:
    default: dict[str, Any]
    thresholds: dict[str, Any]
    zones: dict[str, dict[str, Any]]
    profiles: dict[str, Any]

    @property
    def engine(self) -> dict[str, Any]:
        return self.default["engine"]

    @property
    def config_hash(self) -> str:
        return _hash(self.default)

    @property
    def thresholds_hash(self) -> str:
        return _hash(self.thresholds)

    def nominal_hz(self, zone: str | None) -> float | None:
        if zone and zone in self.zones:
            return float(self.zones[zone]["nominal_hz"])
        return None


def load_settings(config_dir: Path | None = None, thresholds_path: Path | None = None) -> Settings:
    d = Path(config_dir) if config_dir else CONFIG_DIR
    default = yaml.safe_load((d / "default.yaml").read_text())
    thr = yaml.safe_load(Path(thresholds_path or d / "thresholds.yaml").read_text())
    zones = {z["id"]: z for z in yaml.safe_load((d / "zones.yaml").read_text())["zones"]}
    profiles = yaml.safe_load((d / "camera_profiles.yaml").read_text()).get("profiles") or {}
    return Settings(default=default, thresholds=thr, zones=zones, profiles=profiles)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()
