# 01: Audit (why OmniSync is being replaced)

| | |
|---|---|
| **Phase** | 1, Diagnosis and plan (**APPROVED** 2026-10-25 as part of plan Draft 3); evidence added 2026-10-25 after the independent review |
| **Date** | 2026-10-25 |
| **Evidence** | [A: store data checks](01-audit-appendix/A-store-data-checks.md) · [B: OmniSync code and log, with file:line](01-audit-appendix/B-omnisync-evidence.md) |
| **Feeds** | [02 plan](02-plan.md), [03 PRD](03-prd.md) |

> OmniSync (`D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync`) stays as it is and keeps running until ShelfSync passes M7 ([08](08-roadmap.md)). It is reference only: ShelfSync never modifies it or runs its pipeline, and ships none of its code.

## 1. What OmniSync does today
OmniSync takes vendor ZIPs (WordPress themes and plugins), works out which product each belongs to, uploads one file to S3, and points the download on each WooCommerce store (GPLFamily and PluginWay) at it. Unclear cases are settled by editing two JSON files by hand: `data/product-slug-overrides.json` (28 entries) and `data/slug-aliases.json` (14 entries).

## 2. The four problems, their causes, and the fix

| # | Problem (owner) | Cause in OmniSync (evidence in [01-B](01-audit-appendix/B-omnisync-evidence.md)) | How ShelfSync fixes it |
|---|---|---|---|
| P1 | Mappings are unpredictable and wrong | Each store's mapping key is made from the file **currently attached** (`mappings.py:310–337`). Jupiter X carried `js-composer-theme-7.9.zip`, so it was keyed `js-composer-theme`. When two products produce the same key, the later one is **dropped with only a log warning** (`mappings.py:341–347`; log lines 201–202 and 230–231: `layerslider`, `woocommerce-bulk-variations`, both stores). Nothing links a product to its twin on the other store. | A **catalog**: each product has a stable identity and is linked to its twin on every store. Attached files are checked against the product, never used to define it ([02 §2](02-plan.md)). |
| P2 | Wrong files go to wrong products | `business-lounge…theme-v2.4.zip` uploaded `js-composer-9.0.1.zip`, the **bundled** plugin, to both stores and deleted the previous file (log lines 4275–4307). 42 hand-written overrides and aliases are string guesses that go live at once; two point at a key that no longer exists (`gutenkit-blocks-addon`). Editions (pro, free, addon) aren't treated as different products. | The **main-item rule**, scored matching with reasons on screen, a matcher **calibrated on the real files**, and checks before and after every store write ([02 §4–6](02-plan.md)). |
| P3 | Needs an AI in the loop | Unclear cases go to `unmatched.log` and are settled by hand-editing the JSON files; on 2026-10-25 that was done in chat from the owner's "ZIP + URL" messages. | A **Review queue**: pick a candidate or paste the product URL, one click each or in bulk; every decision is remembered ([03 UI-REV](03-prd.md)). |
| P4 | Version and downgrade surprises | Downgrades go live with only a warning, and the newer file is then deleted: Creote 4.3.0 → 3.0.4 on both stores, after which `creote-4.3.0.zip` was deleted (log 4276–4293); GutenKit went 2.4.5 → 2.3.12 → 2.3.11 (log 3494–3516); two more (log 3546–3583). For Jupiter X, the "7.9 → 4.62" warning was really a wrong product, not a downgrade. | Downgrades, unreadable or conflicting versions, a version family jump, or the same version with different content are **always held** ([03 MAT-08](03-prd.md)); the previous file is never deleted before every store succeeds ([03 APL-07](03-prd.md)). |

## 3. Known bad cases (they become permanent tests)
| Case | What went wrong | The correct outcome |
|---|---|---|
| Business Lounge theme package | The package's bundled WPBakery (`js-composer-9.0.1`) was uploaded and set on the stand-alone **WPBakery** product on both stores (a different product from the theme), and WPBakery's previous file was deleted | The theme is the main item; WPBakery is marked bundled and ignored |
| Elementor vs Elementor Pro | Edition words not treated as different products | Edition differs → never auto, a penalty, and Review |
| Jupiter X / js-composer-theme | Product keyed from a wrong attached file; stale `latest_version_js-composer-theme` meta | Identity from the catalog; Cleanup flags the file and the stale meta |
| Creote 4.3.0 → 3.0.4 | A downgrade went live and the newer file was deleted | Held: downgrade; nothing deleted |
| GutenKit | Repeated downgrades; aliases to a dead key | Held: downgrade; no aliases, fingerprint match or Review |
| UDesign | `UDesign 4.15.8.zip`'s theme folder `u-design` didn't match OmniSync's key `udesign`, so a **last-resort filename guess** chose the product; it went live on both stores with no review, and the previous file `udesign.zip` (no version in its name) was **deleted**, so it couldn't be rolled back ([01-B](01-audit-appendix/B-omnisync-evidence.md)). The owner isn't sure this is the case they remembered | Matching uses the theme header, never a filename guess, for Certain; a folder slug that differs from the product slug can't be Certain from the name alone; the previous file is always kept (APL-07). The fixture test is written from this log; the owner can still add details before M4 |

## 4. Facts measured on the live stores (read-only)
Full numbers, how each was obtained, and what still needs re-measuring are in [01-A](01-audit-appendix/A-store-data-checks.md).
- **2398** products returned by WooCommerce's `downloadable=true` filter on each store; **2395** share the same URL slug on both stores.
- **3** near-miss pairs (same title, slightly different slug).
- **No product has a SKU.**
- **2 products per store** have more than one download.
- The S3 bucket held **2398 objects (12.5 GiB)**. How those relate to the extra downloads is re-measured before M4 ([01-A §4](01-audit-appendix/A-store-data-checks.md)).
