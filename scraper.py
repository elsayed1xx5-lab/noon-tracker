"""
Noon Egypt daily scraper.
Fetches category pages, extracts product data, saves daily snapshot to SQLite.
Runs once per day via GitHub Actions (or locally via `python scraper.py`).
"""
import os
import re
import time
import sqlite3
import random
import datetime as dt
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup

# curl_cffi impersonates a real Chrome TLS fingerprint - much more likely
# to bypass Cloudflare than plain `requests`.
try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    import requests as std_requests
    HAS_CFFI = False

from categories import CATEGORIES, PRODUCTS_PER_CATEGORY

DB_PATH = Path(__file__).parent / "noon_data.db"

# Optional fallback: if you get blocked, sign up free at scraperapi.com
# (1000 requests/month free) and set the env var SCRAPERAPI_KEY.
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ---------- DB setup ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date  TEXT NOT NULL,
            category       TEXT NOT NULL,
            rank_in_cat    INTEGER,
            product_id     TEXT,
            title          TEXT,
            url            TEXT,
            price_egp      REAL,
            original_price REAL,
            discount_pct   INTEGER,
            rating         REAL,
            reviews_count  INTEGER,
            sold_recently  INTEGER,
            best_seller    INTEGER,
            category_rank  TEXT,
            fulfillment    TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON snapshots(snapshot_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pid  ON snapshots(product_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cat  ON snapshots(category)")
    conn.commit()
    return conn


# ---------- Parsing helpers ----------
def parse_number(s):
    """'1.6K' -> 1600, '4.4K' -> 4400, '197' -> 197"""
    if not s:
        return None
    s = s.strip().replace(",", "")
    m = re.match(r"([\d.]+)\s*([KMkm]?)", s)
    if not m:
        return None
    num = float(m.group(1))
    suf = m.group(2).upper()
    if suf == "K":
        num *= 1000
    elif suf == "M":
        num *= 1_000_000
    return int(num)


def parse_sold(text):
    """'680+ sold recently' -> 680"""
    if not text:
        return None
    m = re.search(r"(\d+)\+?\s*sold", text)
    return int(m.group(1)) if m else None


def parse_price(text):
    """'EGP 375.60' or '**375.60**' -> 375.60"""
    if not text:
        return None
    m = re.search(r"([\d,]+\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def extract_product_id(url):
    """/egypt-en/.../N70184260V/p/... -> N70184260V"""
    m = re.search(r"/([A-Z0-9]{8,})/p/", url)
    return m.group(1) if m else None


# ---------- Scraping ----------
def _direct_fetch(url, timeout=30):
    if HAS_CFFI:
        r = cffi_requests.get(url, impersonate="chrome120", timeout=timeout)
    else:
        r = std_requests.get(url, headers=HEADERS, timeout=timeout)
    return r.status_code, r.text


def _scraperapi_fetch(url, timeout=60):
    """Fallback via ScraperAPI (free tier: 1000 req/month). Handles Cloudflare."""
    api_url = (
        f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}"
        f"&url={quote(url, safe='')}&country_code=eg"
    )
    r = cffi_requests.get(api_url, timeout=timeout) if HAS_CFFI \
        else std_requests.get(api_url, timeout=timeout)
    return r.status_code, r.text


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            status, text = _direct_fetch(url)
            if status == 200:
                return text
            print(f"  [warn] direct status {status}, retry {attempt + 1}")
        except Exception as e:
            print(f"  [warn] direct error: {e}, retry {attempt + 1}")
        time.sleep(2 + attempt * 2)

    # Fallback to ScraperAPI if key is provided
    if SCRAPERAPI_KEY:
        print("  [i] falling back to ScraperAPI...")
        try:
            status, text = _scraperapi_fetch(url)
            if status == 200:
                return text
            print(f"  [warn] ScraperAPI status {status}")
        except Exception as e:
            print(f"  [warn] ScraperAPI error: {e}")

    return None


def parse_products(html, category_name, limit):
    """
    Noon renders each product as an <a> tag containing the whole card.
    We locate cards by finding links matching the product URL pattern.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    # Every product card is an <a> whose href ends with `/p/...`
    for a in soup.find_all("a", href=re.compile(r"/p/")):
        href = a.get("href", "")
        pid = extract_product_id(href)
        if not pid or pid in seen:
            continue
        seen.add(pid)

        # Full text of the card carries all the visible info
        card_text = a.get_text("", strip=True)
        # --- Title extraction: multi-strategy (works with Noon's compressed HTML) ---
        title = None

        # Strategy A: try each img alt, skip placeholders
        for img_tag in a.find_all("img"):
            alt = (img_tag.get("alt") or "").strip()
            if not alt or alt.lower() == "placeholder":
                continue
            alt_clean = re.sub(r'^placeholder\s*', '', alt).strip()
            alt_clean = re.sub(r'\s*-\s*Image\s*\d+\s*$', '', alt_clean).strip()
            if alt_clean and alt_clean.lower() != 'placeholder' and len(alt_clean) > 10:
                title = alt_clean
                break

        # Strategy B: parse from card text (handles NO-whitespace case)
        if not title:
            for pattern in [
                r'add-to-cart(.+?)(?=[0-5]\.\d[\d.]+[KMkm]?EGP)',
                r'add-to-cart(.+?)(?=EGP)',
            ]:
                m = re.search(pattern, card_text)
                if m:
                    cand = m.group(1).strip()
                    cand = re.sub(r'^(Best Seller|wishlist)\s*', '', cand).strip()
                    cand = re.sub(r'\s*(Best Seller|wishlist)\s*$', '', cand).strip()
                    if len(cand) > 10:
                        title = cand
                        break

        if not title:
            title = card_text[:150] if card_text else "Unknown"
        # --- Price ---
        # Prices are wrapped in <strong> tags after "EGP"
        price = None
        strong = a.find("strong")
        if strong:
            price = parse_price(strong.get_text())

        # --- Original price + discount ---
        original_price = None
        discount = None
        disc_match = re.search(r"([\d,]+)\s*(\d+)%\s*Off", card_text)
        if disc_match:
            original_price = parse_price(disc_match.group(1))
            discount = int(disc_match.group(2))

        # --- Rating (first standalone decimal 0-5 followed by review count) ---
        rating = None
        reviews = None
        rr = re.search(r"\b([0-5]\.\d)\s*([\d.]+[KMkm]?)\b", card_text)
        if rr:
            rating = float(rr.group(1))
            reviews = parse_number(rr.group(2))

        # --- Sold recently ---
        sold = parse_sold(card_text)

        # --- Best Seller badge ---
        best_seller = 1 if "Best Seller" in card_text else 0

        # --- Category rank (#3 in Wall Chargers) ---
        cat_rank = None
        cr = re.search(r"(#\d+\s+in\s+[A-Za-z &]+)", card_text)
        if cr:
            cat_rank = cr.group(1).strip()

        # --- Fulfillment (noon-express / noon-marketplace / market) ---
        fulfillment = None
        for tag in ("noon-express", "noon-marketplace", "market"):
            if tag in card_text:
                fulfillment = tag
                break

        products.append({
            "product_id": pid,
            "title": title,
            "url": "https://www.noon.com" + href if href.startswith("/") else href,
            "price_egp": price,
            "original_price": original_price,
            "discount_pct": discount,
            "rating": rating,
            "reviews_count": reviews,
            "sold_recently": sold,
            "best_seller": best_seller,
            "category_rank": cat_rank,
            "fulfillment": fulfillment,
        })

        if len(products) >= limit:
            break

    return products


def scrape_all(conn):
    today = dt.date.today().isoformat()
    total_saved = 0

    for cat_name, url in CATEGORIES.items():
        print(f"\n[+] {cat_name}")
        html = fetch(url)
        if not html:
            print(f"    [error] could not fetch")
            continue

        products = parse_products(html, cat_name, PRODUCTS_PER_CATEGORY)
        print(f"    parsed {len(products)} products")

        for rank, p in enumerate(products, start=1):
            conn.execute("""
                INSERT INTO snapshots (
                    snapshot_date, category, rank_in_cat, product_id, title, url,
                    price_egp, original_price, discount_pct, rating, reviews_count,
                    sold_recently, best_seller, category_rank, fulfillment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today, cat_name, rank, p["product_id"], p["title"], p["url"],
                p["price_egp"], p["original_price"], p["discount_pct"],
                p["rating"], p["reviews_count"], p["sold_recently"],
                p["best_seller"], p["category_rank"], p["fulfillment"],
            ))
            total_saved += 1
        conn.commit()

        # Be polite: 3–6s between categories
        time.sleep(random.uniform(3, 6))

    print(f"\n[✓] Saved {total_saved} rows for {today}")


if __name__ == "__main__":
    conn = init_db()

    # Skip if we already have today's data (in case of double-run)
    today = dt.date.today().isoformat()
    existing = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE snapshot_date = ?", (today,)
    ).fetchone()[0]
    if existing > 0:
        print(f"[i] {existing} rows already exist for {today}, skipping.")
    else:
        scrape_all(conn)

    conn.close()
