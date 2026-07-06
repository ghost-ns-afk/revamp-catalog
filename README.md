# Revamp Catalog

Static interior-design liquidation catalog, publicly viewable, auto-synced once a day from the Obs Alpha Google Sheet.

## What's in here

- `index.html` — the live public page (already built with the current catalog snapshot).
- `build/index_template.html` — the page source. Edit this, never `index.html` directly.
- `build/products_base.json` — static base data (images, specs, dimensions) scraped once from the source site.
- `build/build_sync.py` — pulls fresh price/stock/MOQ/discount data from Obs Alpha and regenerates `index.html`.
- `.github/workflows/daily-sync.yml` — runs `build_sync.py` automatically every day at 8:00 AM IST.

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

From then on, it runs automatically every morning at 8:00 AM IST — no further action needed. Whenever Obs Alpha's Products tab changes, the site catches up the next morning.

## Security notes

- The service account key only ever lives in GitHub's encrypted Actions secrets store and inside the Action's runner — it is never written into `index.html` or any file a visitor can see.
- The key currently in use (`friday@cogs-499812.iam.gserviceaccount.com`) was originally issued for a different internal project. It works fine here since it already has read access to Obs Alpha, but it's worth asking IT for a dedicated key scoped to just this sheet if you want tighter separation.
- Ordering/enquiries happen entirely over WhatsApp (click-to-chat links generated client-side) — no order data is written back to any Google resource automatically. Your team manages orders manually from WhatsApp.
