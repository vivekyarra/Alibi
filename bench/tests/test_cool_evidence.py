"""Tests for bench/cool_evidence.py. Runs locally with the stock OpenCV wheel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import cool_evidence

pytest.importorskip("cv2")


def test_collect_writes_evidence_files(tmp_path: Path) -> None:
    out = tmp_path / "evidence" / "local"
    manifest = cool_evidence.collect(out)
    assert (out / "build_information.txt").read_text(encoding="utf-8").strip()
    versions = json.loads((out / "versions.json").read_text(encoding="utf-8"))
    assert versions["cv2_version"]
    assert versions["cv2_file"]
    saved = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert saved == manifest
    assert manifest["perf"]["status"] == "skipped"
    if Path("/proc/self/maps").exists():
        assert (out / "loaded_libraries.txt").exists()
    else:
        assert manifest["files"]["loaded_libraries.txt"]["status"] == "skipped"


def test_loaded_libraries_parses_maps(tmp_path: Path) -> None:
    maps = tmp_path / "maps"
    maps.write_text(
        "aaaa-bbbb r-xp 00000000 08:01 123 /opt/cool/cpp_sdk/lib/libopencv_core.so.5.0\n"
        "cccc-dddd r--p 00000000 08:01 124 /usr/lib/libc.so.6\n"
        "eeee-ffff rw-p 00000000 00:00 0 [heap]\n"
        "1111-2222 r-xp 00000000 08:01 123 /opt/cool/cpp_sdk/lib/libopencv_core.so.5.0\n",
        encoding="utf-8")
    libs = cool_evidence.loaded_libraries(maps)
    assert libs == ["/opt/cool/cpp_sdk/lib/libopencv_core.so.5.0", "/usr/lib/libc.so.6"]
    assert cool_evidence.loaded_libraries(tmp_path / "missing") is None


def test_marker_hits_counts_case_insensitive() -> None:
    hits = cool_evidence.marker_hits("KleidiCV: YES\nopencv OpenCV")
    assert hits["kleidicv"] == 1
    assert hits["opencv"] == 2
