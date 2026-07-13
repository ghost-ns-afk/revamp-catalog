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
import re
import sys
import json
import datetime
import copy

sys.path.insert(0, os.path.dirname(__file__))

SHEET_ID = os.environ.get("SHEET_ID", "1v_51cC31snUoFKo7hB5vttn__jPUgBNsKO8t6z3ttFU")
PRODUCTS_RANGE = "Products!A1:X1000"
ORDER_DISCOUNTS_RANGE = "OrderDiscounts!A1:C50"

# Obs Alpha is the single source of truth for which SKUs exist on the site.
# Any row present in the Products tab (regardless of whether it also exists
# in products_base.json) can appear; anything NOT present in the tab at all
# is treated as removed and will not be shown, even if it was scraped
# originally. Category values typed into the sheet get normalized to one of
# these five internal keys via CATEGORY_MAP.
CATEGORY_MAP = {
    "wall panels": "panels",
    "wall panel": "panels",
    "sheets": "panels",
    "tv console": "woodwork",
    "desk": "woodwork",
    "cabinet": "woodwork",
    "mandir unit": "woodwork",
    "shelf": "woodwork",
    "wooden units": "woodwork",
    "light profiles": "lightprofiles",
    "wall mouldings": "mouldings",
    "decorative lights": "decorlight",
}
CATEGORY_LABELS = {
    "panels": "Wall Panels",
    "woodwork": "Wooden Units",
    "decorlight": "Decorative Lights",
    "lightprofiles": "Light Profiles",
    "mouldings": "Wall Mouldings",
}


def slugify(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def resolve_category(row):
    raw = (row.get("Category") or "").strip().lower()
    return CATEGORY_MAP.get(raw, "panels")

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

    # LiveStatus is read fresh from the sheet on every sync — a blank cell
    # is treated as "not live" rather than silently keeping whatever was
    # baked into products_base.json, since Obs Alpha is now the source of
    # truth for what's actually live.
    live_status_raw = str(row.get("LiveStatus", "")).strip()
    merged["liveStatus"] = live_status_raw or "Unknown"
    merged["needsData"] = live_status_raw.lower() != "live"

    return merged


def build_new_product_from_row(row, slug):
    """Builds a brand-new product entry for a sheet row that has no match in
    products_base.json (e.g. a new SKU typed directly into Obs Alpha rather
    than scraped from the source site)."""
    category = resolve_category(row)
    name = (row.get("Name") or "").strip()
    sku = (row.get("SKU") or "").strip()

    price_num = to_float(row.get("Price"))
    orig_num = to_float(row.get("OriginalPrice"))
    disc_num = to_float(row.get("DiscountPct"))
    if disc_num is None and price_num is not None and orig_num:
        disc_num = round((1 - price_num / orig_num) * 100)
    inv_num = to_float(row.get("InventoryQty"))
    moq_num = to_float(row.get("MOQ"))

    image_cols = [row.get("ProductImage"), row.get("MoldImage"), row.get("LookImage1"), row.get("LookImage2")]
    images = [u.strip() for u in image_cols if u and str(u).strip()]
    specs = [s.strip() for s in (row.get("Specs") or "").split(";") if s.strip()]

    live_status_raw = str(row.get("LiveStatus", "")).strip()
    # LiveStatus alone decides visibility — if it's marked Live it shows,
    # even if some fields (Name/Price/Image) are still blank. Missing pieces
    # fall back to placeholders (SKU as name, "—" price, placeholder image)
    # rather than being hidden, so partially-filled rows are still visible
    # while you finish filling them in.
    needs_data = live_status_raw.lower() != "live"

    return {
        "id": slug,
        "slug": slug,
        "url": row.get("SourceURL", "") or "",
        "sku": sku,
        "name": name or sku or "Untitled product",
        "category": category,
        "categoryLabel": CATEGORY_LABELS.get(category, "Wall Panels"),
        "collection": row.get("Collection") or None,
        "material": row.get("Material") or None,
        "dimensions": row.get("Dimensions") or None,
        "panelGroup": row.get("PanelGroup") or None,
        "images": images,
        "specs": specs,
        "sizeVariants": [],
        "price": {
            "unit": row.get("PriceUnit") or "flat_or_base",
            "current": price_num,
            "original": orig_num,
            "discountPct": disc_num,
        },
        "inventory": {
            "qty": inv_num if inv_num is not None else 0,
            "moq": moq_num if moq_num is not None else 1,
            "status": row.get("StockStatus") or "in_stock",
        },
        "needsData": needs_data,
        "liveStatus": live_status_raw or "Unknown",
    }


def build():
    base_products = json.load(open(BASE_JSON_PATH))
    base_by_slug = {p["slug"]: p for p in base_products}
    session = get_sheets_session()

    if session is not None:
        rows = fetch_range_rows(session, PRODUCTS_RANGE)

        merged = []
        seen_slugs = set()
        matched_count = 0
        new_count = 0
        for row in rows:
            raw_slug = (row.get("Slug") or "").strip()
            slug = raw_slug or slugify(row.get("SKU") or row.get("Name") or "")
            if not slug or slug in seen_slugs:
                continue  # no usable key, or an accidental duplicate row
            seen_slugs.add(slug)
            if slug in base_by_slug:
                merged.append(merge_row_into_product(base_by_slug[slug], row))
                matched_count += 1
            else:
                merged.append(build_new_product_from_row(row, slug))
                new_count += 1

        dropped = [s for s in base_by_slug if s not in seen_slugs]
        live_count = sum(1 for p in merged if not p["needsData"])
        incomplete_live = [
            p for p in merged
            if not p["needsData"] and (not p.get("images") or p.get("price", {}).get("current") is None)
        ]
        print(f"Obs Alpha has {len(rows)} rows -> {matched_count} matched an existing catalog SKU, "
              f"{new_count} are new SKUs added directly in the sheet.")
        print(f"{len(dropped)} previously-scraped SKUs are no longer present in Obs Alpha and will not appear on the site.")
        print(f"{live_count} products will show as Live on the site.")
        if incomplete_live:
            print(f"WARNING: {len(incomplete_live)} Live product(s) are missing a price and/or image and will show placeholders: "
                  + ", ".join(p["sku"] for p in incomplete_live[:20]))

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
