"""Pytest checks on the cleaned data (scripts/02_clean.py), the exported
dashboard JSON (scripts/04_export_json.py), the latest raw snapshot, and the
pipeline's own logging output."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = ROOT / "data" / "cleaned"
RAW_DIR = ROOT / "data" / "raw"
ASSETS_DIR = ROOT / "assets" / "data"
LOGS_DIR = ROOT / "logs"

# Current derive_category() rule set (scripts/02_clean.py) never returns
# "Other" -- unmatched abstractly-named products fall back to "T-Shirt".
ALLOWED_CATEGORIES = {
    "Longsleeves", "Tanktop", "Hoodie/Sweatshirt", "Jersey", "Headwear",
    "Bottoms", "Eyewear", "Accessories", "T-Shirt",
}

CSV_FILES = [
    "shopee_clean.csv", "lazada_clean.csv", "combined_clean.csv",
    "shopee_reviews_clean.csv", "lazada_reviews_clean.csv",
    "suspicious_listings.csv",
]

JSON_FILES = [
    "products.json", "reviews.json", "summary.json",
    "categories.json", "price_ranges.json", "weekly_diff.json",
]


@pytest.fixture(scope="module")
def combined():
    return pd.read_csv(CLEANED_DIR / "combined_clean.csv")


@pytest.fixture(scope="module")
def shopee_reviews():
    return pd.read_csv(CLEANED_DIR / "shopee_reviews_clean.csv")


@pytest.fixture(scope="module")
def lazada_reviews():
    return pd.read_csv(CLEANED_DIR / "lazada_reviews_clean.csv")


def test_cleaned_files_exist():
    for name in CSV_FILES:
        path = CLEANED_DIR / name
        assert path.exists(), f"missing {path}"


def test_no_nulls_in_critical_columns(combined):
    for col in ["product_name_clean", "price", "url", "platform", "category_derived"]:
        assert combined[col].isna().sum() == 0, f"{col} has nulls"


def test_discount_pct_is_numeric(combined):
    assert pd.api.types.is_numeric_dtype(combined["discount_pct"])
    assert not combined["discount_pct"].astype(str).str.contains("%").any()


def test_sold_final_no_negatives(combined):
    assert (combined["sold_final"] >= 0).all()


def test_is_authentic_is_boolean(combined):
    assert "is_authentic" in combined.columns
    assert combined["is_authentic"].dtype == bool


def test_category_derived_valid_values(combined):
    actual = set(combined["category_derived"].unique())
    assert actual <= ALLOWED_CATEGORIES, f"unexpected categories: {actual - ALLOWED_CATEGORIES}"


def test_review_dates_iso_format(shopee_reviews, lazada_reviews):
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for df, label in [(shopee_reviews, "Shopee"), (lazada_reviews, "Lazada")]:
        bad = df[~df["date"].astype(str).str.match(pattern)]
        assert bad.empty, f"{label} has non-ISO dates: {bad['date'].tolist()[:5]}"


def test_review_length_correct(shopee_reviews, lazada_reviews):
    for df, label in [(shopee_reviews, "Shopee"), (lazada_reviews, "Lazada")]:
        expected = df["review_text"].fillna("").astype(str).apply(len)
        assert (df["review_length"] == expected).all(), f"{label} review_length mismatch"


def test_json_files_exist():
    for name in JSON_FILES:
        path = ASSETS_DIR / name
        assert path.exists(), f"missing {path}"


def test_json_not_empty():
    for name in JSON_FILES:
        with open(ASSETS_DIR / name, encoding="utf-8") as f:
            data = json.load(f)
        assert data not in (None, [], {}), f"{name} is empty"


def test_latest_raw_exists():
    assert (RAW_DIR / "latest.xlsx").exists(), "data/raw/latest.xlsx not found -- run scripts/01_scrape.py"


def test_log_created():
    logs = list(LOGS_DIR.glob("pipeline_*.log"))
    assert logs, "no pipeline_*.log found in logs/ -- run scripts/run_pipeline.py"
