# brand: the ShelfSync brand pipeline

Every logo, icon and installer image, and the design tokens' CSS, are generated here from numbers. Nothing in `assets/` or `generated/` is edited by hand: change `geometry.mjs` (or take a new `tokens.json` from TecHaust) in a reviewed commit, rebuild, and the tests prove the result. Rules: [docs/05-design-system.md](../docs/05-design-system.md) §1.4; the audit: [docs/14-brand-audit.md](../docs/14-brand-audit.md).

## Commands (in this folder, Node 24)

| What | Command |
|---|---|
| Install the five pinned dev packages from the lockfile | `npm ci` |
| Rebuild everything (about 1 second) | `npm run build` |
| Run the tests | `npm test` |

From the project folder, as the project runs heavy commands (logs in `.logs/`):

```
bash tools/heavy.sh --log brand-test npm --prefix brand test
```

`npm run build` writes `assets/`, `generated/` and the review page in `docs/05-design-system-appendix/p3.3-brand-assets/`, and removes any file there it no longer makes. `npm test` rebuilds everything in memory and compares it with the files on disk, so a hand edit is always caught. Files without zlib (SVG, CSS, JSON, HTML, BMP, fonts, each ICO's directory and its 32-bit bitmap frames, masks included) must match byte for byte. PNGs and PNG frames inside ICOs are compared by their decoded pixels, size, colour type and chunk order, because zlib's bytes can change between Node versions while the image stays the same.

## What is where

| Path | What |
|---|---|
| `geometry.mjs` | **The one place for numbers:** the mark, the pixel-fit rule, the wordmark edits, every lockup, the colour versions, the icon, tray, installer and GitHub layouts, and the file-size limits |
| `tokens.json` | TecHaust's Patina tokens, copied unchanged (source commit, file hash and date recorded inside) |
| `lib/outline.mjs`, `lib/wordmark.mjs` | Text to outlines with HarfBuzz (Archivo, IBM Plex Mono from Fontsource); the f-crossbar cut |
| `lib/lockups.mjs` | Lockup layouts and the SVG files |
| `lib/raster.mjs`, `lib/render.mjs` | Path flattening and an exact-area scanline rasterizer (no sharp) |
| `lib/formats.mjs` | PNG, ICO and BMP writers and readers on Node's `zlib` |
| `lib/icons.mjs`, `lib/art.mjs` | App icon, favicon and tray frames; installer art and GitHub images |
| `lib/tokens.mjs` | The token model, contrast maths and `tokens.css` |
| `lib/measure.mjs` | Every reported number, including every contrast pair stated in 05 and 14 |
| `lib/plan.mjs`, `lib/review.mjs` | The list of generated files; the review page |
| `scripts/build.mjs` | `npm run build` |
| `test/` | vitest: geometry, pixel fit, colour and contrast, file structure and sizes, drift |
| `assets/logo/` | `logo-<lockup>-<version>.svg`: primary, symbol, wordmark, endorsed, stacked, compact × color, dark, ink, white, black |
| `assets/favicon/` | `favicon.svg` (16 px grid, dark-mode colours), `favicon.ico` (16, 32, 48) |
| `assets/app/shelfsync.ico` | 16, 20, 24, 32, 48, 64, 96, 128, 256 px |
| `assets/tray/` | `tray-<normal\|paused\|attention>-<light\|dark>.ico` (16, 20, 24, 32 px; "light" means for a light taskbar) |
| `assets/installer/` | NSIS Modern UI images: `installer-panel.bmp` (164 × 314), `installer-header.bmp` (150 × 57), and PNG previews |
| `assets/github/` | `social-preview.png` (1280 × 640), `readme-header-light.png` and `-dark.png` (1280 × 320, for a 640 px display) |
| `generated/tokens.css` | CSS custom properties, light and dark, from `tokens.json` |
| `generated/measurements.json` | Every measured number, for the review page and the audit |
| `draft/` | The P3.2 generator, kept until the owner approves P3.3 |

## Packages

Dev-only, exact versions, locked in `package-lock.json` (owner's decision, docs/11, 2026-10-26): harfbuzzjs 1.6.2, fontverter 2.0.0, @fontsource-variable/archivo 5.3.0, @fontsource/ibm-plex-mono 5.3.0, vitest 4.1.12 (moved from 4.1.11 for two `npm audit` advisories, owner, 2026-10-26). `.npmrc` turns install scripts off. Nothing is imported from techaust_platform.

## README header on GitHub

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="brand/assets/github/readme-header-dark.png">
  <img src="brand/assets/github/readme-header-light.png" width="640" alt="ShelfSync by TecHaust">
</picture>
```
