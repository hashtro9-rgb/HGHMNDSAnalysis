# HGHMNDS Market Intelligence Dashboard

## Overview

An end-to-end, automated pipeline that scrapes HGHMNDS Clothing's market
presence across Shopee Philippines and Lazada Philippines, cleans and flags
the data (including third-party knockoff listings), runs exploratory
analysis, and serves the results as a live dashboard. A weekly GitHub Actions
run rescrapes, diffs against the previous week, rebuilds the dashboard data,
and emails a summary report — no manual intervention required.

**Notable data caveat**: Shopee's public search API no longer exposes real
"sold" counts (confirmed platform-side limitation, not a scraping bug), so
`review_count`/`rating_avg` stand in as the Shopee engagement proxy wherever
sales volume would otherwise be shown.

## Data Sources

- **Shopee Philippines** — product listings, pricing, ratings, and reviews for
  the HGHMNDS Clothing storefront and third-party sellers using the brand name,
  via Shopee's internal JSON search/detail/review APIs.
- **Lazada Philippines** — same, via headless Playwright browsing (search
  cards + per-product detail pages), since Lazada exposes different fields
  (e.g. lifetime sold count vs Shopee's 30-day figure) and no public JSON API
  for search.

Raw scrape output lives in `data/raw/` and is not committed to this repo (see
`.gitignore`) — it is the untouched source of truth for the cleaning pipeline.

## Structure

```
HGHMNDSAnalysis/
├── .github/workflows/
│   ├── deploy.yml            CI: rebuild assets/ from committed cleaned data, deploy to Pages
│   └── weekly_pipeline.yml   Sunday cron: full scrape -> clean -> EDA -> export -> notify -> deploy
├── assets/
│   └── data/                 JSON exports consumed by the dashboard
├── config/
│   └── settings.py           Keywords, thresholds, paths, notification config
├── data/
│   ├── raw/                  Latest + timestamped raw scrapes (git-ignored)
│   ├── cleaned/              Cleaned CSVs/Excel (committed, CI builds from these)
│   └── archive/              Weekly snapshots of data/cleaned/, pruned to KEEP_WEEKS
├── dashboard/
│   ├── index.html            Dashboard shell (6 tabs)
│   ├── style.css             Design system (dark, editorial streetwear aesthetic)
│   └── script.js             Data loading, charts, filtering, interactions
├── docs/                     Supplementary documentation
├── logs/                     Pipeline run logs + fallback notification reports
├── notebooks/                Jupyter walkthrough of the analysis
├── scripts/
│   ├── 01_scrape.py          Headless scrape (Shopee API + Lazada Playwright) + weekly diff
│   ├── 02_clean.py           Cleaning pipeline
│   ├── 03_eda.py             Exploratory data analysis + charts
│   ├── 04_export_json.py     Dashboard JSON export
│   ├── 05_notify.py          Email summary report (Gmail SMTP)
│   └── run_pipeline.py       Runs 01-05 in sequence, logs, archives, never crashes silently
└── tests/                    pytest checks on cleaned data + pipeline artifacts
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
pytest tests/ -v                    # validate cleaned data + artifacts
python scripts/03_eda.py            # charts + printed analysis -> assets/
python scripts/04_export_json.py    # dashboard JSON -> assets/data/
python scripts/05_notify.py         # email report (falls back to logs/report_*.txt)
```

Open `dashboard/index.html` in a browser to view the dashboard locally, or
visit the live deployment below. To explore interactively, open
`notebooks/hghmnds_analysis.ipynb`.

**Note on CI**: `data/raw/*.xlsx` is git-ignored (raw scrape data stays local
outside of the weekly Actions run, which scrapes fresh and commits the
resulting `data/cleaned/` itself). `deploy.yml` only rebuilds `assets/` from
the already-committed `data/cleaned/*.csv` on every push to `main`.
`weekly_pipeline.yml` runs the full scrape-to-notify pipeline every Sunday and
commits the refreshed cleaned data, assets, and logs automatically.

## Live Dashboard

**https://hashtro9-rgb.github.io/HGHMNDSAnalysis/**

## Author

Gabriel Alegre Caña
