from __future__ import annotations

import zipfile

import numpy as np

from gridprint_engine.adapters import LocalGridLog
from node.ingest import import_neso as neso

T = 1789948800  # 2026-09-21T00:00:00Z


def test_header_detection():
    assert neso.detect_columns(["dtm", "f"]) == (0, 1, True)
    assert neso.detect_columns(["\ufeffDate Time", "Frequency (Hz)"]) == (0, 1, True)
    assert neso.detect_columns(["2026-09-21 00:00:00", "50.01"]) == (0, 1, False)


def test_parse_time_formats():
    assert neso.parse_time("2026-09-21 00:00:00") == T
    assert neso.parse_time("2026-09-21T00:00:01Z") == T + 1
    assert neso.parse_time("21/09/2026 00:00:02") == T + 2
    assert neso.parse_time("nonsense") is None


def test_import_csv_and_zip(tmp_path):
    lines = ["dtm,f"] + [f"2026-09-21 00:00:{s:02d},{50 + s / 1000:.3f}" for s in range(30)]
    lines += ["bad,row", "2026-09-21 00:00:40,70.0", ""]
    p = tmp_path / "f.csv"
    p.write_text("\n".join(lines))
    log = LocalGridLog(tmp_path / "log")
    st = neso.import_file(p, log)
    assert st["written"] == 30 and st["bad_rows"] == 1 and st["out_of_range"] == 1
    assert st["t_min"] == T and st["t_max"] == T + 29
    ts, fs = log.read("GB", T, T + 100)
    assert np.array_equal(ts, np.arange(T, T + 30)) and np.isclose(fs[5], 50.005)
    rows = (tmp_path / "log" / "GB" / "20260921.csv").read_text().splitlines()
    assert rows[1].endswith(",external,neso,neso")
    z = tmp_path / "f.zip"  # header-less file inside a zip
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("m.csv", "\n".join(f"2026-09-21 00:01:{s:02d},50.000" for s in range(5)))
    st2 = neso.import_file(z, LocalGridLog(tmp_path / "log2"))
    assert st2["written"] == 5 and st2["bad_rows"] == 0
