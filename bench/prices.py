"""On-demand EC2 prices from the AWS Price List API (SPEC Part 4 V12, Part 12).

No price is ever written by hand. This script calls `pricing:GetProducts` (service code `AmazonEC2`)
through the Price List endpoint in `us-east-1`, keeps the raw response, and parses the USD per hour
on-demand rate. Output: `results/bench/<date>/prices.json` with the query date and the source.

Usage:
    python -m bench.prices c7i.2xlarge c8g.2xlarge [--region us-east-1] [--profile gridprint]

Needs AWS credentials (human task H1). Without them the script stops with an error; it never
falls back to a guessed price.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]

# The Price List API serves only from a few endpoint regions; us-east-1 is one of them.
PRICING_ENDPOINT_REGION = "us-east-1"
SERVICE_CODE = "AmazonEC2"

# The Price List API filters on the location display name, not on the region code.
# Add a region here only after you check its display name in a GetProducts response.
LOCATION_NAMES: dict[str, str] = {
    "us-east-1": "US East (N. Virginia)",
}

SOURCE = "AWS Price List API, pricing:GetProducts, ServiceCode=AmazonEC2, endpoint us-east-1"


class PriceError(RuntimeError):
    """The response did not give exactly one usable on-demand hourly USD price."""


def build_filters(instance_type: str, location: str) -> list[dict[str, str]]:
    """Filters for one Linux, shared-tenancy, no-preinstalled-software, on-demand instance price."""
    pairs = {
        "instanceType": instance_type,
        "location": location,
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
    }
    return [{"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in pairs.items()]


def _on_demand_usd_per_hour(product: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    on_demand = product.get("terms", {}).get("OnDemand", {})
    for term_code, term in on_demand.items():
        for rate_code, dim in term.get("priceDimensions", {}).items():
            unit = dim.get("unit", "")
            usd = dim.get("pricePerUnit", {}).get("USD")
            if usd is None or unit not in ("Hrs", "Hours"):
                continue
            out.append({
                "offer_term_code": term_code,
                "rate_code": rate_code,
                "usd_per_hour": float(usd),
                "unit": unit,
                "description": dim.get("description", ""),
                "effective_date": term.get("effectiveDate"),
            })
    return out


def parse_price_list(price_list: list[str | dict[str, Any]], instance_type: str) -> dict[str, Any]:
    """Parse the `PriceList` items of a GetProducts response for one instance type.

    Each item is a JSON string (as boto3 returns it) or an already-decoded dict.
    Exactly one non-zero hourly USD on-demand rate must remain, or PriceError is raised.
    """
    candidates: list[dict[str, Any]] = []
    for item in price_list:
        product = json.loads(item) if isinstance(item, str) else item
        attrs = product.get("product", {}).get("attributes", {})
        if attrs.get("instanceType") != instance_type:
            continue
        for rate in _on_demand_usd_per_hour(product):
            if rate["usd_per_hour"] <= 0.0:
                continue
            rate["sku"] = product.get("product", {}).get("sku")
            rate["attributes"] = {k: attrs.get(k) for k in (
                "instanceType", "location", "regionCode", "operatingSystem", "tenancy",
                "preInstalledSw", "capacitystatus", "vcpu", "memory", "physicalProcessor")}
            candidates.append(rate)
    if len(candidates) != 1:
        raise PriceError(
            f"{instance_type}: expected exactly one hourly USD on-demand rate, found {len(candidates)}")
    return candidates[0]


def fetch_raw(client: Any, instance_type: str, location: str) -> list[str]:
    """Call GetProducts with pagination and return all PriceList items."""
    items: list[str] = []
    kwargs: dict[str, Any] = {
        "ServiceCode": SERVICE_CODE,
        "Filters": build_filters(instance_type, location),
        "FormatVersion": "aws_v1",
        "MaxResults": 100,
    }
    while True:
        resp = client.get_products(**kwargs)
        items.extend(resp.get("PriceList", []))
        token = resp.get("NextToken")
        if not token:
            return items
        kwargs["NextToken"] = token


def collect(client: Any, instance_types: list[str], region: str,
            today: dt.date | None = None) -> dict[str, Any]:
    if region not in LOCATION_NAMES:
        raise PriceError(f"no verified location name for region {region}; add it to LOCATION_NAMES")
    location = LOCATION_NAMES[region]
    today = today or dt.datetime.now(dt.UTC).date()
    doc: dict[str, Any] = {
        "source": SOURCE,
        "query_date_utc": today.isoformat(),
        "region": region,
        "location": location,
        "raw": {},
        "prices": {},
    }
    for it in instance_types:
        raw = fetch_raw(client, it, location)
        doc["raw"][it] = [json.loads(x) if isinstance(x, str) else x for x in raw]
        doc["prices"][it] = parse_price_list(raw, it)
    return doc


def write(doc: dict[str, Any], results_dir: Path) -> Path:
    out = results_dir / "bench" / doc["query_date_utc"] / "prices.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    return out


def _config() -> dict[str, Any]:
    with open(REPO / "config" / "default.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv: list[str] | None = None) -> int:
    cfg = _config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("instance_types", nargs="+")
    ap.add_argument("--region", default=cfg["aws"]["region"])
    ap.add_argument("--profile", default=cfg["aws"]["profile"])
    ap.add_argument("--results", type=Path, default=REPO / "results")
    args = ap.parse_args(argv)

    import boto3  # imported here so tests and parsing do not need AWS

    session = boto3.Session(profile_name=args.profile)
    client = session.client("pricing", region_name=PRICING_ENDPOINT_REGION)
    try:
        doc = collect(client, args.instance_types, args.region)
    except PriceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    path = write(doc, args.results)
    for it, p in doc["prices"].items():
        print(f"{it}: {p['usd_per_hour']} USD/h ({doc['location']}, {doc['query_date_utc']}) -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
