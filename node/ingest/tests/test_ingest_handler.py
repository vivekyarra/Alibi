from __future__ import annotations

import json
from decimal import Decimal

import pytest

from node.ingest import handler as h

T = 1789948800  # 2026-09-21T00:00:00Z
NOW = T + 3600


def msg(**kw):
    m = {"zone": "IN", "node_id": "node-01", "t_utc_s": T, "freq_hz": 50.0123, "quality": "gps",
         "gps_lock": True}
    m.update(kw)
    return m


def test_day_key():
    assert h.day_key("IN", T) == "IN#20260921"
    assert h.day_key("IN", T - 1) == "IN#20260920"


@pytest.mark.parametrize("bad", [
    {"zone": "in"}, {"zone": ""}, {"node_id": "a b"}, {"t_utc_s": 1.5}, {"t_utc_s": True},
    {"t_utc_s": NOW + 10_000}, {"t_utc_s": 1000}, {"freq_hz": float("nan")}, {"freq_hz": 80.0},
    {"freq_hz": "50"}, {"quality": "bad"}, {"gps_lock": "yes"}, {"quality": "gps", "gps_lock": False},
    {"source": "neso"}, {"topic_zone": "CE"}, {"topic_node": "node-02"},
])
def test_validate_rejects(bad):
    with pytest.raises(h.ValidationError):
        h.validate(msg(**bad), now_s=NOW)


def test_validate_missing_field():
    m = msg()
    del m["gps_lock"]
    with pytest.raises(h.ValidationError):
        h.validate(m, now_s=NOW)


def test_validate_ok_ntp_and_topic():
    m = h.validate(msg(quality="ntp", gps_lock=False, topic_zone="IN", topic_node="node-01"), now_s=NOW)
    assert m["quality"] == "ntp" and m["source"] == "node" and m["t_utc_s"] == T


def test_allowed_zones_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ZONES", "CE,GB")
    with pytest.raises(h.ValidationError):
        h.validate(msg(), now_s=NOW)


def test_handle_writes_to_fake_table_with_median(fake_table):
    w = h.DynamoWriter(fake_table)
    r = h.handle([msg(node_id="a", freq_hz=50.010), msg(node_id="b", freq_hz=50.020),
                  msg(node_id="c", freq_hz=50.090, quality="ntp", gps_lock=False), {"junk": 1}], w, now_s=NOW)
    assert r["written"] == 3 and len(r["rejected"]) == 1
    it = fake_table.items[("IN#20260921", T)]
    assert it["freq"] == Decimal("50.020000")
    assert it["node"] == "a,b,c"
    assert it["quality"] == "ntp"  # not every reading is gps
    assert it["source"] == "node"
    assert it["version"] == 3
    assert set(it["readings"]) == {"a", "b", "c"}


def test_same_node_rewrite_replaces_reading(fake_table):
    w = h.DynamoWriter(fake_table)
    h.handle(msg(freq_hz=50.01), w, now_s=NOW)
    h.handle(msg(freq_hz=50.02), w, now_s=NOW)
    it = fake_table.items[("IN#20260921", T)]
    assert len(it["readings"]) == 1 and it["freq"] == Decimal("50.020000")


def test_conflict_is_retried(fake_table_cls):
    t = fake_table_cls(conflict_once=True)
    h.handle(msg(), h.DynamoWriter(t), now_s=NOW)
    assert t.put_calls == 2 and ("IN#20260921", T) in t.items


def test_lambda_handler_uses_injected_table(fake_table, monkeypatch):
    monkeypatch.setattr(h, "_TABLE", fake_table)
    r = h.lambda_handler(msg(t_utc_s=T + 5), None)
    assert r["written"] == 1 and ("IN#20260921", T + 5) in fake_table.items


def test_handle_accepts_json_string(fake_table):
    r = h.handle(json.dumps({"messages": [msg()]}), h.DynamoWriter(fake_table), now_s=NOW)
    assert r["written"] == 1


def test_entry_point_alias_matches_infra():
    assert h.handler is h.lambda_handler  # infra IoT stack uses handler="handler.handler"
