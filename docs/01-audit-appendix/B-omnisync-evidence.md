# 01-B: Evidence from OmniSync (read-only, 2026-10-25)

Read on 2026-10-25 from OmniSync's code and its own log, without running anything and without opening `config.env`. Paths are relative to `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync`. Line numbers are as of that date.

## P1: mappings come from the attached file, and collisions are dropped
- **Key from the attached file:** `omnisync/mappings.py:310` `build_mapping()` reads each product's download entries (`:321`), takes the file name (`:324–325`), and turns it into the mapping key with `_mapping_key_from_base()` (`:326`, defined at `:47–50`: strip `.zip` and the version, then slugify). The product's own URL slug is used only when it has no parsable download (`:334–337`).
- **Collisions dropped:** when a key already maps to another product, the later product is skipped with a warning (`:341–347`, "keeping …").
- **In the log** (`data/omnisync.log`), on both stores:
  - line 201: `'woocommerce-bulk-variations' maps to multiple product IDs (6587 and 3729); keeping 6587.`
  - line 202: `'layerslider' maps to multiple product IDs (8097 and 1690); keeping 8097.`
  - lines 230–231: the same on PluginWay (5569/3394; 6805/1816).
- **No twin link:** each store is mapped separately (`refresh_mapping(store_name)`, `mappings.py:400`); nothing records that GPLFamily 1294 and PluginWay 1373 are the same product.

## P2: wrong files to wrong products
- **The bundled plugin was uploaded** (`data/omnisync.log`):
  - line 4275: `business-lounge---multi-purpose-consulting---finance-theme-v2.4.zip: S3 PUT productrepo/js-composer-9.0.1.zip v9.0.1`
  - lines 4286 and 4306: GPLFamily product 485 and PluginWay product 476 were set to `js-composer-9.0.1.zip`. Both are the **WPBakery** (`js-composer`) products (OmniSync's `stores/gplfamily/mapping.json` and `stores/pluginway/mapping.json`, key `js-composer`, line 13988 in each). So a theme package's **bundled** plugin updated a different product, the stand-alone WPBakery one
  - line 4307: the old object `js-composer-8.7.2.zip` was deleted
- **String guesses go live:** two files steer matching by name. `data/product-slug-overrides.json` holds 28 exact filename → key overrides ("Tier 1", `engine.py:149–180`). `data/slug-aliases.json` holds 14 slug aliases (`engine.py:141–143`). Together that's **42 hand-written entries**, the "~40" in [02 §5](../02-plan.md).
- **An alias to a key that no longer exists:** `slug-aliases.json` maps both `gutenkit-blocks-pro` and `gutenkit-blocks-addon-pro` to `gutenkit-blocks-addon`, and that key appears in neither `stores/gplfamily/mapping.json` nor `stores/pluginway/mapping.json` (checked 2026-10-25).

## P3: an AI in the loop
- Unclear cases end in `data/unmatched.log` and `data/fallback-audit.jsonl`. They are settled by editing the two JSON files above by hand. On 2026-10-25 that was done in a chat session from the owner's "ZIP + URL" messages.

## P4: downgrades went live with only a warning
`data/omnisync.log`:
- lines 4276 and 4285: `product 5436: version 3.0.4 is LOWER than current 4.3.0 (downgrade)` (and 4535 on PluginWay), then lines 4281 and 4292 set both stores to `creote-3.0.4.zip`, and **line 4293 deleted `creote-4.3.0.zip`**, so the newer file could not be rolled back.
- lines 3494–3516: GutenKit (GPLFamily 2326, PluginWay 2449) went **2.4.5 → 2.3.12 → 2.3.11**.
- lines 3546–3583: two more downgrades (5.7.4 → 5.7.3; 3.0.11 → 3.0.4).

## What this does not show
- **Jupiter X:** the "7.9 → 4.62" warning was described in the 2026-10-25 runs. This log doesn't name product 1294, so the evidence is the store data ([01-A §3](A-store-data-checks.md)).
- **UDesign** (`data/omnisync.log` lines 4484, 4505, 4521, 4540, 4542; `data/fallback-audit.jsonl`, 2026-10-25 12:05 UTC; these entries are newer than the first audit, which is why it found none):
  - line 4484: `fallback 'u-design' -> 'udesign' (generic-filename, v4.15.8) via product URL slug`
  - lines 4521 and 4540: GPLFamily product 1351 and PluginWay product 1435 (both OmniSync's `udesign` key, `stores/*/mapping.json` line 11840/11876) set to `udesign-4.15.8.zip`
  - line 4542: the old object `udesign.zip` was deleted
  - The owner isn't sure this is the case they remembered (2026-10-25).
