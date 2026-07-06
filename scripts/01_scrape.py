"""01_scrape.py - fully automated, headless scrape of Shopee PH + Lazada PH.
No manual intervention: CAPTCHA/blocks are detected and skipped gracefully,
never waited on. Output: data/raw/hghmnds_MERGED_[timestamp].xlsx +
data/raw/latest.xlsx (fixed-name copy) + data/raw/weekly_diff_[timestamp].json.
"""
import asyncio
import json
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

RAW_DIR = ROOT / settings.RAW_DIR
RAW_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

LAZADA_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]
SHOPEE_UA = LAZADA_USER_AGENTS[0]

MAX_REVIEWS = 50
PAGE_TIMEOUT_MS = 25000
MAX_RETRIES = 3
RETRY_WAIT = 5

LAZADA_STORE_URLS = [
    "https://www.lazada.com.ph/shop/hghmnds/",
    "https://www.lazada.com.ph/shop/hghmnds-clothing/",
]


def random_delay():
    return random.uniform(1.5, 3.0)


def parse_sold(text):
    """'1.2K sold' -> 1200 ; '850 sold' -> 850 ; '' -> ''"""
    if not text:
        return ""
    m = re.search(r"([\d.]+)\s*([KkMm]?)", text.replace(",", ""))
    if not m:
        return ""
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(float(m.group(1)) * mult)


def clean_item_id(raw):
    """'pdp-i3495077605.html' -> '3495077605'"""
    if not raw:
        return ""
    m = re.search(r"i(\d+)", str(raw))
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", str(raw))
    return digits or str(raw)


def is_real_image(url):
    return bool(url) and url.startswith("http")


def is_blocked(title, url):
    t = (title or "").lower()
    return (
        "captcha" in t or "access denied" in t or "verify" in t
        or "captcha" in url or "/verify/" in url or "punish" in url
    )


# ───────────────────────── SHOPEE (JSON API) ─────────────────────────

SHOPEE_SEARCH = (
    "https://shopee.ph/api/v4/search/search_items"
    "?by=relevancy&keyword={kw}&limit=100&newest={offset}&order=desc"
    "&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
)
SHOPEE_ITEM = "https://shopee.ph/api/v4/item/get?itemid={iid}&shopid={sid}"
SHOPEE_RATINGS = (
    "https://shopee.ph/api/v4/item/get_ratings"
    f"?filter=0&flag=1&itemid={{iid}}&limit={MAX_REVIEWS}&offset=0&shopid={{sid}}&type=0"
)


async def shopee_fetch(page, url):
    """Fetch a Shopee API URL from inside the page context (uses session
    cookies established by browsing shopee.ph)."""
    try:
        res = await asyncio.wait_for(
            page.evaluate(
                """async (u) => {
                    const ctrl = new AbortController();
                    setTimeout(() => ctrl.abort(), 20000);
                    const r = await fetch(u, {credentials: 'include',
                        signal: ctrl.signal,
                        headers: {'x-requested-with': 'XMLHttpRequest'}});
                    return {status: r.status, body: await r.text()};
                }""",
                url,
            ),
            timeout=30,
        )
        if res["status"] != 200:
            return None
        data = json.loads(res["body"])
        if data.get("error") not in (None, 0):
            return None
        return data
    except Exception:
        return None


