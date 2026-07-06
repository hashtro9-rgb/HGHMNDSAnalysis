"""04_export_json.py - export cleaned data as JSON for the dashboard -> assets/data/*.json"""
import glob
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

CLEANED_DIR = ROOT / settings.CLEANED_DIR
RAW_DIR = ROOT / settings.RAW_DIR
JSON_DIR = ROOT / settings.ASSETS_DIR
JSON_DIR.mkdir(parents=True, exist_ok=True)


def round_floats(records):
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and not pd.isna(v):
                row[k] = round(v, 2)
            elif isinstance(v, float) and pd.isna(v):
                row[k] = None
    return records


combined = pd.read_csv(CLEANED_DIR / "combined_clean.csv")
shopee_reviews = pd.read_csv(CLEANED_DIR / "shopee_reviews_clean.csv")
lazada_reviews = pd.read_csv(CLEANED_DIR / "lazada_reviews_clean.csv")

# ---------------------------------------------------------------------------
# products.json
# ---------------------------------------------------------------------------
clean_products = combined[combined["is_authentic"] & ~combined["is_suspicious"]].copy()
product_cols = [
    "platform", "item_id", "product_name_clean", "category_derived", "price",
    "original_price", "discount_pct", "sold_final", "sold_source", "rating_avg",
    "review_count", "has_ratings", "url", "image_url",
]
products_records = round_floats(clean_products[product_cols].to_dict(orient="records"))
with open(JSON_DIR / "products.json", "w", encoding="utf-8") as f:
    json.dump(products_records, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# reviews.json
# ---------------------------------------------------------------------------
all_reviews = pd.concat([
    shopee_reviews.assign(platform="Shopee"),
    lazada_reviews.assign(platform="Lazada"),
], ignore_index=True)
substantive = all_reviews[all_reviews["is_substantive"]].copy()
review_cols = ["platform", "item_id", "product_name", "rating", "review_text",
               "buyer_name", "date", "review_length"]
reviews_records = round_floats(substantive[review_cols].to_dict(orient="records"))
with open(JSON_DIR / "reviews.json", "w", encoding="utf-8") as f:
    json.dump(reviews_records, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# summary.json
# ---------------------------------------------------------------------------
authentic = combined[combined["is_authentic"]]
shopee_a = authentic[authentic["platform"] == "Shopee"]
lazada_a = authentic[authentic["platform"] == "Lazada"]

top_category = authentic["category_derived"].value_counts().idxmax()

top_seller_shopee = (shopee_a.sort_values("sold_final", ascending=False)
                     .iloc[0]["product_name_clean"] if len(shopee_a) else None)
top_seller_lazada = (lazada_a.sort_values("sold_final", ascending=False)
                     .iloc[0]["product_name_clean"] if len(lazada_a) else None)

# scraped_at: pull from the Shopee_Products scraped_at column in the latest
# raw file if available, else fall back to today's date.
scraped_at = None
latest_raw = RAW_DIR / "latest.xlsx"
if latest_raw.exists():
    try:
        raw_sp = pd.read_excel(latest_raw, sheet_name="Shopee_Products")
        stamp = str(raw_sp["scraped_at"].dropna().iloc[0])
        scraped_at = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else stamp
    except Exception:
        pass
if not scraped_at:
    from datetime import datetime
    scraped_at = datetime.now().strftime("%Y-%m-%d")

summary = {
    "total_products": int(len(authentic)),
    "shopee_count": int(len(shopee_a)),
    "lazada_count": int(len(lazada_a)),
    "avg_price_shopee": round(float(shopee_a["price"].mean()), 2),
    "avg_price_lazada": round(float(lazada_a["price"].mean()), 2),
    "total_reviews": int(len(shopee_reviews) + len(lazada_reviews)),
    "avg_rating_shopee": round(float(shopee_a.loc[shopee_a["has_ratings"], "rating_avg"].mean()), 2),
    "avg_rating_lazada": round(float(lazada_a.loc[lazada_a["has_ratings"], "rating_avg"].mean()), 2),
    "total_sold": int(authentic["sold_final"].sum()),
    "top_category": top_category,
    "top_seller_shopee": top_seller_shopee,
    "top_seller_lazada": top_seller_lazada,
    "suspicious_count": int(combined["is_suspicious"].sum()),
    "scraped_at": scraped_at,
}
with open(JSON_DIR / "summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# categories.json
# ---------------------------------------------------------------------------
cat_group = authentic.groupby("category_derived").agg(
    count=("item_id", "count"),
    avg_price=("price", "mean"),
    avg_rating=("rating_avg", "mean"),
    total_sold=("sold_final", "sum"),
).reset_index().rename(columns={"category_derived": "category"})
cat_group["count"] = cat_group["count"].astype(int)
cat_group["total_sold"] = cat_group["total_sold"].astype(int)
categories_records = round_floats(cat_group.to_dict(orient="records"))
with open(JSON_DIR / "categories.json", "w", encoding="utf-8") as f:
    json.dump(categories_records, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# price_ranges.json
# ---------------------------------------------------------------------------
bins = [0, 300, 500, 800, 1200, float("inf")]
labels = ["Under ₱300", "₱300–₱500", "₱500–₱800", "₱800–₱1200", "Above ₱1200"]
authentic = authentic.copy()
authentic["price_range"] = pd.cut(authentic["price"], bins=bins, labels=labels, right=False)
range_counts = authentic["price_range"].value_counts().reindex(labels, fill_value=0)
price_ranges_records = [{"range": r, "count": int(c)} for r, c in range_counts.items()]
with open(JSON_DIR / "price_ranges.json", "w", encoding="utf-8") as f:
    json.dump(price_ranges_records, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# weekly_diff.json -- copy of the latest diff from data/raw/
# ---------------------------------------------------------------------------
diff_candidates = sorted(glob.glob(str(RAW_DIR / "weekly_diff_*.json")))
if diff_candidates:
    shutil.copy(diff_candidates[-1], JSON_DIR / "weekly_diff.json")
else:
    with open(JSON_DIR / "weekly_diff.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": None, "previous_file": None,
            "new_products": [], "disappeared_products": [],
            "price_changes": [], "rating_changes": [],
            "note": "No weekly_diff_*.json found in data/raw/ yet -- "
                    "run scripts/01_scrape.py to generate one.",
        }, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Report file sizes
# ---------------------------------------------------------------------------
print("Exported JSON files:")
for name in ["products.json", "reviews.json", "summary.json", "categories.json",
             "price_ranges.json", "weekly_diff.json"]:
    path = JSON_DIR / name
    print(f"  {name:20s} {path.stat().st_size:>8,d} bytes")
