from __future__ import annotations

import numpy as np

from node.ingest.aws_gridlog import DynamoGridLog

T = 1789948800  # 2026-09-21T00:00:00Z


def test_write_read_median_across_days_and_pages(fake_table):
    log = DynamoGridLog(table=fake_table)
    t = np.arange(T - 100, T + 100, dtype=np.int64)  # crosses a UTC day boundary
    log.write("IN", t, np.full(t.size, 50.01), source="node", node="a")
    log.write("IN", t, np.full(t.size, 50.03), source="node", node="b")
    log.write("IN", t[:10], np.full(10, 50.05), source="node", node="c")
    ts, fs = log.read("IN", T - 100, T + 99)
    assert ts.dtype == np.int64 and fs.dtype == np.float64
    assert np.array_equal(ts, t)
    assert np.allclose(fs[:10], 50.03) and np.allclose(fs[10:], 50.02)
    assert log.latest("IN", now_s=T + 500) == T + 99
    assert log.latest("CE", now_s=T + 500) is None


def test_read_empty(fake_table):
    ts, fs = DynamoGridLog(table=fake_table).read("IN", T, T + 10)
    assert ts.size == 0 and fs.size == 0
