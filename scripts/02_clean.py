"""02_clean.py - data/raw/latest.xlsx -> data/cleaned/*.csv + hghmnds_cleaned.xlsx"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

RAW = ROOT / settings.RAW_DIR / "latest.xlsx"
CLEANED_DIR = ROOT / settings.CLEANED_DIR
CLEANED_DIR.mkdir(parents=True, exist_ok=True)

log_lines = []


def log(msg=""):
    print(msg)
    log_lines.append(msg)


CATEGORY_RULES = [
    (["LONGSLEEVE", "LONG SLEEVE"],           "Longsleeves"),
    (["TANKTOP", "TANK TOP"],                  "Tanktop"),
    (["HOODIE", "SWEATSHIRT", "PULLOVER"],     "Hoodie/Sweatshirt"),
    (["JERSEY"],                               "Jersey"),
    (["CAP", "HAT", "BUCKET"],                 "Headwear"),
    (["SHORTS", "PANTS", "TROUSERS"],          "Bottoms"),
    (["SHADES", "SUNGLASSES", "EYEWEAR"],      "Eyewear"),
    (["PURSE", "FANNY", "NECKLACE", "COIN", "BAG",
      "SOCKS", "STICKER"],                     "Accessories"),
    (["SHIRT", "TEE", "T-SHIRT", "TSHIRT"],    "T-Shirt"),
]


def derive_category(name):
    if not isinstance(name, str):
        return "Other"
    upper = name.upper()
    for keywords, cat in CATEGORY_RULES:
        if any(kw in upper for kw in keywords):
            return cat
    # Everything left is an abstractly-named product (AURORA, DIAGRAM, MANIFEST...)
    # with no explicit garment keyword. HGHMNDS is primarily a t-shirt brand, so
    # these are almost certainly tees rather than genuinely uncategorized items.
    return "T-Shirt"


def is_authentic(name):
    if not isinstance(name, str):
        return False
    upper = name.upper()
    return any(pat in upper for pat in settings.AUTHENTIC_KEYWORDS)


def clean_name(name):
    if not isinstance(name, str):
        return name
    name = name.strip()
    return re.sub(r" {2,}", " ", name)


LAZADA_SCRAPE_DATE = datetime.now()
RELATIVE_UNITS = {"day": "days", "days": "days", "week": "weeks", "weeks": "weeks"}


def parse_lazada_date(d):
    if not isinstance(d, str):
        return d
    d = d.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d

    low = d.lower()
    if low == "today":
        return LAZADA_SCRAPE_DATE.strftime("%Y-%m-%d")
    if low == "yesterday":
        return (LAZADA_SCRAPE_DATE - timedelta(days=1)).strftime("%Y-%m-%d")

    m = re.match(r"^(\d+)\s+(day|days|week|weeks|month|months|year|years|hour|hours)\s+ago$", low)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ("month", "months"):
            delta = timedelta(days=n * 30)
        elif unit in ("year", "years"):
            delta = timedelta(days=n * 365)
        elif unit in ("hour", "hours"):
            delta = timedelta(days=0)
        else:
            delta = timedelta(**{RELATIVE_UNITS[unit]: n})
        return (LAZADA_SCRAPE_DATE - delta).strftime("%Y-%m-%d")

    try:
        return pd.to_datetime(d, format="%d %b %Y").strftime("%Y-%m-%d")
    except Exception:
        return d


def clean_review_text(text):
    if not isinstance(text, str):
        return text
    text = text.strip()
    return re.sub(r"\n{2,}", "\n", text)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
if not RAW.exists():
    print(f"[!] {RAW} not found. Run scripts/01_scrape.py first (or place a "
          f"raw xlsx at data/raw/latest.xlsx).")
    sys.exit(1)

log(f"Loading {RAW.name}...")
sp_raw = pd.read_excel(RAW, sheet_name="Shopee_Products")
lp_raw = pd.read_excel(RAW, sheet_name="Lazada_Products")
sr_raw = pd.read_excel(RAW, sheet_name="Shopee_Reviews")
lr_raw = pd.read_excel(RAW, sheet_name="Lazada_Reviews")

before_counts = {
    "Shopee_Products": len(sp_raw), "Lazada_Products": len(lp_raw),
    "Shopee_Reviews": len(sr_raw), "Lazada_Reviews": len(lr_raw),
}
log(f"  Shopee_Products : {len(sp_raw)} rows, {len(sp_raw.columns)} cols")
log(f"  Lazada_Products : {len(lp_raw)} rows, {len(lp_raw.columns)} cols")
log(f"  Shopee_Reviews  : {len(sr_raw)} rows")
log(f"  Lazada_Reviews  : {len(lr_raw)} rows")
log()

# ---------------------------------------------------------------------------
# Shopee_Products
# ---------------------------------------------------------------------------
log("=== Cleaning Shopee_Products ===")
sp = sp_raw.copy()


def parse_pct_text(val):
    if pd.isna(val) or str(val).strip() in ("", "nan"):
        return 0.0
    return float(str(val).replace("%", "").strip())


sp["discount_pct"] = sp["discount_pct"].apply(parse_pct_text)
log("  discount_pct : text '15%' -> float 15.0, nulls -> 0")

sp["sold_final"] = pd.to_numeric(sp["sold_30d"], errors="coerce").fillna(0).astype(int)
sp["sold_source"] = "sold_30d"
log("  sold_final   : copied from sold_30d, nulls -> 0")

sp["review_count"] = pd.to_numeric(sp["review_count"], errors="coerce").fillna(0).astype(int)
sp["has_ratings"] = sp["review_count"] > 0
sp.loc[sp["review_count"] == 0, "rating_avg"] = np.nan
log(f"  rating_avg   : NaN where review_count == 0 "
    f"({int((~sp['has_ratings']).sum())} rows)")

drop_cols = ["stock", "description", "variations"]
sp = sp.drop(columns=drop_cols)
log(f"  Dropped 100%-null columns : {drop_cols}")

sp["product_name_clean"] = sp["product_name"].apply(clean_name)
sp["is_authentic"] = sp["product_name_clean"].apply(is_authentic)
sp["category_derived"] = sp["product_name_clean"].apply(derive_category)

sp_price = pd.to_numeric(sp["price"], errors="coerce")
sp_disc = pd.to_numeric(sp["discount_pct"], errors="coerce").fillna(0)
sp["is_suspicious"] = (sp_disc > settings.SUSPICIOUS_DISCOUNT_THRESHOLD) | \
                      (sp_price < settings.SUSPICIOUS_PRICE_FLOOR)

log(f"  is_authentic : {int(sp['is_authentic'].sum())} True / {len(sp)}")
log(f"  is_suspicious: {int(sp['is_suspicious'].sum())} True / {len(sp)}")
log(f"  category_derived : {sp['category_derived'].value_counts().to_dict()}")
log(f"  Final Shopee_Products : {len(sp)} rows, {len(sp.columns)} cols")
log()

# ---------------------------------------------------------------------------
# Lazada_Products
# ---------------------------------------------------------------------------
log("=== Cleaning Lazada_Products ===")
lp = lp_raw.copy()

lp["sold_final"] = pd.to_numeric(lp["sold_lifetime"], errors="coerce").fillna(0).astype(int)
lp["sold_source"] = "sold_lifetime"
log("  sold_final   : copied from sold_lifetime, nulls -> 0")

lp_price = pd.to_numeric(lp["price"], errors="coerce")
lp_disc = pd.to_numeric(lp["discount_pct"], errors="coerce").fillna(0)
lp["is_suspicious"] = (lp_disc > settings.SUSPICIOUS_DISCOUNT_THRESHOLD) | \
                      (lp_price < settings.SUSPICIOUS_PRICE_FLOOR)
log(f"  is_suspicious: {int(lp['is_suspicious'].sum())} True / {len(lp)} "
    f"(discount_pct>{settings.SUSPICIOUS_DISCOUNT_THRESHOLD} OR "
    f"price<{settings.SUSPICIOUS_PRICE_FLOOR})")

lp["review_count"] = pd.to_numeric(lp["review_count"], errors="coerce")
lp["has_ratings"] = lp["review_count"].fillna(0) > 0
lp.loc[lp["review_count"].isna() | (lp["review_count"] == 0), "rating_avg"] = np.nan
lp["review_count"] = lp["review_count"].fillna(0).astype(int)
log(f"  rating_avg   : NaN where review_count == 0 or null "
    f"({int((~lp['has_ratings']).sum())} rows)")

lp["product_name_clean"] = lp["product_name"].apply(clean_name)
lp["is_authentic"] = lp["product_name_clean"].apply(is_authentic)
lp["category_derived"] = lp["product_name_clean"].apply(derive_category)

log(f"  is_authentic : {int(lp['is_authentic'].sum())} True / {len(lp)}")
log(f"  category_derived : {lp['category_derived'].value_counts().to_dict()}")
log(f"  Final Lazada_Products : {len(lp)} rows, {len(lp.columns)} cols")
log()

# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
log("=== Cleaning Reviews ===")


def clean_reviews(df, platform):
    df = df.copy()
    df["review_text"] = df["review_text"].apply(clean_review_text)
    if platform == "Lazada":
        df["date"] = df["date"].apply(parse_lazada_date)
    df["review_length"] = df["review_text"].fillna("").astype(str).apply(len)
    df["is_substantive"] = df["review_length"] >= settings.MIN_REVIEW_LENGTH
    log(f"  {platform} : {len(df)} rows, "
        f"{int(df['is_substantive'].sum())} substantive "
        f"(>={settings.MIN_REVIEW_LENGTH} chars)")
    return df


sr = clean_reviews(sr_raw, "Shopee")
lr = clean_reviews(lr_raw, "Lazada")
log()

# ---------------------------------------------------------------------------
# Combined_Clean
# ---------------------------------------------------------------------------
COMBINED_COLS = [
    "platform", "item_id", "product_name_clean", "category_derived",
    "price", "original_price", "discount_pct", "sold_final", "sold_source",
    "rating_avg", "review_count", "has_ratings", "is_suspicious",
    "is_authentic", "seller_name", "url", "image_url",
]
combined = pd.concat([sp[COMBINED_COLS], lp[COMBINED_COLS]], ignore_index=True)

suspicious = combined[combined["is_suspicious"]].copy()

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------
sp.to_csv(CLEANED_DIR / "shopee_clean.csv", index=False, encoding="utf-8-sig")
lp.to_csv(CLEANED_DIR / "lazada_clean.csv", index=False, encoding="utf-8-sig")
combined.to_csv(CLEANED_DIR / "combined_clean.csv", index=False, encoding="utf-8-sig")
sr.to_csv(CLEANED_DIR / "shopee_reviews_clean.csv", index=False, encoding="utf-8-sig")
lr.to_csv(CLEANED_DIR / "lazada_reviews_clean.csv", index=False, encoding="utf-8-sig")
suspicious.to_csv(CLEANED_DIR / "suspicious_listings.csv", index=False, encoding="utf-8-sig")

cleaning_log_df = pd.DataFrame({"Cleaning Log": log_lines})
with pd.ExcelWriter(CLEANED_DIR / "hghmnds_cleaned.xlsx", engine="openpyxl") as w:
    sp.to_excel(w, sheet_name="Shopee_Clean", index=False)
    lp.to_excel(w, sheet_name="Lazada_Clean", index=False)
    combined.to_excel(w, sheet_name="Combined_Clean", index=False)
    sr.to_excel(w, sheet_name="Shopee_Reviews", index=False)
    lr.to_excel(w, sheet_name="Lazada_Reviews", index=False)
    suspicious.to_excel(w, sheet_name="Suspicious_Listings", index=False)
    cleaning_log_df.to_excel(w, sheet_name="Cleaning_Log", index=False)

# ---------------------------------------------------------------------------
# Cleaning summary
# ---------------------------------------------------------------------------
print()
print("=" * 65)
print("CLEANING SUMMARY")
print("=" * 65)
print(f"  Shopee_Products : {before_counts['Shopee_Products']} -> {len(sp)} rows  "
      f"({len(sp_raw.columns)} -> {len(sp.columns)} cols, dropped {drop_cols})")
print(f"  Lazada_Products : {before_counts['Lazada_Products']} -> {len(lp)} rows  "
      f"({len(lp_raw.columns)} -> {len(lp.columns)} cols, 0 dropped)")
print(f"  Shopee_Reviews  : {before_counts['Shopee_Reviews']} -> {len(sr)} rows")
print(f"  Lazada_Reviews  : {before_counts['Lazada_Reviews']} -> {len(lr)} rows")
print(f"  Combined_Clean  : {len(combined)} rows ({len(sp)} Shopee + {len(lp)} Lazada)")
print()
print(f"  Suspicious listings : {len(suspicious)} total "
      f"(Shopee {int((suspicious['platform']=='Shopee').sum())}, "
      f"Lazada {int((suspicious['platform']=='Lazada').sum())})")
print(f"  Authentic products  : Shopee {int(sp['is_authentic'].sum())}/{len(sp)}, "
      f"Lazada {int(lp['is_authentic'].sum())}/{len(lp)}")
print()
print(f"  Output dir : {CLEANED_DIR}")
print("  Files: shopee_clean.csv, lazada_clean.csv, combined_clean.csv, "
      "shopee_reviews_clean.csv, lazada_reviews_clean.csv, "
      "suspicious_listings.csv, hghmnds_cleaned.xlsx")
