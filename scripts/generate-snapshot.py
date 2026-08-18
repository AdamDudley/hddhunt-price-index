#!/usr/bin/env python3
"""Generate one daily snapshot of the HDD Price Index and refresh the dataset files.

This is the automated, byte-format-compatible reproduction of the manual daily
refresh. It reads the live, public, no-auth PostgREST API over the HDDHunt
catalogue and (re)writes, for the current UTC day:

  - price-index-YYYY-MM-DD.csv    dated, immutable snapshot (one row per tier)
  - price-index-YYYY-MM-DD.json   same snapshot with full per-pick detail
  - price-index-latest.csv        copy of today's CSV (always the newest)
  - price-index-timeseries.jsonl  append-only, one compact record per day

Methodology (matches README.md exactly):
  Universe  : Amazon.com (US), condition=New, technology=HDD, interface=SATA,
              form_factor=Internal 3.5" (SAS/USB excluded — directly usable drives).
  Tiering   : nominal capacity tiers 4..24 TB; per tier the single cheapest
              qualifying drive by $/TB, using band [(T-1)*1024, (T+0.25)*1024) GB
              (the exact band documented in the README "verify it yourself" block).
  Tier depth: new_hdd_listings_in_tier = count of ALL new HDD in the band
              (index depth / how competitive the tier is).

Safety:
  - Idempotent: if today's date is already in the time series, does nothing.
  - Validates every tier resolves to a sane $/TB before writing ANY file, so an
    upstream outage or malformed response never corrupts the published dataset.

Usage:
  python3 scripts/generate-snapshot.py            # today (UTC)
  DATE=2026-08-18 python3 scripts/generate-snapshot.py   # override (testing)
"""

import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://postgrest.hddhunt.com/drives"
TIERS = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
METRIC = "cheapest_new_internal_3.5in_sata_usd_per_tb"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A qualifying $/TB below this or above this is treated as a data error and aborts
# the run without writing anything (e.g. a fake-capacity scam or an upstream glitch).
MIN_PPT, MAX_PPT = 5.0, 500.0

PICK_FILTERS = [
    ("marketplace", "eq.amazon.com"),
    ("technology", "eq.HDD"),
    ("condition", "eq.New"),
    ("form_factor", 'eq.Internal 3.5"'),
    ("interface", "eq.SATA"),
]
COUNT_FILTERS = [
    ("marketplace", "eq.amazon.com"),
    ("technology", "eq.HDD"),
    ("condition", "eq.New"),
]


def _band(tier):
    """Capacity band in GB for a nominal tier, per the published README method."""
    return int((tier - 1) * 1024), int((tier + 0.25) * 1024)


def _get(params, headers):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp, resp.read()


def fetch_pick(tier):
    lo, hi = _band(tier)
    params = list(PICK_FILTERS) + [
        ("capacity_gb", f"gte.{lo}"),
        ("capacity_gb", f"lt.{hi}"),
        ("order", "price_per_tb.asc"),
        ("select", "name,brand,capacity_gb,price,price_per_tb,form_factor,interface,last_updated"),
    ]
    _, body = _get(params, {"Range": "0-0"})
    rows = json.loads(body)
    return rows[0] if rows else None


def fetch_tier_depth(tier):
    lo, hi = _band(tier)
    params = list(COUNT_FILTERS) + [
        ("capacity_gb", f"gte.{lo}"),
        ("capacity_gb", f"lt.{hi}"),
    ]
    resp, _ = _get(params, {"Range": "0-0", "Prefer": "count=exact"})
    cr = resp.headers.get("Content-Range", "")  # e.g. "0-0/280"
    if "/" in cr:
        total = cr.split("/")[-1]
        if total.isdigit():
            return int(total)
    return None


def main():
    day = os.environ.get("DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ts_path = os.path.join(REPO_ROOT, "price-index-timeseries.jsonl")
    if os.path.exists(ts_path):
        with open(ts_path, encoding="utf-8") as f:
            if any(f'"date": "{day}"' in line for line in f):
                print(f"price-index: {day} already recorded — nothing to do.", file=sys.stderr)
                return 0

    picks = []
    for tier in TIERS:
        pick = fetch_pick(tier)
        if pick is None:
            print(f"ABORT: no qualifying drive for tier {tier} TB — refusing to write a partial snapshot.", file=sys.stderr)
            return 1
        ppt = float(pick["price_per_tb"])
        if not (MIN_PPT <= ppt <= MAX_PPT):
            print(f"ABORT: tier {tier} TB $/TB {ppt} outside sane range [{MIN_PPT},{MAX_PPT}] — likely bad data.", file=sys.stderr)
            return 1
        depth = fetch_tier_depth(tier)
        if depth is None:
            print(f"ABORT: could not read tier depth for tier {tier} TB.", file=sys.stderr)
            return 1
        picks.append((tier, pick, depth))

    # --- dated CSV + latest CSV ---
    header = [
        "capacity_tb", "cheapest_usd_per_tb", "price_usd", "drive", "brand",
        "interface", "form_factor", "new_hdd_listings_in_tier",
        "listing_last_updated", "snapshot_date",
    ]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for tier, pick, depth in picks:
        w.writerow([
            tier,
            round(float(pick["price_per_tb"]), 2),
            pick["price"],
            pick["name"],
            pick["brand"],
            pick["interface"],
            pick["form_factor"],
            depth,
            pick["last_updated"],
            day,
        ])
    csv_text = buf.getvalue()
    with open(os.path.join(REPO_ROOT, f"price-index-{day}.csv"), "w", encoding="utf-8") as f:
        f.write(csv_text)
    with open(os.path.join(REPO_ROOT, "price-index-latest.csv"), "w", encoding="utf-8") as f:
        f.write(csv_text)

    # --- dated JSON (full per-pick detail) ---
    detail = []
    for tier, pick, depth in picks:
        detail.append({
            "tier": tier,
            "pick": {
                "name": pick["name"],
                "brand": pick["brand"],
                "capacity_gb": pick["capacity_gb"],
                "price": pick["price"],
                "price_per_tb": pick["price_per_tb"],
                "form_factor": pick["form_factor"],
                "interface": pick["interface"],
                "last_updated": pick["last_updated"],
            },
            "tier_new_hdd_listings": str(depth),
        })
    with open(os.path.join(REPO_ROOT, f"price-index-{day}.json"), "w", encoding="utf-8") as f:
        json.dump(detail, f, indent=2)
        f.write("\n")

    # --- append to time series ---
    per_tier = {str(tier): round(float(pick["price_per_tb"]), 2) for tier, pick, _ in picks}
    vals = {int(k): v for k, v in per_tier.items()}
    cheapest_tier = min(vals, key=vals.get)
    dearest_tier = max(vals, key=vals.get)
    rec = {
        "date": day,
        "metric": METRIC,
        "per_tier": per_tier,
        "cheapest_tier_tb": cheapest_tier,
        "cheapest_usd_per_tb": vals[cheapest_tier],
        "dearest_tier_tb": dearest_tier,
        "dearest_usd_per_tb": vals[dearest_tier],
    }
    with open(ts_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

    print(f"price-index: wrote snapshot for {day} "
          f"(cheapest {cheapest_tier}TB ${vals[cheapest_tier]}/TB, "
          f"dearest {dearest_tier}TB ${vals[dearest_tier]}/TB).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
