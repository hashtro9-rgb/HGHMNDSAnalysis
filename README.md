# HGHMNDS Market Intelligence Dashboard

## Overview

An end-to-end, automated market-intelligence pipeline for HGHMNDS Clothing's
presence across Shopee Philippines and Lazada Philippines. It scrapes product
listings and reviews, cleans and flags the data (including third-party
knockoff/counterfeit listings), runs exploratory analysis, and serves the
results as a live 7-tab dashboard (Overview, Sales, Pricing, Reviews,
Recommendations, Products, About). A scheduled GitHub Actions run rescrapes
weekly, diffs against the previous snapshot, rebuilds every chart and JSON
export, emails a summary report, and redeploys the dashboard — with no
manual intervention.

**Snapshot at last analysis**: 221 verified HGHMNDS listings (118 Shopee,
103 Lazada), 1,812 reviews scraped, 54 additional listings flagged as
suspicious/knockoff and excluded from the analytics shown.

## Data Sources

- **Shopee Philippines** — product listings, pricing, ratings, and reviews for
  the HGHMNDS Clothing storefront and third-party sellers using the brand name,
  via Shopee's internal JSON search/detail/review APIs (session-cookie
  approach; the item-detail endpoint is blocked by anti-bot measures more
  often than not).
- **Lazada Philippines** — same, via headless Playwright browsing (search
  cards + per-product detail pages with rotating user agents and retries),
  since Lazada exposes different fields (lifetime sold count vs Shopee's
  30-day figure) and has no public JSON search API.

Raw scrape output lives in `data/raw/` and is **not committed** to this repo
(see `.gitignore`) — it is the untouched source of truth the cleaning
pipeline reads from. Only the cleaned, derived data (`data/cleaned/`) and the
dashboard's JSON exports (`assets/data/`) are version-controlled.

## Key Findings

- **Shopee lists at a premium; Lazada moves more verified volume.** Shopee's
  median price (₱620) beats Lazada's (₱500), and Shopee carries far more
  reviews (1,431 vs 381) and a higher average rating (4.88★ vs 4.40★). But
  `sold_final` is 0 across every Shopee listing — **confirmed a genuine,
  permanent platform limitation**: Shopee's public search API no longer
  returns real sold counts at all, even in fully successful responses where
  other fields (`rating_avg`, `review_count`) come back correctly populated
  and varied. Only Lazada's `sold_lifetime` (41,906 units total) is usable
  for sales-volume analysis; `review_count`/`rating_avg` stand in as the
  Shopee engagement proxy everywhere sales volume would otherwise appear.
- **T-Shirt dominates the catalog** — 187 of 221 listings (85%), reflecting
  that HGHMNDS is fundamentally a graphic-tee brand. The remainder splits
  across Accessories (8), Longsleeves (7), Bottoms (5), Jersey (5),
  Hoodie/Sweatshirt (3), Eyewear (3), Headwear (2), and Tanktop (1). Category
  is derived from product-name keywords, with abstractly-named products
  (e.g. "AURORA - HGHMNDS", "HGHMNDS - DIAGRAM") defaulting to T-Shirt since
  that's what they overwhelmingly turn out to be.
- **All 5 of the top-5 bestsellers are Lazada T-shirts at ₱750** — AURORA
  (6,400 sold), THE COSMIC PROCESS (5,800), DIAGRAM (5,000), SURFER (3,900),
  and FREEDOM T-SHIRT (3,900). Shopee has no comparable ranking available
  due to the sold-count limitation above.
- **Lazada carries far more knockoff risk than Shopee.** 40.8% of Lazada
  listings are flagged `is_suspicious` (discount > 80% or price under ₱250)
  vs 10.2% on Shopee — classic fake-original-price knockoffs, e.g. a "₱7,777"
  original marked down to ₱199. The average discount among flagged listings
  is 82.5%, well beyond anything a legitimate sale would offer. These 54
  listings are excluded from all dashboard analytics.
- **Ratings barely correlate with review volume** (Pearson r ≈ 0.20 on
  Shopee, 0.19 on Lazada) — popular items aren't systematically rated higher
  or lower than niche ones; rating quality and sales volume are largely
  independent signals here.
