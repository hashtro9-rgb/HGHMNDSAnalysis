# HGHMNDS Clothing Market Analysis

## Project Overview

An end-to-end data pipeline analyzing HGHMNDS Clothing's market presence across
Shopee Philippines and Lazada Philippines. The pipeline scrapes product and
review data, cleans and flags it (including third-party knockoff listings),
runs exploratory data analysis, and exports the results as JSON for a
dashboard.

## Data Sources

- **Shopee Philippines** — product listings, pricing, ratings, and reviews for
  the HGHMNDS Clothing storefront and third-party sellers using the brand name.
- **Lazada Philippines** — same, scraped separately since the two platforms
  expose different fields (e.g. Shopee tracks 30-day sales, Lazada tracks
  lifetime sales).

Raw scrape output lives in `data/raw/` and is not committed to this repo (see
`.gitignore`) — it is the untouched source of truth for the cleaning pipeline.

## Folder Structure

```
HGHMNDSAnalysis/
├── .github/workflows/   CI: rerun pipeline + deploy assets/ to GitHub Pages
├── assets/              Charts (PNG) and exported JSON for the dashboard
├── data/
│   ├── raw/             Original scraped Excel (git-ignored, local only)
│   └── cleaned/         Cleaned CSVs/Excel produced by scripts/01_clean.py
├── docs/                Supplementary documentation
├── notebooks/           Jupyter notebook walkthrough of the analysis
├── scripts/
│   ├── 01_clean.py      Cleaning pipeline
│   ├── 02_eda.py        Exploratory data analysis + charts
│   └── 03_export_json.py Dashboard JSON export
└── tests/               pytest checks on the cleaned data
```

## How to Run

```bash
pip install -r requirements.txt

python scripts/01_clean.py        # data/raw/*.xlsx -> data/cleaned/
pytest tests/ -v                  # validate cleaned data
python scripts/02_eda.py          # charts + printed analysis -> assets/
python scripts/03_export_json.py  # dashboard JSON -> assets/data/
```

To explore interactively, open `notebooks/hghmnds_analysis.ipynb`.

**Note on CI**: `data/raw/*.xlsx` is git-ignored (raw scrape data stays local),
so `.github/workflows/deploy.yml` only runs `02_eda.py` and `03_export_json.py`
against the committed `data/cleaned/*.csv` — it does not rerun `01_clean.py`.
Whenever new raw data is scraped, run `01_clean.py` locally and commit the
refreshed `data/cleaned/` files so CI has something current to build from.

## Key Findings

- **Shopee lists at a premium but its sales-volume data is unusable.** Shopee's
  median price (PHP 620) beats Lazada's (PHP 500), and Shopee products carry far
  more reviews (1,431 vs 381) and a higher average rating (4.88 vs 4.40). However
  `sold_final` is 0 across every Shopee listing — confirmed to be a genuine
  platform limitation (Shopee's public search API no longer exposes real sold
  counts, even in successful responses where other fields like `rating_avg` and
  `review_count` are correctly populated and varied), not a scraping bug. Only
  Lazada's `sold_lifetime` figures are usable for sales-volume analysis this run;
  `review_count`/`rating_avg` stand in as the engagement proxy for Shopee.
- **Lazada carries far more knockoff risk.** ~41% of Lazada listings are flagged
  `is_suspicious` (discount > 80% or price under ₱250 — fake "original prices"
  like ₱7,777 discounted to ₱199), versus ~10% on Shopee.
- **"Other" is the largest category on both platforms** (53 Shopee, 49 Lazada)
  because many product names (e.g. "AURORA - HGHMNDS", "HGHMNDS - DIAGRAM") don't
  contain an explicit garment-type keyword — the classifier only matches literal
  keywords (shirt/tee/hoodie/etc.), so abstractly-named products fall through.
  Known limitation of this pipeline's simple keyword-based category rules.
- **`is_authentic` is true for virtually all 221 listings** since it only checks
  whether the product name mentions HGHMNDS/HIGHMINDS/HIGH MINDS — it doesn't by
  itself separate the official store from resellers or knockoffs (`is_suspicious`
  handles that).
- **Ratings barely correlate with review volume** (Pearson r ≈ 0.19–0.20 on both
  platforms) — popular items aren't systematically rated higher or lower than
  niche ones.
- **Reviews mix English and Filipino.** Word-frequency analysis on 1-star reviews
  is dominated by Filipino function words (ng, sa, na, mga) since the stopword
  list is English-only — negative reviews skew more Filipino-language than
  5-star reviews. A bilingual stopword list would sharpen this analysis further.

## Author

Gabriel Alegre Caña
