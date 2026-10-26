"""Validate gridprint_capability.json files written by the GRIDPRINT Capture "Device check" screen.

SPEC Part 4 V7 and Part 16 H4. Standard library only (Python 3.11).

Usage:
    python capture-android/validate_capability.py PATH [PATH ...]

For each file, prints PASS or FAIL per capability. The script does not trust the "supported"
flags alone: it recomputes each one from the raw values in the file and reports a mismatch as FAIL.

Exit code 1 if any file is unreadable, has the wrong format, or misses a REQUIRED capability.
Optional capabilities have a documented fallback (calibration-rig readout profile, SPEC 10.5) and
only print FAIL with the fallback note.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCHEMA = "gridprint_capability/1"
FPS = 30

# Documented values of the Android constants (android.hardware.camera2.CameraMetadata).
CONTROL_AE_MODE_OFF = 0
CONTROL_AE_ANTIBANDING_MODE_OFF = 0
SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME = 1


def _ae_mode_off(c: dict[str, Any]) -> bool:
    return CONTROL_AE_MODE_OFF in c["available_ae_modes"]


def _antibanding_off(c: dict[str, Any]) -> bool:
    return CONTROL_AE_ANTIBANDING_MODE_OFF in c["available_antibanding_modes"]


def _manual_exposure(c: dict[str, Any]) -> bool:
    rng = c["exposure_range_ns"]
    if not c["manual_sensor_capability"] or rng is None or len(rng) != 2:
        return False
    return int(rng[0]) <= int(c["requested_exposure_ns"]) <= int(rng[1])


def _fixed_30fps(c: dict[str, Any]) -> bool:
    return any(len(r) == 2 and r[0] <= FPS <= r[1] for r in c["available_fps_ranges"])


def _skew(c: dict[str, Any]) -> bool:
    obs = c["observed_ns"]
    return bool(c["listed_in_result_keys"]) and obs is not None and int(obs) > 0


def _realtime(c: dict[str, Any]) -> bool:
    return c["value"] == SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME


# name -> (required, recompute function, keys that must exist, fallback note)
CAPABILITIES: dict[str, tuple[bool, Callable[[dict[str, Any]], bool], tuple[str, ...], str]] = {
    "ae_mode_off": (True, _ae_mode_off, ("available_ae_modes",), ""),
    "antibanding_off": (True, _antibanding_off, ("available_antibanding_modes",), ""),
    "manual_exposure": (
        True,
        _manual_exposure,
        ("manual_sensor_capability", "exposure_range_ns", "requested_exposure_ns"),
        "",
    ),
    "fixed_30fps": (True, _fixed_30fps, ("available_fps_ranges",), ""),
    "rolling_shutter_skew": (
        False,
        _skew,
        ("listed_in_result_keys", "observed_ns"),
        "fallback: readout from the calibration rig profile (SPEC 10.5); the app writes no sidecar",
    ),
    "timestamp_source_realtime": (
        False,
        _realtime,
        ("value",),
        "fallback: wall_clock_start_utc is the record-button time; sensor_timestamp_wall_offset_ns is null",
    ),
}


def validate(data: Any) -> tuple[list[str], bool]:
    """Return (report lines, ok). ok is False if the format is wrong or a required capability fails."""
    lines: list[str] = []
    if not isinstance(data, dict):
        return ["FAIL  format: top level is not a JSON object"], False
    if data.get("schema") != SCHEMA:
        return [f"FAIL  format: schema is {data.get('schema')!r}, expected {SCHEMA!r}"], False
    caps = data.get("capabilities")
    if not isinstance(caps, dict):
        return ["FAIL  format: 'capabilities' object missing"], False

    ok = True
    lines.append(
        f"device: {data.get('device_model')} | android_sdk_int: {data.get('android_sdk_int')} | "
        f"camera: {data.get('camera_id')} | level: {data.get('hardware_level')} | "
        f"sensor_orientation: {data.get('sensor_orientation')}"
    )
    for name, (required, fn, keys, note) in CAPABILITIES.items():
        kind = "required" if required else "optional"
        entry = caps.get(name)
        if not isinstance(entry, dict) or "supported" not in entry or any(k not in entry for k in keys):
            lines.append(f"FAIL  {name} ({kind}): missing in file")
            ok = ok and not required
            continue
        try:
            recomputed = fn(entry)
        except (TypeError, ValueError, KeyError) as exc:
            lines.append(f"FAIL  {name} ({kind}): bad values ({exc})")
            ok = ok and not required
            continue
        claimed = entry["supported"]
        if claimed is not recomputed:
            lines.append(f"FAIL  {name} ({kind}): file says supported={claimed}, values give {recomputed}")
            ok = ok and not required
            continue
        detail = {k: entry[k] for k in keys}
        if recomputed:
            lines.append(f"PASS  {name} ({kind}): {detail}")
        else:
            suffix = f"; {note}" if note else ""
            lines.append(f"FAIL  {name} ({kind}): {detail}{suffix}")
            ok = ok and not required
    return lines, ok


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: validate_capability.py gridprint_capability.json [more.json ...]")
        return 2
    all_ok = True
    for arg in argv:
        path = Path(arg)
        print(f"== {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL  read: {exc}")
            all_ok = False
            continue
        lines, ok = validate(data)
        for line in lines:
            print(line)
        summary = "OK (all required capabilities present)" if ok else "MISSING REQUIRED CAPABILITY"
        print("RESULT: " + summary)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