async def scrape_shopee(browser):
    print("\n[SHOPEE] Starting (fully automated, headless)...")
    products, reviews = {}, []
    context = await browser.new_context(
        user_agent=SHOPEE_UA, viewport={"width": 1366, "height": 768}, locale="en-PH")
    page = await context.new_page()

    try:
        await page.goto("https://shopee.ph/search?keyword=hghmnds",
                         wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        await asyncio.sleep(5)
        title = await page.title()
        if is_blocked(title, page.url):
            print("  [!] Blocked immediately on session page. Skipping Shopee this run.")
            await context.close()
            return [], []
    except Exception as e:
        print(f"  [!] Could not open shopee.ph: {e}")
        await context.close()
        return [], []

    for kw in settings.SHOPEE_KEYWORDS:
        print(f"  [~] Keyword: '{kw}'")
        offset = 0
        while True:
            data = await shopee_fetch(
                page, SHOPEE_SEARCH.format(kw=kw.replace(" ", "%20"), offset=offset))
            if data is None:
                print("      [!] API blocked or errored (Shopee anti-bot). Stopping this keyword.")
                break
            items = data.get("items") or []
            if not items:
                break
            print(f"      offset {offset}: {len(items)} items")
            for it in items:
                info = it.get("item_basic") or {}
                iid, sid = info.get("itemid"), info.get("shopid")
                if not iid or str(iid) in products:
                    continue
                rc = (info.get("item_rating") or {}).get("rating_count") or [0]
                stars = rc + [0] * (6 - len(rc))
                img = info.get("image", "")
                products[str(iid)] = {
                    "platform": "Shopee",
                    "item_id": str(iid),
                    "shop_id": str(sid),
                    "product_name": info.get("name", ""),
                    "seller_name": info.get("shop_name", ""),
                    "price": (info.get("price") or 0) / 100000,
                    "original_price": (info.get("price_before_discount") or 0) / 100000,
                    "discount_pct": info.get("discount", ""),
                    "stock": info.get("stock", ""),
                    "sold_30d": info.get("sold", ""),
                    "sold_lifetime": info.get("historical_sold", ""),
                    "rating_avg": (info.get("item_rating") or {}).get("rating_star", ""),
                    "review_count": stars[0],
                    "star_5": stars[5], "star_4": stars[4], "star_3": stars[3],
                    "star_2": stars[2], "star_1": stars[1],
                    "description": "",
                    "category": "",
                    "variations": "",
                    "url": f"https://shopee.ph/product/{sid}/{iid}",
                    "image_url": f"https://down-ph.img.susercontent.com/file/{img}" if img else "",
                    "search_keyword": kw,
                    "scraped_at": TIMESTAMP,
                }
            if len(items) < 100:
                break
            offset += 100
            await asyncio.sleep(random_delay())

    if products:
        print(f"  [*] Enriching {len(products)} Shopee items "
              f"(detail + up to {MAX_REVIEWS} reviews)...")
        for n, p in enumerate(products.values(), 1):
            detail = await shopee_fetch(
                page, SHOPEE_ITEM.format(iid=p["item_id"], sid=p["shop_id"]))
            d = (detail or {}).get("data") or (detail or {}).get("item")
            if d:
                p["description"] = (d.get("description") or "")[:3000]
                p["category"] = " > ".join(
                    c.get("display_name", "") for c in d.get("categories") or [])
                p["variations"] = json.dumps([
                    {v.get("name", ""): v.get("options", [])}
                    for v in d.get("tier_variations") or []
                ], ensure_ascii=False)

            rd = await shopee_fetch(
                page, SHOPEE_RATINGS.format(iid=p["item_id"], sid=p["shop_id"]))
            if rd and (rd.get("data") or {}).get("ratings"):
                for r in rd["data"]["ratings"][:MAX_REVIEWS]:
                    ts = r.get("ctime")
                    reviews.append({
                        "platform": "Shopee",
                        "item_id": p["item_id"],
                        "product_name": p["product_name"],
                        "rating": r.get("rating_star", ""),
                        "review_text": r.get("comment", ""),
                        "buyer_name": r.get("author_username", ""),
                        "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                                if ts else "",
                    })
            if n % 10 == 0:
                print(f"      [{n}/{len(products)}]")
            await asyncio.sleep(random_delay())

    await context.close()
    print(f"  [DONE] Shopee: {len(products)} products, {len(reviews)} reviews")
    return list(products.values()), reviews


# ──────────────────────── LAZADA (Playwright) ────────────────────────

async def new_lazada_context(browser, ua_idx):
    ua = LAZADA_USER_AGENTS[ua_idx % len(LAZADA_USER_AGENTS)]
    context = await browser.new_context(
        user_agent=ua, viewport={"width": 1366, "height": 768}, locale="en-PH")
    page = await context.new_page()
    return context, page


async def robust_goto(browser, url, label=""):
    """Navigate with up to MAX_RETRIES attempts, rotating user agent each
    retry. Returns (context, page) on success (caller must close context),
    or (None, None) if every attempt failed/was blocked."""
    for attempt in range(MAX_RETRIES):
        context, page = await new_lazada_context(browser, attempt)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            await asyncio.sleep(2)
            title = await page.title()
            if not is_blocked(title, page.url):
                return context, page
            print(f"    [!] Blocked on {label or url} (attempt {attempt + 1}/{MAX_RETRIES}).")
        except Exception as e:
            print(f"    [!] Nav failed on {label or url} "
                  f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        await context.close()
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_WAIT)
    return None, None


async def wait_for_real_images(page, timeout_s=10):
    """Poll until at least one real (non-base64) lazcdn image is present."""
    for _ in range(timeout_s * 2):
        found = await page.evaluate(
            "() => Array.from(document.querySelectorAll('img')).some("
            "img => (img.src || '').includes('lazcdn.com'))"
        )
        if found:
            return True
        await asyncio.sleep(0.5)
    return False


async def lazada_collect_cards(page, products, source_label):
    for _ in range(6):
        await page.keyboard.press("End")
        await asyncio.sleep(1.5)
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(2)
    for _ in range(6):
        await page.mouse.wheel(0, 900)
        await asyncio.sleep(1.0)
    await wait_for_real_images(page, timeout_s=8)

    cards = await page.query_selector_all("[data-qa-locator='product-item'], .Bm3ON")
    print(f"      cards in DOM: {len(cards)}")
    new = 0
    for card in cards:
        try:
            link_el = await card.query_selector("a[href*='.html']")
            link = (await link_el.get_attribute("href")) if link_el else ""
            if link and not link.startswith("http"):
                link = "https:" + link
            if not link:
                continue
            item_id = clean_item_id(link.split("/")[-1].split("?")[0])
            if not item_id or item_id in products:
                continue

            async def txt(sel):
                el = await card.query_selector(sel)
                return (await el.inner_text()).strip() if el else ""

            name_el = await card.query_selector("[title], .RfADt a, .RfADt")
            name = ""
            if name_el:
                name = (await name_el.get_attribute("title")) or \
                       (await name_el.inner_text())

            price_txt = await txt(".ooOxS, [data-qa-locator='product-price'], .aBrP0")
            orig_txt = await txt(".WNoq3, ._1m41m del")
            price = re.sub(r"[^\d.]", "", price_txt.replace(",", ""))
            orig = re.sub(r"[^\d.]", "", orig_txt.replace(",", ""))

            sold_txt = await txt("._1cEkb, .WsSaz")
            review_txt = await txt(".qzqFw, ._8kiEy")
            rev_digits = re.sub(r"[^\d]", "", review_txt)

            img_el = await card.query_selector("img[type='product'], img")
            img = ""
            if img_el:
                img = (await img_el.get_attribute("src")) or ""
                if not is_real_image(img):
                    img = (await img_el.get_attribute("data-src")) or ""
                if not is_real_image(img):
                    img = ""

            p, o = (float(price) if price else ""), (float(orig) if orig else "")
            disc = round((1 - p / o) * 100, 1) if p and o and o > 0 else ""

            products[item_id] = {
                "platform": "Lazada",
                "item_id": item_id,
                "product_name": (name or "").strip(),
                "seller_name": "",
                "price": p,
                "original_price": o,
                "discount_pct": disc,
                "stock": "",
                "sold_30d": "",
                "sold_lifetime": parse_sold(sold_txt),
                "rating_avg": "",
                "review_count": int(rev_digits) if rev_digits else "",
                "star_5": "", "star_4": "", "star_3": "", "star_2": "", "star_1": "",
                "description": "",
                "category": "",
                "variations": "",
                "url": link.split("?")[0],
                "image_url": img,
                "search_keyword": source_label,
                "scraped_at": TIMESTAMP,
            }
            new += 1
        except Exception:
            continue
    print(f"      new unique products: {new} (total {len(products)})")


async def lazada_page_fetch(page, url):
    """Fetch a Lazada API URL using the browser context's cookies."""
    try:
        res = await page.request.get(url, timeout=15000)
        if res.status != 200:
            return None
        return json.loads(await res.text())
    except Exception:
        return None


def _json_unescape(s):
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


async def lazada_enrich(page, product, reviews):
    """Pull structured data from the embedded ld+json / app JSON on an
    already-loaded product detail page, plus reviews from Lazada's API."""
    html = await page.content()

    for m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL):
        try:
            ld = json.loads(m.group(1))
        except Exception:
            continue
        nodes = ld if isinstance(ld, list) else [ld]
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "Product":
                continue
            desc = re.sub(r"<[^>]+>", " ", node.get("description") or "")
            desc = re.sub(r"\s+", " ", desc).strip()
            if desc:
                product["description"] = desc[:3000]
            agg = node.get("aggregateRating") or {}
            if agg.get("ratingValue"):
                product["rating_avg"] = agg["ratingValue"]
            if agg.get("reviewCount") and not product.get("review_count"):
                product["review_count"] = agg["reviewCount"]
            img = node.get("image") or ""
            if isinstance(img, list):
                img = img[0] if img else ""
            if is_real_image(img):
                product["image_url"] = img

    m = re.search(r'"sellerName"\s*:\s*"([^"]*)"', html)
    if m:
        product["seller_name"] = _json_unescape(m.group(1))

    crumbs = await page.query_selector_all("#J_breadcrumb li, .breadcrumb_item")
    if crumbs:
        parts = [(await c.inner_text()).strip() for c in crumbs]
        product["category"] = " > ".join(x for x in parts if x)

    var_els = await page.query_selector_all(
        ".sku-selector .sku-variable-name, .sku-prop-content span, .sku-variable-size")
    if var_els:
        vals = [(await v.inner_text()).strip() for v in var_els]
        product["variations"] = json.dumps([v for v in vals if v], ensure_ascii=False)

    api = ("https://my.lazada.com.ph/pdp/review/getReviewList"
           f"?itemId={product['item_id']}&pageSize={MAX_REVIEWS}"
           "&filter=0&sort=0&pageNo=1")
    data = await lazada_page_fetch(page, api)
    model = (data or {}).get("model") or {}

    scores = (model.get("ratings") or {}).get("scores")
    if isinstance(scores, list) and len(scores) >= 5:
        product["star_5"], product["star_4"], product["star_3"], \
            product["star_2"], product["star_1"] = scores[:5]
    avg = (model.get("ratings") or {}).get("average")
    if avg and not product.get("rating_avg"):
        product["rating_avg"] = avg

    for r in (model.get("items") or [])[:MAX_REVIEWS]:
        text = (r.get("reviewContent") or "").strip()
        if not (text or r.get("rating")):
            continue
        reviews.append({
            "platform": "Lazada",
            "item_id": product["item_id"],
            "product_name": product["product_name"],
            "rating": r.get("rating", ""),
            "review_text": text,
            "buyer_name": r.get("buyerName", ""),
            "date": r.get("reviewTime", "") or r.get("boughtDate", ""),
        })


