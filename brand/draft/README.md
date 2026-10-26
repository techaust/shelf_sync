# brand/draft: the P3.2 logo generator (temporary)

The ShelfSync symbol, wordmark and lockups as numbers, and the script that draws everything from them. Nothing it writes is edited by hand. **P3.3 replaces this folder** with the real `brand/` pipeline on ShelfSync's own dev libraries.

## Rebuild everything (one command)

From the project folder:

```
node brand/draft/build.mjs
```

It writes 21 SVGs, `index.html` (the review board) and `measurements.json` to `docs/05-design-system-appendix/p3.2-logo-refine/`, prints the key numbers, and exits with an error if a rule breaks: an edge off the pixel grid at 16, 20, 24, 32, 48 or 64 px, a cut that isn't 45° "/" (channel or f crossbar), horizontals not about 8 % thinner, a counter opening or spur under 2 px, verdigris not the smaller part, fewer than 2 clear channel pixels at 16 px, the white-area method drifting from TecHaust's published values, or a re-spaced pair coming too close. It takes about 5 seconds on Node 24.

## Files

| File | What it does |
|---|---|
| `geometry.mjs` | **The one place for numbers:** mark strokes, spine, spur, the pixel-fit rule, the three colour-split variants and the recommended one, wordmark axes, tracking and pair kerns, the white-area settings, lockup and endorsement layout, minimums |
| `outline.mjs` | Outlines text with HarfBuzz (as TecHaust's `outline.ts`). For P3.2 only it imports HarfBuzz, fontverter and the Archivo / IBM Plex Mono files from `techaust_platform`'s `node_modules`. It reads and runs them and never writes there (owner decision, docs/11, 2026-10-26) |
| `wordmark.mjs` | The "ShelfSync" wordmark with the f-crossbar cut and pair kerns, plus the "BY TECHAUST" endorsement |
| `raster.mjs` | Pure geometry: path to polygons, exact areas, supersampled pixel coverage, glyph extremes per scanline |
| `measure.mjs` | Every reported number: verdigris shares, contrast and ΔE2000, the pixel-fit check, the dark split at 16 px, the not-a-5 pixel count, the white area per letter pair (with the check against TecHaust's own published values) |
| `svg.mjs` | The standalone SVGs: symbol (vector and 16/32/48/64 px), the variants, and four lockups in three colour versions |
| `board.mjs` | The review board `index.html` |
| `build.mjs` | Runs it all and checks the rules |
| `p3.1/` | The P3.1 concept generator, copied unchanged from the session scratchpad for the record. It is not part of the P3.2 build |

Colours come from TecHaust's Patina tokens (`packages/ui/tokens/tokens.json`, read-only), copied once into `measure.mjs` as `PALETTE` and written into every SVG and the board as commented custom properties.
