#!/usr/bin/env python3
"""Generate one daily snapshot of the HDD Price Index and refresh the dataset files.

This is the automated, byte-format-compatible reproduction of the manual daily
refresh. It reads the live, public, no-auth PostgREST API over the HDDHunt
catalogue and (re)writes, for the current UTC day:

  - price-index-YYYY-MM-DD.csv    dated, immutable snapshot (one row per tier)
  - price-index-YYYY-MM-DD.json   same snapshot with full per-pick detail
  - price-index-latest.csv        copy of today's CSV (always the newest)
  - price-index-timeseries.jsonl  append-only, one compact record per day

Each tier carries TWO $/TB metrics over the identical qualifying universe:
  - cheapest_usd_per_tb : the single lowest $/TB listing (a deal, volatile day-to-day)
  - median_usd_per_tb   : the median $/TB across ALL qualifying listings in the tier
                          (a structural, deal-noise-resistant figure). Added 2026-08-20.

The median is the more citable metric for a durable claim: it states the market
floor ("~$48/TB is the practical floor for 16TB+ new SATA HDDs") rather than a
single discounted listing that can vanish in 24h.

Methodology (matches README.md exactly):
  Universe  : Amazon.com (US), condition=New, technology=HDD, interface=SATA,
              form_factor=Internal 3.5" (SAS/USB excluded — directly usable drives).
  Tiering   : nominal capacity tiers 4..24 TB; per tier the single cheapest
              qualifying drive by $/TB, using band [(T-1)*1024, (T+0.25)*1024) GB
              (the exact band documented in the README "verify it yourself" block).
  Median    : the median of every qualifying drive's $/TB in that same band
              (same universe as the cheapest pick), computed over sane values only.
  Tier depth: new_hdd_listings_in_tier = count of ALL new HDD in the band
              (index depth / how competitive the tier is).

Safety:
  - Idempotent: if today's date is already in the time series, does nothing
    (unless FORCE=1, which re-generates and REPLACES today's record — used the
    day the median series was introduced to seed it consistently with cheapest).
  - Validates every tier resolves to a sane $/TB before writing ANY file, so an
    upstream outage or malformed response never corrupts the published dataset.

Usage:
  python3 scripts/generate-snapshot.py            # today (UTC)
  DATE=2026-08-18 python3 scripts/generate-snapshot.py   # override (testing)
  FORCE=1 python3 scripts/generate-snapshot.py    # re-generate & replace today
"""

import csv
import io
import json
import os
import statistics
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

# Minimum sane listings in a tier before we publish a median for it. Below this
# the median is statistically meaningless, so we publish null (cheapest still ships).
MIN_MEDIAN_SAMPLES = 3

# Pull all qualifying $/TB values per tier in pages of this size (PostgREST caps
# a single response, so the median needs pagination, not just the cheapest row).
PAGE = 50
MAX_OFFSET = 5000  # hard safety stop; no real tier is anywhere near this deep

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


# Fake-capacity scam guard (added 2026-08-27; mirrors the private
# tools/price-index-snapshot.sh guard applied 2026-08-25). The server-side filters
# (form_factor / interface / condition) do NOT catch mislabelled listings — a drive
# sold as "24TB" that is physically ~8TB passes every filter and lands as a bogus
# sub-$20/TB "floor". We fetch the cheapest ~12 rows, take the median of their $/TB
# as a robust reference, and pick the cheapest row that is >= 65% of that median.
# Genuine deals (within ~35% of the cluster) are kept; fake-capacity artifacts
# (~50-65% below the cluster) are skipped and logged. This preserves "cheapest $/TB"
# semantics — only implausible scam floors are dropped.
GUARD_SAMPLE = 12
GUARD_RATIO = 0.65


def fetch_pick(tier):
    """Cheapest qualifying drive in the tier, after the fake-capacity scam guard."""
    lo, hi = _band(tier)
    params = list(PICK_FILTERS) + [
        ("capacity_gb", f"gte.{lo}"),
        ("capacity_gb", f"lt.{hi}"),
        ("order", "price_per_tb.asc"),
        ("select", "name,brand,capacity_gb,price,price_per_tb,form_factor,interface,last_updated"),
        ("limit", str(GUARD_SAMPLE)),
    ]
    _, body = _get(params, {})
    rows = [r for r in json.loads(body) if r.get("price_per_tb") is not None]
    if not rows:
        return None
    if len(rows) < 3:
        return rows[0]  # too few listings to judge plausibility — take the cheapest
    ppts = [float(r["price_per_tb"]) for r in rows]
    ref = statistics.median(ppts)  # robust to 1-3 deep fake-capacity outliers
    floor_min = GUARD_RATIO * ref
    picked = next((r for r in rows if float(r["price_per_tb"]) >= floor_min), rows[0])
    dropped = [round(p, 2) for p in ppts if p < floor_min]
    if dropped:
        print("price-index: tier %dTB SCAM-GUARD dropped %s (< %.2f = %.0f%% of "
              "cheapest-%d median %.2f); floor=%.2f"
              % (tier, dropped, floor_min, GUARD_RATIO * 100, GUARD_SAMPLE, ref,
                 float(picked["price_per_tb"])), file=sys.stderr)
    return picked