async def scrape_lazada(browser):
    print("\n[LAZADA] Starting (fully automated, headless, UA rotation)...")
    products, reviews = {}, []

    search_urls = [
        f"https://www.lazada.com.ph/catalog/?q={kw.replace(' ', '+')}"
        for kw in settings.LAZADA_KEYWORDS
    ] + LAZADA_STORE_URLS

    for url in search_urls:
        label = url.split("q=")[-1].replace("+", " ") if "q=" in url else url
        print(f"  [~] Source: '{label}'")
        context, page = await robust_goto(browser, url, label=label)
        if not page:
            print(f"    [!] Gave up on '{label}' after {MAX_RETRIES} attempts.")
            continue
        try:
            await lazada_collect_cards(page, products, label)
        except Exception as e:
            print(f"    [!] Failed collecting cards: {e}")
        await context.close()
        await asyncio.sleep(random_delay())

    print(f"\n  [*] Enriching {len(products)} Lazada products (detail pages)...")
    for n, p in enumerate(products.values(), 1):
        context, page = await robust_goto(browser, p["url"], label=p["url"])
        if not page:
            print(f"    [!] {p['item_id']}: blocked after {MAX_RETRIES} attempts, "
                  f"skipping enrichment.")
        else:
            try:
                await asyncio.wait_for(lazada_enrich(page, p, reviews),
                                        timeout=PAGE_TIMEOUT_MS / 1000 + 15)
            except asyncio.TimeoutError:
                print(f"    [!] {p['item_id']}: enrich timed out, skipping")
            except Exception as e:
                print(f"    [!] {p['item_id']}: {e}")
            await context.close()
        if n % 10 == 0:
            print(f"      [{n}/{len(products)}]")
        await asyncio.sleep(random_delay())

    print(f"  [DONE] Lazada: {len(products)} products, {len(reviews)} reviews")
    return list(products.values()), reviews


