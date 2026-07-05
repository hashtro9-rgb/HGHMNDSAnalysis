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

## Key Findings

_TBD — filled in after EDA._

## Author

Gabriel Alegre Caña
