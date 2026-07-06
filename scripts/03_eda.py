"""03_eda.py - exploratory data analysis on data/cleaned/*.csv -> charts in assets/, tables printed."""
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

CLEANED_DIR = ROOT / settings.CLEANED_DIR
ASSETS_DIR = ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

plt.style.use("seaborn-v0_8-darkgrid")
PALETTE = {"Shopee": "#ee4d2d", "Lazada": "#0f156d"}

STOPWORDS = {"the", "a", "is", "it", "and", "in", "of", "to", "i", "my", "for",
             "was", "so", "very", "this", "that", "are", "with", "on"}

summary = {}

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
combined = pd.read_csv(CLEANED_DIR / "combined_clean.csv")
shopee = pd.read_csv(CLEANED_DIR / "shopee_clean.csv")
lazada = pd.read_csv(CLEANED_DIR / "lazada_clean.csv")
shopee_reviews = pd.read_csv(CLEANED_DIR / "shopee_reviews_clean.csv")
lazada_reviews = pd.read_csv(CLEANED_DIR / "lazada_reviews_clean.csv")

print(f"Loaded: combined={len(combined)}, shopee={len(shopee)}, lazada={len(lazada)}, "
      f"shopee_reviews={len(shopee_reviews)}, lazada_reviews={len(lazada_reviews)}")

# =============================================================================
# PRICING
# =============================================================================
print("\n" + "=" * 70)
print("PRICING")
print("=" * 70)

price_stats = combined.groupby("platform")["price"].agg(
    mean="mean", median="median", min="min", max="max").round(2)
print("\n-- Price stats per platform --")
print(price_stats.to_string())
summary["price_stats"] = price_stats.to_dict("index")

fig, ax = plt.subplots(figsize=(9, 5))
for plat in ["Shopee", "Lazada"]:
    data = combined.loc[combined["platform"] == plat, "price"]
    ax.hist(data, bins=25, alpha=0.55, label=plat, color=PALETTE[plat])
ax.set_xlabel("Price (PHP)")
ax.set_ylabel("Count")
ax.set_title("Price Distribution: Shopee vs Lazada")
ax.legend()
fig.tight_layout()
fig.savefig(ASSETS_DIR / "price_distribution.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'price_distribution.png'}")

fig, ax = plt.subplots(figsize=(11, 6))
order = combined.groupby("category_derived")["price"].median().sort_values().index
sns.boxplot(data=combined, x="category_derived", y="price", hue="platform",
            order=order, palette=PALETTE, ax=ax)
ax.set_xlabel("Category")
ax.set_ylabel("Price (PHP)")
ax.set_title("Price by Category")
plt.xticks(rotation=30, ha="right")
fig.tight_layout()
fig.savefig(ASSETS_DIR / "price_by_category.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'price_by_category.png'}")

clean_mask = combined["is_authentic"] & ~combined["is_suspicious"]
avg_discount = (combined.loc[clean_mask].assign(discount_pct=lambda d: d["discount_pct"].fillna(0))
                .groupby("platform")["discount_pct"].mean().round(2))
print("\n-- Avg discount % per platform (authentic + non-suspicious only) --")
print(avg_discount.to_string())
summary["avg_discount_clean"] = avg_discount.to_dict()

# =============================================================================
# SALES
# =============================================================================
print("\n" + "=" * 70)
print("SALES")
print("=" * 70)

authentic = combined[combined["is_authentic"]]
top15 = authentic.sort_values("sold_final", ascending=False).head(15)[
    ["platform", "product_name_clean", "category_derived", "price", "sold_final"]]
print("\n-- Top 15 bestsellers (authentic, by sold_final) --")
print(top15.to_string(index=False))

total_sold = combined.groupby("platform")["sold_final"].sum()
print("\n-- Total sold_final per platform --")
print(total_sold.to_string())
summary["total_sold"] = total_sold.to_dict()

fig, ax = plt.subplots(figsize=(11, 6))
sales_by_cat = (combined.groupby(["category_derived", "platform"])["sold_final"]
                .sum().unstack(fill_value=0))
sales_by_cat = sales_by_cat.loc[sales_by_cat.sum(axis=1).sort_values(ascending=False).index]
sales_by_cat.plot(kind="bar", ax=ax, color=[PALETTE.get(c, "gray") for c in sales_by_cat.columns])
ax.set_xlabel("Category")
ax.set_ylabel("Total units sold (sold_final)")
ax.set_title("Sales by Category")
plt.xticks(rotation=30, ha="right")
fig.tight_layout()
fig.savefig(ASSETS_DIR / "sales_by_category.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'sales_by_category.png'}")

fig, ax = plt.subplots(figsize=(9, 6))
for plat in ["Shopee", "Lazada"]:
    d = combined[combined["platform"] == plat]
    ax.scatter(d["price"], d["sold_final"], alpha=0.6, label=plat, color=PALETTE[plat])
ax.set_xlabel("Price (PHP)")
ax.set_ylabel("Units sold (sold_final)")
ax.set_title("Price vs Sales")
ax.legend()
fig.tight_layout()
fig.savefig(ASSETS_DIR / "price_vs_sales.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'price_vs_sales.png'}")