# ─────────────────────────── WEEKLY DIFF ──────────────────────────────

def compute_weekly_diff(old_path, new_overview_df):
    """Compare item IDs between last run's data/raw/latest.xlsx and this
    run: new products, disappeared products, price changes > 20%, rating
    changes."""
    diff = {
        "generated_at": TIMESTAMP, "previous_file": None,
        "new_products": [], "disappeared_products": [],
        "price_changes": [], "rating_changes": [],
    }
    if not old_path or not old_path.exists():
        diff["note"] = "No previous data/raw/latest.xlsx found -- first run, nothing to diff."
        return diff

    diff["previous_file"] = old_path.name
    try:
        old_df = pd.read_excel(old_path, sheet_name="Combined_Overview")
    except Exception as e:
        diff["note"] = f"Could not read previous file: {e}"
        return diff

    old_df = old_df.copy()
    new_df = new_overview_df.copy()
    old_df["key"] = old_df["platform"].astype(str) + ":" + old_df["item_id"].astype(str)
    new_df["key"] = new_df["platform"].astype(str) + ":" + new_df["item_id"].astype(str)

    old_keys, new_keys = set(old_df["key"]), set(new_df["key"])

    for key in sorted(new_keys - old_keys):
        row = new_df[new_df["key"] == key].iloc[0]
        diff["new_products"].append({
            "platform": row["platform"], "item_id": str(row["item_id"]),
            "product_name": row["product_name"],
        })
    for key in sorted(old_keys - new_keys):
        row = old_df[old_df["key"] == key].iloc[0]
        diff["disappeared_products"].append({
            "platform": row["platform"], "item_id": str(row["item_id"]),
            "product_name": row["product_name"],
        })

    old_idx = old_df.set_index("key")
    new_idx = new_df.set_index("key")
    for key in sorted(old_keys & new_keys):
        try:
            old_price = float(old_idx.loc[key, "price"])
            new_price = float(new_idx.loc[key, "price"])
            if old_price > 0:
                pct = (new_price - old_price) / old_price * 100
                if abs(pct) > 20:
                    diff["price_changes"].append({
                        "platform": str(new_idx.loc[key, "platform"]),
                        "item_id": key.split(":", 1)[1],
                        "product_name": new_idx.loc[key, "product_name"],
                        "old_price": old_price, "new_price": new_price,
                        "pct_change": round(pct, 1),
                    })
        except Exception:
            pass
        try:
            old_rating, new_rating = old_idx.loc[key, "rating_avg"], new_idx.loc[key, "rating_avg"]
            if (pd.notna(old_rating) and pd.notna(new_rating)
                    and str(old_rating).strip() not in ("", "nan")
                    and str(new_rating).strip() not in ("", "nan")):
                old_r, new_r = float(old_rating), float(new_rating)
                if abs(old_r - new_r) >= 0.05:
                    diff["rating_changes"].append({
                        "platform": str(new_idx.loc[key, "platform"]),
                        "item_id": key.split(":", 1)[1],
                        "product_name": new_idx.loc[key, "product_name"],
                        "old_rating": old_r, "new_rating": new_r,
                    })
        except Exception:
            pass

    return diff


