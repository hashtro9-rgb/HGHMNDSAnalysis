"""Pytest checks on the cleaned data produced by scripts/01_clean.py."""
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = ROOT / "data" / "cleaned"

ALLOWED_CATEGORIES = {
    "Longsleeves", "Tanktop", "Hoodie/Sweatshirt", "Jersey",
    "Headwear", "Accessories", "T-Shirt", "Other",
}

CSV_FILES = [
    "shopee_clean.csv", "lazada_clean.csv", "combined_clean.csv",
    "shopee_reviews_clean.csv", "lazada_reviews_clean.csv",
    "suspicious_listings.csv",
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


def test_cleaned_csvs_exist():
    for name in CSV_FILES:
        path = CLEANED_DIR / name
        assert path.exists(), f"missing {path}"


def test_no_nulls_in_critical_columns(combined):
    for col in ["product_name_clean", "price", "url", "platform", "category_derived"]:
        assert combined[col].isna().sum() == 0, f"{col} has nulls"


def test_discount_pct_is_numeric(combined):
    assert pd.api.types.is_float_dtype(combined["discount_pct"]) or \
        pd.api.types.is_numeric_dtype(combined["discount_pct"])


def test_sold_final_no_negatives(combined):
    assert (combined["sold_final"] >= 0).all()


def test_is_authentic_exists_and_boolean(combined):
    assert "is_authentic" in combined.columns
    assert combined["is_authentic"].dtype == bool


def test_category_derived_allowed_values(combined):
    assert set(combined["category_derived"].unique()) <= ALLOWED_CATEGORIES


def test_review_dates_iso_format(shopee_reviews, lazada_reviews):
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for df, label in [(shopee_reviews, "Shopee"), (lazada_reviews, "Lazada")]:
        bad = df[~df["date"].astype(str).str.match(pattern)]
        assert bad.empty, f"{label} has non-ISO dates: {bad['date'].tolist()[:5]}"


def test_review_length_matches_text(shopee_reviews, lazada_reviews):
    for df, label in [(shopee_reviews, "Shopee"), (lazada_reviews, "Lazada")]:
        expected = df["review_text"].fillna("").astype(str).apply(len)
        assert (df["review_length"] == expected).all(), f"{label} review_length mismatch"