# =============================================================================
# RATINGS
# =============================================================================
print("\n" + "=" * 70)
print("RATINGS")
print("=" * 70)

rated = combined[combined["has_ratings"]]
avg_rating = rated.groupby("platform")["rating_avg"].mean().round(3)
print("\n-- Avg rating_avg per platform (has_ratings only) --")
print(avg_rating.to_string())
summary["avg_rating"] = avg_rating.to_dict()

bins = [1, 2, 3, 4, 5]
labels = ["1-2", "2-3", "3-4", "4-5"]
rated_copy = rated.copy()
rated_copy["rating_bucket"] = pd.cut(rated_copy["rating_avg"], bins=bins, labels=labels,
                                      include_lowest=True)
bucket_counts = (rated_copy.groupby(["rating_bucket", "platform"], observed=True).size()
                 .unstack(fill_value=0).reindex(labels))
print("\n-- Product count per rating bucket --")
print(bucket_counts.to_string())

fig, ax = plt.subplots(figsize=(8, 5))
bucket_counts.plot(kind="bar", ax=ax, color=[PALETTE.get(c, "gray") for c in bucket_counts.columns])
ax.set_xlabel("Rating bucket")
ax.set_ylabel("Product count")
ax.set_title("Rating Distribution (products)")
plt.xticks(rotation=0)
fig.tight_layout()
fig.savefig(ASSETS_DIR / "rating_distribution.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'rating_distribution.png'}")

top_rated = (combined[combined["review_count"] >= 10]
             .sort_values("rating_avg", ascending=False).head(10)
             [["platform", "product_name_clean", "rating_avg", "review_count"]])
print("\n-- Top 10 highest-rated products (>=10 reviews) --")
print(top_rated.to_string(index=False))

print("\n-- Pearson r: rating_avg vs review_count, per platform --")
corr_results = {}
for plat in ["Shopee", "Lazada"]:
    d = rated[rated["platform"] == plat]
    r = d["rating_avg"].corr(d["review_count"])
    corr_results[plat] = round(r, 4)
    print(f"  {plat}: r = {r:.4f}")
summary["rating_review_corr"] = corr_results

# =============================================================================
# REVIEWS
# =============================================================================
print("\n" + "=" * 70)
print("REVIEWS")
print("=" * 70)

review_counts = {"Shopee": len(shopee_reviews), "Lazada": len(lazada_reviews)}
print("\n-- Total review count per platform --")
for k, v in review_counts.items():
    print(f"  {k}: {v}")
summary["review_counts"] = review_counts

avg_len = {
    "Shopee": round(shopee_reviews.loc[shopee_reviews["is_substantive"], "review_length"].mean(), 2),
    "Lazada": round(lazada_reviews.loc[lazada_reviews["is_substantive"], "review_length"].mean(), 2),
}
print("\n-- Avg review_length per platform (substantive only) --")
for k, v in avg_len.items():
    print(f"  {k}: {v}")
summary["avg_review_length"] = avg_len

all_reviews = pd.concat([
    shopee_reviews.assign(platform="Shopee"),
    lazada_reviews.assign(platform="Lazada"),
], ignore_index=True)

star_counts = (all_reviews.groupby(["rating", "platform"]).size()
               .unstack(fill_value=0).reindex(range(1, 6), fill_value=0))
print("\n-- Review rating distribution (1-5 stars) --")
print(star_counts.to_string())

fig, ax = plt.subplots(figsize=(8, 5))
star_counts.plot(kind="bar", ax=ax, color=[PALETTE.get(c, "gray") for c in star_counts.columns])
ax.set_xlabel("Star rating")
ax.set_ylabel("Review count")
ax.set_title("Review Star Distribution")
plt.xticks(rotation=0)
fig.tight_layout()
fig.savefig(ASSETS_DIR / "review_stars.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'review_stars.png'}")


def word_freq(texts, top_n=20):
    counter = Counter()
    for t in texts.dropna().astype(str):
        words = re.findall(r"[a-zA-Z']+", t.lower())
        for w in words:
            if w not in STOPWORDS and len(w) > 1:
                counter[w] += 1
    return counter.most_common(top_n)


five_star_words = word_freq(all_reviews.loc[all_reviews["rating"] == 5, "review_text"])
one_star_words = word_freq(all_reviews.loc[all_reviews["rating"] == 1, "review_text"])

word_table = pd.DataFrame({
    "5-star word": [w for w, _ in five_star_words] + [""] * (20 - len(five_star_words)),
    "5-star count": [c for _, c in five_star_words] + [""] * (20 - len(five_star_words)),
    "1-star word": [w for w, _ in one_star_words] + [""] * (20 - len(one_star_words)),
    "1-star count": [c for _, c in one_star_words] + [""] * (20 - len(one_star_words)),
})
print("\n-- Top 20 words: 5-star vs 1-star reviews --")
print(word_table.to_string(index=False))