# ───────────────────────────── EXCEL OUT ─────────────────────────────

PRODUCT_COLS = [
    "platform", "item_id", "product_name", "seller_name", "price",
    "original_price", "discount_pct", "stock", "sold_30d", "sold_lifetime",
    "rating_avg", "review_count", "star_5", "star_4", "star_3", "star_2",
    "star_1", "description", "category", "variations", "url", "image_url",
    "search_keyword", "scraped_at",
]
REVIEW_COLS = ["platform", "item_id", "product_name", "rating",
               "review_text", "buyer_name", "date"]
OVERVIEW_COLS = ["platform", "item_id", "product_name", "price", "sold_lifetime",
                 "rating_avg", "review_count", "seller_name", "url"]


def summary_block(df, platform):
    if df.empty:
        return {"Platform": platform, "Products": 0, "Avg Price (PHP)": "",
                "Min Price": "", "Max Price": "", "Avg Rating": "",
                "Total Units Sold": "", "Total Reviews": ""}
    price = pd.to_numeric(df["price"], errors="coerce")
    rating = pd.to_numeric(df["rating_avg"], errors="coerce")
    sold = pd.to_numeric(df["sold_lifetime"], errors="coerce")
    revs = pd.to_numeric(df["review_count"], errors="coerce")
    return {
        "Platform": platform,
        "Products": len(df),
        "Avg Price (PHP)": round(price.mean(), 2),
        "Min Price": price.min(),
        "Max Price": price.max(),
        "Avg Rating": round(rating.mean(), 2) if rating.notna().any() else "",
        "Total Units Sold": int(sold.sum()) if sold.notna().any() else "",
        "Total Reviews": int(revs.sum()) if revs.notna().any() else "",
    }