def fetch_tier_ppt_values(tier):
    """Every qualifying $/TB in the tier band (same universe as the cheapest pick),
    clamped to the sane [MIN_PPT, MAX_PPT] window, returned sorted ascending."""
    lo, hi = _band(tier)
    vals = []
    offset = 0
    while offset <= MAX_OFFSET:
        params = list(PICK_FILTERS) + [
            ("capacity_gb", f"gte.{lo}"),
            ("capacity_gb", f"lt.{hi}"),
            ("order", "price_per_tb.asc"),
            ("select", "price_per_tb"),
            ("limit", str(PAGE)),
            ("offset", str(offset)),
        ]
        _, body = _get(params, {})
        chunk = json.loads(body)
        if not chunk:
            break
        for row in chunk:
            ppt = row.get("price_per_tb")
            if ppt is None:
                continue
            ppt = float(ppt)
            if MIN_PPT <= ppt <= MAX_PPT:
                vals.append(ppt)
        if len(chunk) < PAGE:
            break
        offset += PAGE
    vals.sort()
    return vals


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
    force = os.environ.get("FORCE") == "1"

    ts_path = os.path.join(REPO_ROOT, "price-index-timeseries.jsonl")
    existing_lines = []
    if os.path.exists(ts_path):
        with open(ts_path, encoding="utf-8") as f:
            existing_lines = f.readlines()
        already = any(f'"date": "{day}"' in line for line in existing_lines)
        if already and not force:
            print(f"price-index: {day} already recorded — nothing to do "
                  f"(set FORCE=1 to re-generate).", file=sys.stderr)
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
        vals = fetch_tier_ppt_values(tier)
        if len(vals) >= MIN_MEDIAN_SAMPLES:
            median = round(statistics.median(vals), 2)
        else:
            median = None  # too few listings for a meaningful median; cheapest still ships
        picks.append((tier, pick, depth, median, len(vals)))

    # --- dated CSV + latest CSV ---
    header = [
        "capacity_tb", "cheapest_usd_per_tb", "median_usd_per_tb", "median_sample_n",
        "price_usd", "drive", "brand", "interface", "form_factor",
        "new_hdd_listings_in_tier", "listing_last_updated", "snapshot_date",
    ]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for tier, pick, depth, median, msn in picks:
        w.writerow([
            tier,
            round(float(pick["price_per_tb"]), 2),
            "" if median is None else median,
            msn,
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
    for tier, pick, depth, median, msn in picks:
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
            "tier_median_price_per_tb": median,
            "tier_median_sample_n": msn,
        })
    with open(os.path.join(REPO_ROOT, f"price-index-{day}.json"), "w", encoding="utf-8") as f:
        json.dump(detail, f, indent=2)
        f.write("\n")

    # --- append to time series ---
    per_tier = {str(tier): round(float(pick["price_per_tb"]), 2) for tier, pick, _, _, _ in picks}
    median_per_tier = {str(tier): median for tier, _, _, median, _ in picks}
    median_n_per_tier = {str(tier): msn for tier, _, _, _, msn in picks}
    vals = {int(k): v for k, v in per_tier.items()}
    cheapest_tier = min(vals, key=vals.get)
    dearest_tier = max(vals, key=vals.get)
    # Structural floor for large drives = median of the per-tier medians for 16TB+.
    big_medians = [median for tier, _, _, median, _ in picks if tier >= 16 and median is not None]
    median_floor_16tb_plus = round(statistics.median(big_medians), 2) if big_medians else None
    rec = {
        "date": day,
        "metric": METRIC,
        "per_tier": per_tier,
        "cheapest_tier_tb": cheapest_tier,
        "cheapest_usd_per_tb": vals[cheapest_tier],
        "dearest_tier_tb": dearest_tier,
        "dearest_usd_per_tb": vals[dearest_tier],
        "median_per_tier": median_per_tier,
        "median_sample_n_per_tier": median_n_per_tier,
        "median_floor_16tb_plus_usd_per_tb": median_floor_16tb_plus,
    }
    # Replace today's line if it already exists (FORCE re-run), else append.
    new_line = json.dumps(rec) + "\n"
    kept = [ln for ln in existing_lines if f'"date": "{day}"' not in ln]
    with open(ts_path, "w", encoding="utf-8") as f:
        f.writelines(kept)
        f.write(new_line)

    print(f"price-index: wrote snapshot for {day} "
          f"(cheapest {cheapest_tier}TB ${vals[cheapest_tier]}/TB, "
          f"dearest {dearest_tier}TB ${vals[dearest_tier]}/TB, "
          f"16TB+ median floor ${median_floor_16tb_plus}/TB).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
