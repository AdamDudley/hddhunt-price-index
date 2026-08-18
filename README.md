# HDD Price Index

An open dataset tracking the **cheapest new, internal 3.5" SATA hard drive price per
terabyte (USD/TB)** at each capacity tier (4 TB – 24 TB) on Amazon.com (US).

**Live index:** the always-current version, with the full per-TB-by-capacity table and
methodology, is published at
**[hddhunt.com/cheapest-hdd-per-tb](https://hddhunt.com/cheapest-hdd-per-tb/)**. This
repository is the downloadable, machine-readable companion to that page.

The index answers one durable question — *"what is the actual cheapest way to buy a
terabyte of new spinning disk right now, and is bigger really cheaper per TB?"* — and
tracks how that answer moves over time. In the 2026 supply crunch the per-TB sweet
spot is **not** the largest drive: on the 2026-08-17 snapshot, **4 TB leads at
$23.80/TB** while **16 TB is the worst value at $34.48/TB**, and **14 TB ($24.99/TB)
is ~38% cheaper per TB than 16 TB**. Those relationships shift week to week as
individual models go on and off sale, which is exactly why this is published as a
dated, self-updating index rather than a one-off article.

All files download directly, no login or purchase required. Free to reuse under
[CC BY 4.0](./LICENSE) with attribution to [HDDHunt](https://hddhunt.com/).

## Files

| File | What it is |
|---|---|
| `price-index-latest.csv` | Most recent snapshot — one row per capacity tier (the cheapest qualifying drive in that tier). Always points at the newest data. |
| `price-index-YYYY-MM-DD.csv` | Dated, immutable copy of each snapshot. |
| `price-index-YYYY-MM-DD.json` | Same snapshot with full per-pick detail (model, price, per-TB, listing timestamp, tier depth). |
| `price-index-timeseries.jsonl` | Append-only daily time series — one JSON object per day, with the full per-tier `$/TB` curve. |

## Columns (`*.csv`)

| Column | Meaning |
|---|---|
| `capacity_tb` | Nominal drive capacity tier, in TB. |
| `cheapest_usd_per_tb` | Cheapest qualifying drive's price ÷ capacity, USD per TB (rounded to 2dp). |
| `price_usd` | List price of that cheapest drive, USD. |
| `drive` | Full product title of the cheapest qualifying drive. |
| `brand` | Manufacturer / brand. |
| `interface` | Host interface (SATA). |
| `form_factor` | Physical form factor (Internal 3.5"). |
| `new_hdd_listings_in_tier` | Number of *new* HDD listings surveyed in that capacity tier (index depth / how competitive the tier is). |
| `listing_last_updated` | When that specific listing's price was last refreshed (UTC). |
| `snapshot_date` | Date of the snapshot. |

## Methodology

- **Universe:** Amazon.com (US) marketplace listings from the HDDHunt catalogue
  (~8,500 listings total). Each snapshot surveys the **new, internal 3.5" SATA** HDDs
  — the drive a normal buyer can actually put in a case or NAS. SAS server pulls and
  USB externals are **excluded** so the per-TB number reflects a directly usable
  drive, not a shucking project or a data-centre-only part.
- **Tiering:** listings are bucketed into nominal capacity tiers (4, 6, 8, 10, 12,
  14, 16, 18, 20, 22, 24 TB). For each tier the index records the single cheapest
  qualifying drive by `$/TB`.
- **Cadence:** refreshed on a **daily** accrual cadence; `price-index-latest.csv`
  tracks the newest snapshot and `price-index-timeseries.jsonl` accumulates the
  history.
- **Reproducibility (verify it yourself):** the underlying listings are exposed
  through a **public, no-auth PostgREST API**. For any tier T (e.g. 16 TB), the
  cheapest new internal 3.5" SATA HDD is:

  ```bash
  curl -s -H 'Range: 0-49' \
    'https://postgrest.hddhunt.com/drives?marketplace=eq.amazon.com&technology=eq.HDD&condition=eq.New' \
    --data-urlencode 'capacity_gb=gte.15360' \
    --data-urlencode 'capacity_gb=lt.16640' \
    --data-urlencode 'order=price_per_tb.asc' -G | head
  ```

## Caveats

- Prices are marketplace list prices at snapshot time; they move constantly and a
  single discounted listing can swing a tier's `$/TB` sharply day to day (that
  volatility is the point of tracking a time series).
- Coverage is Amazon.com (US) only.
- This is descriptive market data, not purchasing advice.

## License

[Creative Commons Attribution 4.0 International (CC BY 4.0)](./LICENSE). You may share
and adapt the data for any purpose with attribution to
**HDDHunt — https://hddhunt.com/**.