def save_excel(shopee_p, shopee_r, lazada_p, lazada_r):
    df_sp = pd.DataFrame(shopee_p, columns=PRODUCT_COLS)
    df_sr = pd.DataFrame(shopee_r, columns=REVIEW_COLS)
    df_lp = pd.DataFrame(lazada_p, columns=PRODUCT_COLS)
    df_lr = pd.DataFrame(lazada_r, columns=REVIEW_COLS)

    combined = pd.concat(
        [df_sp[OVERVIEW_COLS] if not df_sp.empty else pd.DataFrame(columns=OVERVIEW_COLS),
         df_lp[OVERVIEW_COLS] if not df_lp.empty else pd.DataFrame(columns=OVERVIEW_COLS)],
        ignore_index=True)

    stats = pd.DataFrame([summary_block(df_sp, "Shopee"), summary_block(df_lp, "Lazada")])

    latest_path = RAW_DIR / "latest.xlsx"
    diff = compute_weekly_diff(latest_path if latest_path.exists() else None, combined)
    diff_path = RAW_DIR / f"weekly_diff_{TIMESTAMP}.json"
    with open(diff_path, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[DIFF] new={len(diff['new_products'])} "
          f"disappeared={len(diff['disappeared_products'])} "
          f"price_changes={len(diff['price_changes'])} "
          f"rating_changes={len(diff['rating_changes'])}")
    print(f"[OK] Weekly diff saved: {diff_path}")

    all_p = pd.concat([df_sp, df_lp], ignore_index=True)
    if not all_p.empty:
        all_p["_sold"] = pd.to_numeric(all_p["sold_lifetime"], errors="coerce")
        top10 = (all_p.sort_values("_sold", ascending=False).head(10)
                 [["platform", "product_name", "price", "sold_lifetime",
                   "rating_avg", "url"]])
    else:
        top10 = pd.DataFrame()

    out_path = RAW_DIR / f"hghmnds_MERGED_{TIMESTAMP}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df_sp.to_excel(w, sheet_name="Shopee_Products", index=False)
        df_sr.to_excel(w, sheet_name="Shopee_Reviews", index=False)
        df_lp.to_excel(w, sheet_name="Lazada_Products", index=False)
        df_lr.to_excel(w, sheet_name="Lazada_Reviews", index=False)
        combined.to_excel(w, sheet_name="Combined_Overview", index=False)
        stats.to_excel(w, sheet_name="Summary_Stats", index=False)
        if not top10.empty:
            top10.to_excel(w, sheet_name="Summary_Stats", index=False,
                           startrow=len(stats) + 3)

    shutil.copy(out_path, latest_path)

    print(f"\n[OK] Excel saved: {out_path}")
    print(f"[OK] Fixed-name copy: {latest_path}")
    return out_path


# ─────────────────────────────── MAIN ───────────────────────────────

async def main():
    print("=" * 60)
    print(" HGHMNDS Weekly Scrape - Shopee PH + Lazada PH (fully headless)")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        shopee_p, shopee_r = await scrape_shopee(browser)
        lazada_p, lazada_r = await scrape_lazada(browser)
        await browser.close()

    print(f"\n[SUMMARY] Shopee: {len(shopee_p)} products / {len(shopee_r)} reviews")
    print(f"[SUMMARY] Lazada: {len(lazada_p)} products / {len(lazada_r)} reviews")
    save_excel(shopee_p, shopee_r, lazada_p, lazada_r)


if __name__ == "__main__":
    asyncio.run(main())