# =============================================================================
# CROSS-PLATFORM COMPARISON
# =============================================================================
print("\n" + "=" * 70)
print("CROSS-PLATFORM COMPARISON")
print("=" * 70)

metrics = {
    "Avg Price (PHP)": price_stats["mean"].to_dict(),
    "Avg Rating": avg_rating.to_dict(),
    "Total Sold": total_sold.to_dict(),
    "Total Reviews": review_counts,
}
fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
for ax, (metric_name, vals) in zip(axes, metrics.items()):
    plats = ["Shopee", "Lazada"]
    heights = [vals.get(p, 0) for p in plats]
    ax.bar(plats, heights, color=[PALETTE[p] for p in plats])
    ax.set_title(metric_name)
fig.suptitle("Platform Comparison")
fig.tight_layout()
fig.savefig(ASSETS_DIR / "platform_comparison.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'platform_comparison.png'}")

cat_share = (combined.groupby(["platform", "category_derived"]).size()
             .groupby(level=0).apply(lambda s: (s / s.sum() * 100).round(2))
             .unstack(fill_value=0))
print("\n-- Category share per platform (%) --")
print(cat_share.to_string())

fig, ax = plt.subplots(figsize=(9, 6))
cat_share.T.plot(kind="bar", stacked=True, ax=ax, color=[PALETTE.get(c, "gray") for c in cat_share.index])
ax.set_xlabel("Category")
ax.set_ylabel("% of listings")
ax.set_title("Category Share per Platform")
plt.xticks(rotation=30, ha="right")
fig.tight_layout()
fig.savefig(ASSETS_DIR / "category_share.png", dpi=150)
plt.close(fig)
print(f"Saved {ASSETS_DIR / 'category_share.png'}")

# =============================================================================
# SUSPICIOUS LISTINGS
# =============================================================================
print("\n" + "=" * 70)
print("SUSPICIOUS LISTINGS")
print("=" * 70)

suspicious = pd.read_csv(CLEANED_DIR / "suspicious_listings.csv")
susp_by_plat = suspicious["platform"].value_counts()
total_by_plat = combined["platform"].value_counts()
susp_pct = (susp_by_plat / total_by_plat * 100).round(2)

print(f"\nTotal suspicious: {len(suspicious)} / {len(combined)} "
      f"({len(suspicious) / len(combined) * 100:.2f}%)")
for plat in ["Shopee", "Lazada"]:
    n = int(susp_by_plat.get(plat, 0))
    pct = susp_pct.get(plat, 0.0)
    print(f"  {plat}: {n} suspicious / {total_by_plat.get(plat, 0)} total ({pct}%)")

avg_fake_discount = suspicious["discount_pct"].mean()
print(f"\nAverage discount % among suspicious listings: {avg_fake_discount:.2f}%")

top5_suspicious = suspicious.sort_values("discount_pct", ascending=False).head(5)[
    ["platform", "product_name_clean", "price", "original_price", "discount_pct"]]
print("\n-- Top 5 most suspicious (highest discount %) --")
print(top5_suspicious.to_string(index=False))

summary["suspicious"] = {
    "total": len(suspicious),
    "by_platform": susp_by_plat.to_dict(),
    "pct_by_platform": susp_pct.to_dict(),
    "avg_fake_discount": round(avg_fake_discount, 2),
}

# =============================================================================
# FULL EDA SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("FULL EDA SUMMARY")
print("=" * 70)
print(f"""
Products              : {len(combined)}  (Shopee {len(shopee)}, Lazada {len(lazada)})
Price (mean)          : Shopee PHP {price_stats.loc['Shopee','mean']:.2f}  |  Lazada PHP {price_stats.loc['Lazada','mean']:.2f}
Price (median)        : Shopee PHP {price_stats.loc['Shopee','median']:.2f}  |  Lazada PHP {price_stats.loc['Lazada','median']:.2f}
Avg discount (clean)  : Shopee {avg_discount.get('Shopee', 0):.2f}%  |  Lazada {avg_discount.get('Lazada', 0):.2f}%
Total sold (sold_final): Shopee {total_sold.get('Shopee', 0)}  |  Lazada {total_sold.get('Lazada', 0)}
Avg rating (rated)    : Shopee {avg_rating.get('Shopee', 0):.3f}  |  Lazada {avg_rating.get('Lazada', 0):.3f}
Rating/review corr r  : Shopee {corr_results.get('Shopee', 0):.4f}  |  Lazada {corr_results.get('Lazada', 0):.4f}
Total reviews scraped : Shopee {review_counts['Shopee']}  |  Lazada {review_counts['Lazada']}
Avg review length     : Shopee {avg_len['Shopee']:.2f} chars  |  Lazada {avg_len['Lazada']:.2f} chars
Suspicious listings   : {len(suspicious)} total ({susp_pct.get('Shopee', 0)}% of Shopee, {susp_pct.get('Lazada', 0)}% of Lazada)
Avg fake discount     : {avg_fake_discount:.2f}%
Charts saved to       : {ASSETS_DIR}
""")
