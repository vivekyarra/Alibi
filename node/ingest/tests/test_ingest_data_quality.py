from __future__ import annotations

from node.ingest import data_quality as dq
from node.ingest import simulated_publisher as sp

T = 1789948800  # 2026-09-21T00:00:00Z


def rows_for(seconds, quality="gps", skip=()):
    return [{"t_utc_s": T + i, "freq_hz": 50.0 + 0.001 * (i % 7), "quality": quality, "source": "node",
             "node": "n1"} for i in range(seconds) if i not in skip]


def test_gaps_coverage_and_outliers():
    rows = rows_for(1000, skip=set(range(100, 110)) | {500})
    rows[200]["freq_hz"] = 50.4  # local outlier
    rows[300]["freq_hz"] = 52.0  # absolute outlier
    rep = dq.analyze(rows, T, T + 999, 50.0)
    assert rep["gaps"] == [{"start_utc_s": T + 100, "length_s": 10}, {"start_utc_s": T + 500, "length_s": 1}]
    assert rep["coverage_pct"] == 100.0 * 989 / 1000
    assert rep["outliers"] == 2
    day = rep["days"]["2026-09-21"]
    assert day["gaps"] == 2 and day["longest_gap_s"] == 10


def test_cli_exit_codes(tmp_path, capsys):
    sp.run_local(tmp_path, sp.messages("SIM50", ["n1"], T, 3600, seed=2))
    assert dq.main(["--zone", "SIM50", "--hours", "1", "--end", str(T + 3599), "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "coverage_pct=100.000" in out and "gps_lock_pct=100.000" in out and "PASS" in out
    # a window twice as long gives 50 % coverage -> exit 1
    assert dq.main(["--zone", "SIM50", "--hours", "2", "--end", str(T + 3599), "--root", str(tmp_path)]) == 1


def test_cli_fails_on_ntp(tmp_path, capsys):
    sp.run_local(tmp_path, sp.messages("SIM50", ["n1"], T, 600, seed=2, quality="ntp"))
    rc = dq.main(["--zone", "SIM50", "--hours", str(600 / 3600), "--end", str(T + 599),
                  "--root", str(tmp_path)])
    assert rc == 1
    assert "gps_lock_pct=0.000" in capsys.readouterr().out
