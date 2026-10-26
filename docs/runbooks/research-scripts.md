# Runbook: the read-only store research scripts

Four small scripts in `tools/research/`, used for the audit ([01-A](../01-audit-appendix/A-store-data-checks.md)).
- **They only read:** every request is a GET.
- **They borrow OmniSync's store settings** by importing `omnisync.config` read-only, so they run with OmniSync's own Python (its `venv` folder), which has `requests` and the keys configured.
- **`-B` stops Python from writing cache files** into OmniSync's folder. Nothing in OmniSync is changed: the config module only reads its settings and the Windows keyring when imported (checked 2026-10-25).

Run them only when the owner asks for a fresh count. The numbers will differ a little from 01-A as the stores change; the newest run wins.

## 1. Open PowerShell
Click **Start**, type **PowerShell**, and click **Windows PowerShell**.

## 2. Count products across both stores
Paste this one command and press **Enter**:

```powershell
& "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync\venv\Scripts\python.exe" -B "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync\tools\research\slug_overlap.py" "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync"
```

**Takes** about a minute (about 25 pages per store, spaced 0.15 s apart). **Prints:**
- the UTC time
- per store: the product count (and a warning if it doesn't match the store's own total), counts per status, products with a SKU, products with more than one download, slugs repeated within the store
- across stores: slugs on both, slugs on one store only, same slug with different titles, near-miss candidates

## 3. Look up one slug
Replace `jupiterx-website-builder-for-wordpress-woocommerce` with the slug you want:

```powershell
& "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync\venv\Scripts\python.exe" -B "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync\tools\research\lookup_slug.py" "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync" jupiterx-website-builder-for-wordpress-woocommerce
```

It prints, for each store, the HTTP status and each matching product's ID, status, name and link. (This is the product's **URL slug**; ShelfSync's canonical slug starts the same and can be shortened, e.g. `jupiterx`.)

## 3a. Variations and link forms
```powershell
& "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync\venv\Scripts\python.exe" -B "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync\tools\research\downloads_check.py" "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync"
```
Prints, per store, products by type, the forms download links take (never the links themselves), and any downloadable variations. Takes about a minute.

## 3b. WooCommerce version
```powershell
& "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync\venv\Scripts\python.exe" -B "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync\tools\research\wc_version.py" "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync"
```
One GET per store; prints only the WooCommerce and WordPress versions.

## 4. If something goes wrong
- **`HTTP 401` or `403`** (with the start of the store's reply after it): the store refused the key, or Cloudflare blocked the request. **Stop.** Nothing was written. Send the last line of the output.
- **`not JSON`:** usually a Cloudflare challenge page. Wait a few minutes and try once more; if it repeats, send the last line.
- **A Python traceback:** stop and send its last line.

