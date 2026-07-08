#!/usr/bin/env python3
"""
Revamp Catalog — daily sync/build script
-----------------------------------------
Pulls the "Products" tab from the Obs Alpha Google Sheet using a service
account (read-only use), merges it on top of the static base catalog
(products_base.json — images/specs/etc scraped once from the source site),
and regenerates index.html from index_template.html with the merged data
and a "last synced" timestamp baked in.

This is meant to be run once a day by the GitHub Actions workflow at
.github/workflows/daily-sync.yml, but can also be run locally:

    export GOOGLE_SERVICE_ACCOUNT_KEY="$(cat friday-gsheets-key.json)"
    python3 build/build_sync.py

Env vars:
    GOOGLE_SERVICE_ACCOUNT_KEY  - full JSON contents of the service account key
    SHEET_ID                   - defaults to the Obs Alpha sheet below
"""
import os
import sys
import json
import datetime
import copy

sys.path.insert(0, os.path.dirname(__file__))

SHEET_ID = os.environ.get("SHEET_ID", "1v_51cC31snUoFKo7hB5vttn__jPUgBNsKO8t6z3ttFU")
PRODUCTS_RANGE = "Products!A1:X1000"
ORDER_DISCOUNTS_RANGE = "OrderDiscounts!A1:C50"

BUILD_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BUILD_DIR)
BASE_JSON_PATH = os.path.join(BUILD_DIR, "products_base.json")
TEMPLATE_PATH = os.path.join(BUILD_DIR, "index_template.html")
OUTPUT_HTML_PATH = os.path.join(REPO_ROOT, "index.html")


def get_sheets_session():
    """Returns an authorized requests Session for the Sheets API, or None if
    no service account key is configured (local dry-run)."""
    key_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not key_json:
        print("No GOOGLE_SERVICE_ACCOUNT_KEY set — skipping live sync, using base catalog as-is.")
        return None

    os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession

    info = json.loads(key_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return AuthorizedSession(creds)


def fetch_range_rows(session, range_str):
    """Fetch a sheet range as a list of dicts (header -> value)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{range_str}"
    resp = session.get(url)
    resp.raise_for_status()
    values = resp.json().get("values", [])
    if not values:
        return []
    headers = [h.strip() for h in values[0]]
    rows = []
    for row in values[1:]:
        if not any(c.strip() for c in row if isinstance(c, str)):
            continue
        obj = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        rows.append(obj)
    return rows


def fetch_order_discounts(session):
    """Fetch the OrderDiscounts tab as a sorted list of {minValue, discountPct}.
    Returns [] if the tab is missing/empty or there's no session."""
    if session is None:
        return []
    try:
        rows = fetch_range_rows(session, ORDER_DISCOUNTS_RANGE)
    except Exception as e:
        print(f"Could not read OrderDiscounts tab (does it exist?): {e}")
        return []
    tiers = []
    for r in rows:
        min_val = to_float(r.get("MinOrderValue"))
        disc = to_float(r.get("DiscountPct"))
        if min_val is None or disc is None:
            continue
        tiers.append({"minValue": min_val, "discountPct": disc, "label": r.get("Label", "")})
    tiers.sort(key=lambda t: t["minValue"])
    return tiers


def to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def merge_row_into_product(p, row):
    merged = copy.deepcopy(p)
    if row.get("Name"):
        merged["name"] = row["Name"]
    if row.get("Material"):
        merged["material"] = row["Material"]
    if row.get("Dimensions"):
        merged["dimensions"] = row["Dimensions"]

    # ProductImage = the actual panel/material photo — the ONLY image shown
    # on the catalog landing page (card thumbnail). MoldImage/LookImage1/
    # LookImage2 are only shown on the product detail page (main gallery +
    # look book), never on the landing grid. If any of these four are filled
    # in on the Products tab, they fully replace the scraped images for this
    # SKU (in this order) — this is how mismatched/wrong images get
    # corrected, and how mold/look-book photos get added per SKU.
    image_cols = [row.get("ProductImage"), row.get("MoldImage"), row.get("LookImage1"), row.get("LookImage2")]
    new_images = [u.strip() for u in image_cols if u and str(u).strip()]
    if new_images:
        merged["images"] = new_images

    price_num = to_float(row.get("Price"))
    if price_num is not None:
        merged["price"]["current"] = price_num
    orig_num = to_float(row.get("OriginalPrice"))
    if orig_num is not None:
        merged["price"]["original"] = orig_num
    disc_num = to_float(row.get("DiscountPct"))
    if disc_num is not None:
        merged["price"]["discountPct"] = disc_num

    inv_num = to_float(row.get("InventoryQty"))
    if inv_num is not None:
        merged["inventory"]["qty"] = inv_num
    moq_num = to_float(row.get("MOQ"))
    if moq_num is not None:
        merged["inventory"]["moq"] = moq_num
    if row.get("StockStatus"):
        merged["inventory"]["status"] = row["StockStatus"]

    if row.get("LiveStatus"):
        merged["liveStatus"] = row["LiveStatus"]
        merged["needsData"] = str(row["LiveStatus"]).strip().lower() != "live"

    return merged


def build():
    base_products = json.load(open(BASE_JSON_PATH))
    session = get_sheets_session()

    if session is not None:
        rows = fetch_range_rows(session, PRODUCTS_RANGE)
        by_slug = {r.get("Slug"): r for r in rows if r.get("Slug")}
        merged = [
            merge_row_into_product(p, by_slug[p["slug"]]) if p["slug"] in by_slug else p
            for p in base_products
        ]
        print(f"Synced {len(by_slug)} rows from Obs Alpha, merged into {len(merged)} products.")
        order_discounts = fetch_order_discounts(session)
        print(f"Synced {len(order_discounts)} order-value discount tier(s) from Obs Alpha.")
    else:
        merged = base_products
        order_discounts = []

    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    now = datetime.datetime.now(datetime.timezone.utc)
    ist = now + datetime.timedelta(hours=5, minutes=30)
    stamp = ist.strftime("%d %b %Y, %I:%M %p IST")

    html = template.replace("__PRODUCTS_JSON__", json.dumps(merged, ensure_ascii=False))
    html = html.replace("__ORDER_DISCOUNTS_JSON__", json.dumps(order_discounts, ensure_ascii=False))
    html = html.replace("__LAST_SYNCED__", stamp)

    with open(OUTPUT_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_HTML_PATH} ({len(html)} bytes), last synced: {stamp}")


if __name__ == "__main__":
    build()