- **Reviews mix English and Filipino.** Word-frequency analysis on 1-star
  reviews is dominated by Filipino function words (ng, sa, na, mga) since the
  stopword list used is English-only — negative reviews skew more
  Filipino-language than 5-star reviews. A bilingual stopword list would
  sharpen this analysis further.

## Structure

```
HGHMNDSAnalysis/
├── .github/workflows/
│   ├── deploy.yml            CI: rebuild charts/JSON from committed cleaned data,
│   │                         bundle into dashboard/, deploy to Pages on every push
│   └── weekly_pipeline.yml   Sunday cron + manual trigger: full scrape -> clean ->
│                             EDA -> export -> notify -> commit -> deploy
├── assets/
│   └── data/                 JSON exports consumed by the dashboard (products,
│                              reviews, summary, categories, price_ranges, weekly_diff)
├── config/
│   └── settings.py           Keywords, thresholds, paths, notification config
├── dashboard/
│   ├── index.html            7-tab dashboard shell (Power BI style command center)
│   ├── style.css             Dark-blue design system
│   └── script.js             Data loading, Chart.js visuals, filtering, drawer, KPIs
├── data/
│   ├── raw/                  Latest + timestamped raw scrapes (git-ignored)
│   ├── cleaned/               Cleaned CSVs/Excel (committed, CI builds from these)
│   └── archive/               Weekly snapshots of data/cleaned/, pruned to KEEP_WEEKS
├── docs/                     Supplementary documentation
├── logs/                     Pipeline run logs, status JSON, fallback notification reports
├── notebooks/                Jupyter walkthrough of the analysis
├── scripts/
│   ├── 01_scrape.py          Headless scrape (Shopee API + Lazada Playwright,
│   │                         UA rotation + retries) + weekly diff vs last run
│   ├── 02_clean.py           Cleaning pipeline: authenticity/suspicious flagging,
│   │                         category derivation, review normalization
│   ├── 03_eda.py             Exploratory analysis + chart generation
│   ├── 04_export_json.py     Dashboard JSON export
│   ├── 05_notify.py          Email summary report (Gmail SMTP, fallback to logs/)
│   └── run_pipeline.py       Runs 01-05 in sequence; logs, archives, status tracking;
│                             never crashes silently
└── tests/                    12 pytest checks on cleaned data + pipeline artifacts
```

## How to Run

```bash
pip install -r requirements.txt
playwright install chromium

python scripts/run_pipeline.py    # full pipeline: scrape -> clean -> EDA -> export -> notify
```

Or run each stage independently:

```bash
python scripts/01_scrape.py         # data/raw/hghmnds_MERGED_[ts].xlsx + data/raw/latest.xlsx
python scripts/02_clean.py          # data/raw/latest.xlsx -> data/cleaned/
pytest tests/ -v                    # validate cleaned data + artifacts (12 checks)
python scripts/03_eda.py            # charts + printed analysis -> assets/
python scripts/04_export_json.py    # dashboard JSON -> assets/data/
python scripts/05_notify.py         # email report (falls back to logs/report_*.txt)
```

Open `dashboard/index.html` in a browser (served over HTTP — browsers block
`fetch()` on `file://`) to view the dashboard locally, or visit the live
deployment below. To explore interactively, open
`notebooks/hghmnds_analysis.ipynb`.

**Note on CI**: `data/raw/*.xlsx` is git-ignored (raw scrape data stays local
except during the weekly Actions run, which scrapes fresh and commits the
resulting `data/cleaned/` itself). `deploy.yml` rebuilds charts/JSON from the
already-committed `data/cleaned/*.csv` on every push to `main` and redeploys
the dashboard — it does not rerun `02_clean.py`, since that needs the raw
file. `weekly_pipeline.yml` runs the full scrape-to-notify pipeline every
Sunday (and on manual trigger) and commits the refreshed cleaned data,
assets, and logs automatically.

## Live Dashboard

**https://hashtro9-rgb.github.io/HGHMNDSAnalysis/**

## Author

Gabriel Alegre Caña
