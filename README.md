# Revamp Catalog

Static interior-design liquidation catalog, publicly viewable, synced from the Obs Alpha Google Sheet once a day automatically — plus on demand whenever you need it.

## What's in here

- `index.html` — the live public page (already built with the current catalog snapshot).
- `build/index_template.html` — the page source. Edit this, never `index.html` directly.
- `build/products_base.json` — static base data (images, specs, dimensions) scraped once from the source site.
- `build/build_sync.py` — pulls fresh price/stock/MOQ/discount/inventory/LiveStatus data from Obs Alpha and regenerates `index.html`. Every sync re-reads the whole Products tab, so any field you change gets picked up, not just inventory.
- `.github/workflows/daily-sync.yml` — runs `build_sync.py` automatically every day at 8:00 AM IST, and can also be triggered manually (see below).
- `ObsAlpha_PushButton.gs.txt` (in your Apps Script project, not this repo) — adds a "Revamp Catalog → 🔄 Push update now" menu to the Obs Alpha sheet so you can force an immediate sync without opening GitHub.

## One-time setup (~5 minutes)

1. **Create the repo.** On GitHub, create a new **public** repository (e.g. `revamp-catalog`) under your account `ghost-ns-afk`.
2. **Upload these files**, keeping the folder structure exactly as-is (`index.html` at the root, `build/` and `.github/` as subfolders). Easiest way: on the repo's main page, click "Add file" → "Upload files", then drag the whole unzipped folder in, or use `git`:
   ```
   git clone https://github.com/ghost-ns-afk/revamp-catalog.git
   cd revamp-catalog
   # copy all files from this package in here
   git add .
   git commit -m "Initial catalog"
   git push
   ```
3. **Add the service account key as a secret.** Go to Settings → Secrets and variables → Actions → "New repository secret".
   - Name: `GOOGLE_SERVICE_ACCOUNT_KEY`
   - Value: paste the **entire contents** of your `friday-gsheets-key.json` file (the whole JSON, including the `{ }`).
4. **Enable GitHub Pages.** Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder `/ (root)` → Save. GitHub will give you a URL like `https://ghost-ns-afk.github.io/revamp-catalog/` — that's your public catalog link.
5. **Enable Actions** if prompted (Settings → Actions → General → allow workflows to run).
6. **Test the sync manually**: go to the "Actions" tab → "Daily catalog sync" → "Run workflow" → Run. After it finishes (~30 seconds), check that `index.html` in the repo shows a new commit and the Pages site reflects the latest sheet data.

From then on, it runs automatically every morning at 8:00 AM IST — no further action needed for routine inventory updates.

## Pushing updates immediately (price/MOQ/discount changes, etc.)

You don't have to wait for the daily 8 AM run. Two ways to force an immediate sync:

- **From GitHub directly**: Actions tab → "Daily catalog sync" → "Run workflow" → Run. Works any time, no extra setup (it's already enabled).
- **From the Obs Alpha sheet itself (recommended for day-to-day use)**: paste `ObsAlpha_PushButton.gs.txt` into the sheet's Apps Script project (Extensions → Apps Script), do the one-time GitHub token setup described in that file's header comment, and you'll get a "Revamp Catalog" menu on the sheet with a "🔄 Push update now" button — one click, no GitHub login needed.

Either way, the sync always re-reads the entire Products tab, so it picks up any dynamic field you've changed — price, MOQ, discount, stock status, or LiveStatus — not just inventory.

## Editing the catalog — everything lives in Obs Alpha

There is no admin panel or edit mode on the site anymore — it's a pure read-only catalog. To change anything visitors see, edit the sheet directly:

**Products tab** (per-SKU data), key columns:
- `Price` — current selling price
- `OriginalPrice` — struck-through "was" price
- `DiscountPct` — badge % shown on the card
- `InventoryQty` — units available ("Qty available" on the site), shown under the price. Pricing and quantities are per unit (per piece) across all categories — there's no separate sq.ft basis anymore.
- `MOQ` — minimum order quantity
- `StockStatus` — `in_stock`, `low_stock`, or `out_of_stock`
- `LiveStatus` — set to anything other than `Live` (e.g. `Hidden`) to pull a SKU off the public site entirely; it will not appear or be reachable by any visitor, only reappearing once you set it back to `Live`

**OrderDiscounts tab** (new) — automatic discount based on total cart value, independent of any single SKU:
- `MinOrderValue` — cart subtotal threshold (₹)
- `DiscountPct` — extra % off applied automatically once the customer's cart reaches that value
- `Label` — optional description shown to the customer (e.g. "Orders above ₹40,000")

Add as many rows/tiers as you like; the highest threshold the cart qualifies for is applied automatically, both in the cart drawer, the quote form summary, and the WhatsApp enquiry message. Starter tiers are already seeded (₹15,000/3%, ₹40,000/6%, ₹1,00,000/10%) — edit the values to whatever you actually want to offer.

All of this updates on the live site once a day automatically (8 AM IST), or immediately via "Run workflow" on GitHub or the sheet's "Push update now" button (see above) — same mechanism either way, since every sync re-reads both tabs in full.

## Security notes

- The service account key only ever lives in GitHub's encrypted Actions secrets store and inside the Action's runner — it is never written into `index.html` or any file a visitor can see.
- The key currently in use (`friday@cogs-499812.iam.gserviceaccount.com`) was originally issued for a different internal project. It works fine here since it already has read access to Obs Alpha, but it's worth asking IT for a dedicated key scoped to just this sheet if you want tighter separation.
- Ordering/enquiries happen entirely over WhatsApp (click-to-chat links generated client-side) — no order data is written back to any Google resource automatically. Your team manages orders manually from WhatsApp.
