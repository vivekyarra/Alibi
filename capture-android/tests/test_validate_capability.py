"""Tests for capture-android/validate_capability.py.

Fixtures in tests/fixtures/ were written by the Kotlin classes CapabilityReport and SidecarBuilder
(app/src/main/java/dev/gridprint/capture) with synthetic input values. They are not device results.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
REPO = APP_DIR.parent
FIX = HERE / "fixtures"
SCRIPT = APP_DIR / "validate_capability.py"

_spec = importlib.util.spec_from_file_location("validate_capability", SCRIPT)
assert _spec is not None and _spec.loader is not None
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def run(*paths: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), *map(str, paths)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_pass_fixture_all_pass() -> None:
    lines, ok = vc.validate(load("synthetic_capability_pass.json"))
    assert ok
    assert sum(line.startswith("PASS") for line in lines) == 6


def test_fail_fixture_missing_required() -> None:
    lines, ok = vc.validate(load("synthetic_capability_fail.json"))
    assert not ok
    text = "\n".join(lines)
    assert "FAIL  ae_mode_off (required)" in text
    assert "FAIL  rolling_shutter_skew (optional)" in text
    assert "calibration rig" in text


def test_optional_failures_do_not_fail_the_file() -> None:
    d = load("synthetic_capability_pass.json")
    d["capabilities"]["rolling_shutter_skew"].update(supported=False, observed_ns=None)
    d["capabilities"]["timestamp_source_realtime"].update(supported=False, value=0, name="UNKNOWN")
    lines, ok = vc.validate(d)
    assert ok
    assert any(line.startswith("FAIL  timestamp_source_realtime (optional)") for line in lines)


def test_inconsistent_flag_is_fail() -> None:
    d = load("synthetic_capability_pass.json")
    d["capabilities"]["antibanding_off"]["available_antibanding_modes"] = [1, 2, 3]  # OFF (0) absent
    lines, ok = vc.validate(d)
    assert not ok
    assert any("antibanding_off" in line and "file says supported=True" in line for line in lines)


@pytest.mark.parametrize(
    ("rng", "expected"),
    [([10_000, 500_000_000], True), ([2_000_000, 500_000_000], False), ([10_000, 900_000], False)],
)
def test_manual_exposure_range(rng: list[int], expected: bool) -> None:
    d = load("synthetic_capability_pass.json")
    c = d["capabilities"]["manual_exposure"]
    c["exposure_range_ns"] = rng
    c["supported"] = expected
    _, ok = vc.validate(d)
    assert ok is expected


def test_missing_capability_and_bad_schema() -> None:
    d = load("synthetic_capability_pass.json")
    del d["capabilities"]["fixed_30fps"]
    _, ok = vc.validate(d)
    assert not ok
    bad = copy.deepcopy(load("synthetic_capability_pass.json"))
    bad["schema"] = "other"
    _, ok2 = vc.validate(bad)
    assert not ok2


def test_cli_exit_codes(tmp_path: Path) -> None:
    good = run(FIX / "synthetic_capability_pass.json")
    assert good.returncode == 0, good.stdout
    assert "RESULT: OK" in good.stdout
    mixed = run(FIX / "synthetic_capability_pass.json", FIX / "synthetic_capability_fail.json")
    assert mixed.returncode == 1
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert run(broken).returncode == 1
    assert run().returncode == 2


def test_kotlin_sidecar_fixture_matches_engine_schema_keys() -> None:
    """Field names written by the Kotlin SidecarBuilder equal the engine CaptureSidecar fields."""
    sidecar = load("sidecar_from_kotlin.json")
    schema_src = (REPO / "engine" / "gridprint_engine" / "schemas.py").read_text(encoding="utf-8")
    block = schema_src.split("class CaptureSidecar(BaseModel):", 1)[1].split("\nclass ", 1)[0]
    fields = re.findall(r"^    ([a-z_0-9]+):", block, flags=re.MULTILINE)
    assert list(sidecar) == fields
    assert not any(k in sidecar for k in ("gps", "latitude", "longitude", "location"))


def test_kotlin_config_matches_repo_config() -> None:
    """CaptureConfig.kt mirrors config/default.yaml capture: exposure_ns, fps, bitrate_bps."""
    yaml_text = (REPO / "config" / "default.yaml").read_text(encoding="utf-8")
    section = yaml_text.split("\ncapture:", 1)[1]

    def yaml_int(key: str) -> int:
        m = re.search(rf"^\s+{key}:\s*([0-9_]+)", section, flags=re.MULTILINE)
        assert m, key
        return int(m.group(1).replace("_", ""))

    kt = (APP_DIR / "app/src/main/java/dev/gridprint/capture/CaptureConfig.kt").read_text(encoding="utf-8")

    def kt_int(name: str) -> int:
        m = re.search(rf"const val {name}: \w+ = ([0-9_]+)L?", kt)
        assert m, name
        return int(m.group(1).replace("_", ""))

    assert kt_int("EXPOSURE_NS") == yaml_int("exposure_ns")
    assert kt_int("FPS") == yaml_int("fps")
    assert kt_int("BITRATE_BPS") == yaml_int("bitrate_bps")
