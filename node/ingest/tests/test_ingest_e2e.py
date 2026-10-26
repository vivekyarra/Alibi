"""Simulated publisher -> handler (validation) -> LocalGridLog, end to end in a tmp dir."""

from __future__ import annotations

import numpy as np
from gridprint_engine.adapters import LocalGridLog

from node.ingest import data_quality
from node.ingest import simulated_publisher as sp

T = 1789948800 - 300  # crosses 2026-09-21T00:00:00Z


def test_ou_parameters_match_decision_d010():
    assert sp.THETA == 0.02 and sp.SIGMA_HZ == 0.004
    x = sp.ou_track(20000, 50.0, seed=3) - 50.0
    # stationary std of this discrete OU process: sigma / sqrt(1 - (1 - theta)^2)
    expected = 0.004 / np.sqrt(1 - 0.98**2)
    assert 0.6 * expected < x.std() < 1.4 * expected


def test_simulated_publisher_end_to_end(tmp_path):
    msgs = list(sp.messages("SIM50", ["sim-a", "sim-b"], T, 600, seed=1))
    r = sp.run_local(tmp_path, iter(msgs), batch=100)
    assert r == {"written": 1200, "rejected": 0}
    ts, fs = LocalGridLog(tmp_path).read("SIM50", T, T + 599)
    assert np.array_equal(ts, np.arange(T, T + 600))
    per_sec: dict[int, list[float]] = {}
    for m in msgs:
        per_sec.setdefault(m["t_utc_s"], []).append(m["freq_hz"])
    assert np.allclose(fs, [np.median(per_sec[int(t)]) for t in ts], atol=1e-6)
    assert np.all(np.abs(fs - 50.0) < 0.5)
    assert len(list((tmp_path / "SIM50").glob("*.csv"))) == 2
    rows = data_quality.read_local_rows(tmp_path, "SIM50", T, T + 599)
    assert {r["source"] for r in rows} == {"sim"}
    rep = data_quality.analyze(rows, T, T + 599, 50.0)
    assert rep["coverage_pct"] == 100.0 and rep["gps_lock_pct"] == 100.0 and rep["gaps"] == []


def test_invalid_messages_are_not_written(tmp_path):
    msgs = list(sp.messages("SIM50", ["sim-a"], T, 10, seed=1))
    msgs[3]["freq_hz"] = 99.0
    msgs[4]["quality"] = "gps"
    msgs[4]["gps_lock"] = False
    r = sp.run_local(tmp_path, iter(msgs))
    assert r == {"written": 8, "rejected": 2}
    ts, _ = LocalGridLog(tmp_path).read("SIM50", T, T + 9)
    assert set(ts.tolist()) == set(range(T, T + 10)) - {T + 3, T + 4}
