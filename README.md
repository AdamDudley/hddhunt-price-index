# HDD Price Index

An open dataset tracking the **cheapest new, internal 3.5" SATA hard drive price per
terabyte (USD/TB)** at each capacity tier (4 TB – 24 TB) on Amazon.com (US).

**Live index:** the always-current version, with the full per-TB-by-capacity table and
methodology, is published at
**[hddhunt.com/cheapest-hdd-per-tb](https://hddhunt.com/cheapest-hdd-per-tb/)**. This
repository is the downloadable, machine-readable companion to that page.

**At a glance** — a live, self-updating card of the lowest `$/TB` listings on the
site right now, rendered fresh from HDDHunt's daily snapshot (it is not a static
screenshot). Note this card is a *cheapest-deal ranking* across capacities and shows
**each row's condition** (some entries may be **refurbished**), so it is a broader,
more volatile view than this repository's dataset, which is filtered to **new** drives
and organised **by capacity tier**:

[![Live "Cheapest HDD per TB today" card — lowest $/TB listings on HDDHunt, condition-tagged](https://hddhunt.com/embed/cheapest-hdd-per-tb.png)](https://hddhunt.com/cheapest-hdd-per-tb/)

Each capacity tier carries **two** `$/TB` figures, because they answer two different
questions:

- **`cheapest_usd_per_tb`** — the single lowest-priced qualifying listing right now.
  This is *today's best deal*, and it is **volatile**: one discounted model going on
  or off sale swings it sharply day to day, so which tier looks "cheapest" flips
  around (on the 2026-08-20 snapshot 4 TB leads at $23.80/TB, but that is a single
  deal, not a structural fact). Track the time series, not any one day, for this
  number.
- **`median_usd_per_tb`** — the median `$/TB` across *all* qualifying listings in the
  tier. This is the **structural** figure, robust to any one discounted listing, and
  it tells the durable story: per-TB cost is **high for small drives, falls with
  capacity, and then flattens**. On 2026-08-20 the median runs from ~$63/TB at 4 TB
  down to a plateau of **~$48/TB across 16–24 TB** (16 TB $58.97, 18 TB $43.71,
  20 TB $49.55, 24 TB $45.00). The practical takeaway: **the median $/TB sweet spot
  is ~16 TB and up — buying bigger than ~16 TB does not meaningfully lower your cost
  per terabyte on the typical listing.**

Publishing both — a volatile deal number and a stable structural number — is exactly
why this is a dated, self-updating index rather than a one-off article.
`price-index-latest.csv` always holds the current numbers.

All files download directly, no login or purchase required. Free to reuse under
[CC BY 4.0](./LICENSE) with attribution to [HDDHunt](https://hddhunt.com/).

## Files

| File | What it is |
|---|---|
| `price-index-latest.csv` | Most recent snapshot — one row per capacity tier (the cheapest qualifying drive in that tier). Always points at the newest data. |
| `price-index-YYYY-MM-DD.csv` | Dated, immutable copy of each snapshot. |
| `price-index-YYYY-MM-DD.json` | Same snapshot with full per-pick detail (model, price, per-TB, listing timestamp, tier depth). |
| `price-index-timeseries.jsonl` | Append-only daily time series — one JSON object per day, with the full per-tier `$/TB` curve (both `per_tier` cheapest and `median_per_tier`, plus the `median_floor_16tb_plus_usd_per_tb` structural headline). |

## Columns (`*.csv`)

| Column | Meaning |
|---|---|
| `capacity_tb` | Nominal drive capacity tier, in TB. |
| `cheapest_usd_per_tb` | Cheapest qualifying drive's price ÷ capacity, USD per TB (rounded to 2dp). Volatile day-to-day — a single deal, not a structural figure. |
| `median_usd_per_tb` | **Median** `$/TB` across *all* qualifying listings in the tier (same universe as the cheapest pick). The structural, deal-noise-resistant metric. Added 2026-08-20; blank if a tier has fewer than 3 listings. |
| `median_sample_n` | Number of qualifying listings the median was computed over. |
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
  14, 16, 18, 20, 22, 24 TB). For each tier the index records two `$/TB` figures over
  the **identical** qualifying universe: the single **cheapest** qualifying drive by
  `$/TB`, and the **median** `$/TB` of every qualifying listing in that tier. The
  cheapest is a volatile deal number; the median is the structural one (robust to any
  single discounted listing). A tier needs at least 3 listings for a median to be
  published; otherwise `median_usd_per_tb` is blank.
- **Fake-capacity scam guard (since 2026-08-27):** marketplace filters cannot catch
  a mislabelled listing — a drive sold as "24 TB" that is physically ~8 TB passes
  every filter and would otherwise land as a bogus sub-$20/TB "floor". Before
  recording a tier's cheapest, the generator fetches the cheapest ~12 listings, takes
  the median of their `$/TB` as a robust reference, and keeps the cheapest listing
  that is **≥ 65 %** of that median; anything ~50-65 % below the cluster is treated as
  a fake-capacity artifact, skipped, and logged. Genuine deals within ~35 % of the
  cluster are unaffected. (Snapshots dated **before 2026-08-27** predate this guard,
  so the `cheapest_usd_per_tb` for a few tiers on those days may include an unfiltered
  mislabelled listing; the `median_usd_per_tb` figures are unaffected.)
- **Cadence:** refreshed on a **daily** accrual cadence by a scheduled job
  ([`.github/workflows/daily-snapshot.yml`](./.github/workflows/daily-snapshot.yml)
  running [`scripts/generate-snapshot.py`](./scripts/generate-snapshot.py) against
  the public API each morning UTC); `price-index-latest.csv` tracks the newest
  snapshot and `price-index-timeseries.jsonl` accumulates the history. The job is
  idempotent and refuses to write a partial or implausible snapshot, so the
  published series is never corrupted by an upstream glitch.
- **Reproducibility (verify it yourself):** the exact generation code is in this
  repo ([`scripts/generate-snapshot.py`](./scripts/generate-snapshot.py)) and the
  underlying listings are exposed through a **public, no-auth PostgREST API**. For
  any tier T (e.g. 16 TB), the cheapest new internal 3.5" SATA HDD is:

  ```bash
  curl -s -H 'Range: 0-49' \
    'https://postgrest.hddhunt.com/drives?marketplace=eq.amazon.com&technology=eq.HDD&condition=eq.New' \
    --data-urlencode 'capacity_gb=gte.15360' \
    --data-urlencode 'capacity_gb=lt.16640' \
    --data-urlencode 'order=price_per_tb.asc' -G | head
  ```

  The **median** for the same tier is the median of `price_per_tb` over *all* rows in
  that band (add `&form_factor=eq.Internal 3.5"&interface=eq.SATA`, page through with
  `limit`/`offset`, drop values outside a sane `[5, 500]` window). The exact code that
  does this — cheapest pick + median in one pass — is
  [`scripts/generate-snapshot.py`](./scripts/generate-snapshot.py).

## Caveats

- Prices are marketplace list prices at snapshot time; they move constantly and a
  single discounted listing can swing a tier's `$/TB` sharply day to day (that
  volatility is the point of tracking a time series).
- Coverage is Amazon.com (US) only.
- This is descriptive market data, not purchasing advice.

## Cite this dataset

Machine-readable citation metadata is provided in
[`CITATION.cff`](./CITATION.cff) — GitHub renders a **"Cite this repository"**
button from it. A permanent, versioned DOI (via Zenodo's GitHub-release archiving)
is being minted; once live it will appear here as a badge and in `CITATION.cff`.

Suggested attribution:

> HDDHunt. *HDD Price Index — cheapest new internal 3.5" SATA HDD price per TB
> (USD/TB), Amazon US.* https://hddhunt.com/cheapest-hdd-per-tb/

## License

[Creative Commons Attribution 4.0 International (CC BY 4.0)](./LICENSE). You may share
and adapt the data for any purpose with attribution to
**HDDHunt — https://hddhunt.com/**.
