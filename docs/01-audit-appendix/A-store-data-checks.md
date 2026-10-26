# 01-A: Store data checks (read-only, 2026-10-25)

Measured on the live stores and bucket with read-only calls on 2026-10-25, during the research session before the plan was approved. Nothing was written. This page says, for each number, **how it was obtained** and whether the kept scripts reproduce it.

## 1. Product linking by URL slug

| Measure | GPLFamily | PluginWay | How obtained | Reproduced by `tools/research/` |
|---|---|---|---|---|
| Products returned by `downloadable=true` (WooCommerce default `status=any`: publish, draft, pending, private; trash excluded) | 2398 | 2398 | `slug_overlap.py` (first version) | Yes. The improved script also prints counts per status and checks the total against `X-WP-Total` |
| Same slug on both stores | 2395 | 2395 | `slug_overlap.py` | Yes |
| Slug repeated within one store | 0 | 0 | `slug_overlap.py` (first version) | Yes: re-measured with the improved script, which tests each store on its own (2026-10-25, 15:43 UTC) |
| Products with a SKU | 0 | 0 | `slug_overlap.py` | Yes |
| Products with more than one download | 2 | 2 | The research session's product reads (method not recorded) | Yes: the improved script reads `downloads` and prints this count |

**Re-measured 2026-10-25, 15:43 UTC (21:13 IST)** with the improved scripts, owner's go-ahead: identical results. Each store: 2398 downloadable products (matching `X-WP-Total`), all `publish`, 0 with a SKU, 0 slugs repeated within the store, 2 with more than one download (GPLFamily 1694 and 436, PluginWay 1821 and 427), 0 without a download; 2395 slugs on both; the same 3 near-miss pairs (§2) found automatically; 1 shared slug with a different title. Without the `downloadable` filter each store has 2402 products and **0 in trash**, **all `simple`** (no variable products, so no variations, 04-A V30), and all 2400 download links are the `[amazon_s3 ...]` shortcode. Before M3 the catalog build re-reads everything anyway.

**Versions (read 2026-10-25, 15:50 UTC):** both stores run **WooCommerce 11.2.1** on WordPress 7.1.3 (`tools/research/wc_version.py`), well above the 5.8 minimum ([04-A V2](../04-architecture-appendix/A-stack-verification.md)). The first-run catalog check in M3 (CAT-01, ERR-02) records it again.

## 2. The three near-miss pairs
Same title on both stores; slugs differ slightly. Found from the slugs that exist on one store only (3 on each side), compared by hand. The improved script prints candidates automatically (slug edit distance ≤ 2 or a WordPress `-N` suffix, plus the same normalised title). ShelfSync offers these as one-click suggestions and never links them silently ([03 CAT-03](../03-prd.md)).

| GPLFamily slug | PluginWay slug | Difference |
|---|---|---|
| `jetformbuilder-mailpoet-action-add-on` | `jetformbuilder-mailpoet-action-addon` | one hyphen |
| `openpos-woocommerce-point-of-salepos-82-addons` | `openpos-woocommerce-point-of-salepos82-addons` | one hyphen |
| `css-igniter-lense-wordpress-theme` | `css-igniter-lense-wordpress-theme-2` | WordPress's `-2` suffix |

## 3. A known product, as an example
JupiterX – Website Builder: GPLFamily product **1294**, PluginWay product **1373**. Its URL slug on both stores is `jupiterx-website-builder-for-wordpress-woocommerce`. Its attached file was `js-composer-theme-7.9.zip`, and it still carries the stale meta key `latest_version_js-composer-theme`. In the plan, its canonical slug is shortened by the owner to `jupiterx` (the canonical slug starts as the URL slug, [02 §2](../02-plan.md)).

## 4. The S3 corpus
- **2398 objects, 12.5 GiB** in the bucket, read by the research session through the AWS connection (method not recorded).
- **Open:** that equals the product count, yet 2 products per store have a second download. Either the extra downloads live outside the bucket, or some objects aren't attached to any product. The calibration preparation in M4 lists the bucket read-only (with the owner's go-ahead) and maps every object to a slot, or marks it "unattached".
- **Cost estimate for calibration** (range reads of each ZIP's central directory and header files): **about 1 GiB of downloads, an estimate.** Vendor packages that hold an inner theme ZIP stored compressed must be downloaded whole to read the inner header, which could raise it to a few GiB. Either way, downloads stay inside AWS's free 100 GB/month. Request charges for about 10–15 thousand GETs come to **under one US cent**, possibly covered by the AWS free tier. That's not strictly $0, so it's flagged here as the owner's rule asks.

## 5. Scripts
| Script | What it prints |
|---|---|
| `tools/research/slug_overlap.py` | Per store: the UTC time, total vs `X-WP-Total`, counts per status, SKU count, products with more than one download, slugs repeated within the store. Across stores: slugs on both, on one store only, same slug with different titles, near-miss candidates |
| `tools/research/lookup_slug.py` | For one slug on each store: the HTTP status and each matching product's ID, status, name and link |
| `tools/research/downloads_check.py` | Per store: products by type, the forms download links take, variable products and their downloadable variations |
| `tools/research/wc_version.py` | Per store: the WooCommerce and WordPress versions only |
