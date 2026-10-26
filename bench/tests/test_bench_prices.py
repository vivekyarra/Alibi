"""Tests for bench/prices.py parsing. The fake response mirrors the GetProducts shape
(PriceList = list of JSON strings with product.attributes and terms.OnDemand.*.priceDimensions.*).
The rate value below is a test fixture, not a real price."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from bench import prices

FIXTURE_RATE = "1.2345000000"   # test value only


def _product(instance_type: str, usd: str, unit: str = "Hrs", sku: str = "SKU1") -> str:
    return json.dumps({
        "product": {
            "sku": sku,
            "productFamily": "Compute Instance",
            "attributes": {
                "instanceType": instance_type, "location": "US East (N. Virginia)", "regionCode": "us-east-1",
                "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA",
                "capacitystatus": "Used", "vcpu": "8", "memory": "16 GiB",
            },
        },
        "serviceCode": "AmazonEC2",
        "terms": {"OnDemand": {f"{sku}.JRTCKXETXF": {
            "offerTermCode": "JRTCKXETXF", "sku": sku, "effectiveDate": "2026-10-01T00:00:00Z",
            "priceDimensions": {f"{sku}.JRTCKXETXF.6YS6EN2CT7": {
                "unit": unit, "description": "fixture", "pricePerUnit": {"USD": usd}}},
        }}},
    })


class FakePricing:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_products(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def test_filters_cover_required_fields() -> None:
    f = {x["Field"]: x["Value"] for x in prices.build_filters("c8g.2xlarge", "US East (N. Virginia)")}
    assert f == {"instanceType": "c8g.2xlarge", "location": "US East (N. Virginia)",
                 "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA",
                 "capacitystatus": "Used"}


def test_parse_single_rate() -> None:
    r = prices.parse_price_list([_product("c8g.2xlarge", FIXTURE_RATE)], "c8g.2xlarge")
    assert r["usd_per_hour"] == float(FIXTURE_RATE)
    assert r["sku"] == "SKU1"
    assert r["attributes"]["vcpu"] == "8"


def test_parse_ignores_zero_and_other_types() -> None:
    items = [_product("c8g.2xlarge", "0.0000000000", sku="Z"), _product("c7i.2xlarge", FIXTURE_RATE, sku="X"),
             _product("c8g.2xlarge", FIXTURE_RATE, sku="Y")]
    assert prices.parse_price_list(items, "c8g.2xlarge")["sku"] == "Y"


def test_parse_rejects_ambiguous_or_missing() -> None:
    with pytest.raises(prices.PriceError):
        prices.parse_price_list([], "c8g.2xlarge")
    with pytest.raises(prices.PriceError):
        prices.parse_price_list([_product("c8g.2xlarge", FIXTURE_RATE, sku="A"),
                                 _product("c8g.2xlarge", FIXTURE_RATE, sku="B")], "c8g.2xlarge")


def test_collect_paginates_and_writes(tmp_path: Path) -> None:
    client = FakePricing([
        {"PriceList": [], "NextToken": "t1"},
        {"PriceList": [_product("c8g.2xlarge", FIXTURE_RATE)]},
    ])
    doc = prices.collect(client, ["c8g.2xlarge"], "us-east-1", today=dt.date(2026, 10, 26))
    assert len(client.calls) == 2
    assert client.calls[1]["NextToken"] == "t1"
    assert client.calls[0]["ServiceCode"] == "AmazonEC2"
    out = prices.write(doc, tmp_path)
    assert out == tmp_path / "bench" / "2026-10-26" / "prices.json"
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["prices"]["c8g.2xlarge"]["usd_per_hour"] == float(FIXTURE_RATE)
    assert saved["raw"]["c8g.2xlarge"][0]["product"]["sku"] == "SKU1"
    assert saved["source"].startswith("AWS Price List API")


def test_unknown_region_is_an_error() -> None:
    with pytest.raises(prices.PriceError):
        prices.collect(FakePricing([]), ["c8g.2xlarge"], "xx-nowhere-1")
