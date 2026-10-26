# P3.5 screenshots of the P3.4 mockup

Pictures of the P3.4 mockup (`../mockup/`), taken on 2026-10-26 and retaken the same day after the eight P3.5 fixes (see [runs/p3.5-screenshots.md](../../runs/p3.5-screenshots.md) §4, "Fixes and retake"). **All data in them is sample data** (each page carries a dashed "Sample data" tag).

## Method

- **2× capture, full page.** Every PNG was made in the built-in browser pane at a 1440 × 900 viewport by the capture helper in `capture/capture.js`:
  - It clones the rendered page with its live form state.
  - It inlines every stylesheet with the Archivo and IBM Plex Mono fonts as data URLs, plus the Lucide icon sprite and the logo.
  - It draws the clone through an SVG `foreignObject` onto a canvas at scale 2, and posts the PNG to `capture/receiver.py`.
  - The receiver is bound to 127.0.0.1 only and run with `python -I`. It accepts names matching `[a-z0-9-]+.png` and bodies up to 20 MB.
- **Width:** 2880 px is the 1440 px layout at 2×. The height is the page's full height at 2×.
- **Full page:** the page is laid out the way a full-page capture normally is, as if the window were as tall as the page. That has these visible effects:
  - The side nav's catalog count sits at the foot of the full page.
  - Review's queue shows all 10 items instead of scrolling.
  - Review's action bar sits at the end of the card, not stuck to the bottom of the window.
  - Scroll areas inside cards stay as they are at 1440 × 900, with their scrollbars. This affects the Catalog table, which shows rows 1–18.
- **Overlays:** `x11` (help panel) and `x12` (ConfirmDialog) are 1440 × 900 viewport shots at 2× (2880 × 1800), because a modal belongs to the window, not the page.
- **Fidelity test:**
  - `fidelity-side-by-side-dashboard-light.png` sets the helper's Dashboard (light) beside the pane's own capture of the same state. The helper image is on the left, scaled to the pane capture's 800 px width.
  - `fidelity-helper-dashboard-light.png` is the helper capture used in the test. It was the same capture as the first-pass `01-dashboard-light.png`; the retaken `01` differs (fixes applied, no mock bar).
- **Mockup controls:** the owner's set leaves out the dashed "Mockup controls" bar, which belongs to the mockup page, not the app. The helper hides it on the live page only while it measures and clones, removes it from the clone, then puts it back; the mockup's files aren't touched. Each shot's state is recorded in the tables below instead (the "State" column is the hash the shot was taken on).
- **Fidelity images:** the two `fidelity-*` files are from the first P3.5 pass and are kept as they were. **They include the mock bar** and show the Dashboard before the fixes.
- **States:** see the State column in each table.

## Main shots (8 screens × light and dark)

All main shots use: Normal state, trust ramp 37 / 50, teaching off, brake off, Low disk off, no open popover. The hash is `#/<route>?theme=<theme>` with `state=normal&ramp=ramp&teach=off&brake=0&disk=no`.

| File | Shows | State | Theme | Pixels |
|---|---|---|---|---|
| `01-dashboard-light.png` | Dashboard | `#/dashboard` | light | 2880 × 2738 |
| `01-dashboard-dark.png` | Dashboard | `#/dashboard` | dark | 2880 × 2738 |
| `02-upload-light.png` | Upload, a batch of 12 rows | `#/upload` | light | 2880 × 3548 |
| `02-upload-dark.png` | Upload, a batch of 12 rows | `#/upload` | dark | 2880 × 3548 |
| `03-review-light.png` | Review, with the held downgrade item (`copperline-4.9.3.zip`) selected | `#/review` | light | 2880 × 3220 |
| `03-review-dark.png` | Review, with the held downgrade item selected | `#/review` | dark | 2880 × 3220 |
| `04-catalog-light.png` | Catalog | `#/catalog` | light | 2880 × 2192 |
| `04-catalog-dark.png` | Catalog | `#/catalog` | dark | 2880 × 2192 |
| `05-product-light.png` | Product: Copperline | `#/product?id=copperline` | light | 2880 × 2694 |
| `05-product-dark.png` | Product: Copperline | `#/product?id=copperline` | dark | 2880 × 2694 |
| `06-cleanup-light.png` | Cleanup | `#/cleanup` | light | 2880 × 3462 |
| `06-cleanup-dark.png` | Cleanup | `#/cleanup` | dark | 2880 × 3462 |
| `07-activity-light.png` | Activity, last 7 days | `#/activity` | light | 2880 × 3652 |
| `07-activity-dark.png` | Activity, last 7 days | `#/activity` | dark | 2880 × 3652 |
| `08-settings-light.png` | Settings › Stores | `#/settings/stores` | light | 2880 × 2974 |
| `08-settings-dark.png` | Settings › Stores | `#/settings/stores` | dark | 2880 × 2974 |

## Extras

Same defaults as the main shots unless the State column says otherwise.

| File | Shows | State | Theme | Pixels |
|---|---|---|---|---|
| `x01-wizard-step1-light.png` | First-run wizard, step 1 (Stores) | `#/wizard?step=1`, Normal | light | 2880 × 2196 |
| `x02-wizard-err02-dark.png` | ERR-02, Test-step variant: "PluginWay returned no downloadable products.", Continue disabled | `#/wizard?step=3`, Error | dark | 2880 × 1924 |
| `x03-wizard-teach-light.png` | Wizard step 6 (Teach) | `#/wizard?step=6`, Normal | light | 2880 × 1800 |
| `x04-review-empty-dark.png` | Review, empty ("Nothing waiting…", Open Upload) | `#/review`, Empty | dark | 2880 × 1800 |
| `x05-cleanup-empty-light.png` | Cleanup, empty ("No issues…", last check, Sync now) | `#/cleanup`, Empty | light | 2880 × 1800 |
| `x06-activity-empty-dark.png` | Activity, empty ("Nothing changed yet…", Upload a ZIP) | `#/activity`, Empty | dark | 2880 × 1800 |
| `x07-catalog-no-stores-light.png` | Catalog with no stores yet ("Add your first store to start."); the app bar shows only the S3 chip | `#/catalog`, Empty | light | 2880 × 1800 |
| `x08-dashboard-err01-dark.png` | ERR-01: PluginWay can't be reached (Connections card, PW health chip) | `#/dashboard`, Error | dark | 2880 × 3080 |
| `x09-settings-storage-err03-light.png` | ERR-03: S3 refused access (Settings › Storage, S3 health chip) | `#/settings/storage`, Error | light | 2880 × 2740 |
| `x10-upload-err04-low-disk-dark.png` | ERR-04: low-disk banner ("Only 1.4 GB free on drive C.") and paused drop zone | `#/upload`, Normal, Low disk on (`disk=low`) | dark | 2880 × 3642 |
| `x11-review-help-panel-light.png` | Help panel open on Review (viewport only) | `#/review`, Normal, help panel open | light | 2880 × 1800 |
| `x12-review-confirm-apply-anyway-dark.png` | ConfirmDialog: Apply anyway on Review (viewport only) | `#/review`, Normal, dialog open | dark | 2880 × 1800 |
| `x13-wizard-err02-stores-light.png` | ERR-02, Stores-step variant: "PluginWay runs WooCommerce 5.6. ShelfSync needs 5.8 or newer.", Continue disabled | `#/wizard?step=1`, Error | light | 2880 × 2498 |
| `x13-wizard-err02-stores-dark.png` | ERR-02, Stores-step variant, as above | `#/wizard?step=1`, Error | dark | 2880 × 2498 |

## Fidelity record (first pass, with the mock bar)

| File | Shows | Theme | Pixels |
|---|---|---|---|
| `fidelity-helper-dashboard-light.png` | The helper's capture used in the fidelity test (before the fixes, mock bar included) | light | 2880 × 2834 |
| `fidelity-side-by-side-dashboard-light.png` | The helper (left, scaled down) beside the pane's own capture (right), both with the mock bar | light | 1610 × 505 |

## Re-taking a shot

1. Start the `design-appendix` preview.
2. Start the receiver from `capture/`. This is the one command:
   `python -I receiver.py 8766`
3. Open `http://127.0.0.1:8765/mockup/` in the browser pane, at a 1440 × 900 viewport.
4. Load `/screenshots/capture/capture.js` into the page.
5. Set the hash. For example:
   `#/review?state=normal&theme=light&ramp=ramp&teach=off&brake=0&disk=no`
6. Run `await SSCapture.shot({ name: "03-review-light.png" })`. Add `mode: "viewport"` for an open dialog, and `keepBar: true` to keep the mock bar.
7. Stop both servers afterwards.
