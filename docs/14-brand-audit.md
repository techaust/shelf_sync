# 14: Brand audit, the ShelfSync logo

| | |
|---|---|
| **Phase** | 3, step P3.2 (refine and audit) |
| **Date** | 2026-10-26 |
| **Scope** | The S-cut symbol, the wordmark, the lockups and their generator: `brand/draft/` and `docs/05-design-system-appendix/p3.2-logo-refine/`. The full asset set is P3.3. |
| **Status** | **APPROVED** by the owner 2026-10-26 (the `reviewer` approved it on round 2) |
| **Run file** | [runs/p3.2-logo-refine.md](runs/p3.2-logo-refine.md) (all measurements, with method) |
| **Decisions** | [11](11-decisions.md), 2026-10-26: S-cut chosen; verdigris is the smaller part; f-crossbar cut; the cut always runs "/" |

## 1. How the audit was done
- **Starting point:** P3.1's concept 2, S-cut, which the owner chose over Shelves (reads as an E at 16 px) and One to many (reads as a bar chart) ([runs/p3.1-logo-concepts.md](runs/p3.1-logo-concepts.md)).
- **Method:** the same as TecHaust's brand audit (`techaust_platform` `docs/11-brand-audit.md`). Each aspect is scored out of 10 against what a professional identity studio would deliver. Wherever possible a score rests on a **measurement**:
  - WCAG contrast
  - verdigris share of the inked area
  - optical white area between letter pairs
  - pixel-grid fit at 16/32/48/64 px
  - pixel difference from a look-alike glyph
- **Reproducible:** every number comes from `node brand/draft/build.mjs`. The build checks the construction rules and exits non-zero if any fail. Two runs gave identical files.
- **What a 10 means:** nothing left that a professional would change, within what can be done in code. Where a 10 needs something outside code, the score says what.

## 2. Findings and fixes

### 2.1 Colour share
| Finding | Fix |
|---|---|
| In P3.1, verdigris was 50.5 % of the mark, a second colour rather than an accent. | Three splits were tried: A, the cut piece, at 10.6 %; B, the lower bowl, at 18.6 %; C, the lower terminal, at 26.4 %. **A was chosen.** Verdigris is exactly the piece the channel cuts off, so the one device and the one accent are the same detail, as in TecHaust's mark. At 16 px it is 9.3 %. |

### 2.2 Legibility at 16 px
| Finding | Fix |
|---|---|
| The S could be taken for a 5: at 16 px a square 5 differed from it by only 12 pixels. | Turned terminals (a spur of 9 units, 47 % of a stroke) at both ends. The difference from the 5 is now 20 px at 16 px, and 84 px at 32 px (was 48). |
| On dark, the two halves differ only 1.71:1 (mist against verdigris-300), so the split leaned on the gap: 3 clear pixels (the channel's run is 4). | With variant A, both blocks are mist on dark and are separated only by the pixel-fitted channel. Every spine row keeps 3 clear background pixels, so the shape doesn't depend on colour. The board proves it with the same raster drawn without verdigris. |

### 2.3 Pixel fitting
| Finding | Fix |
|---|---|
| Below 64 px, scaled vectors put edges between pixels. | Fitted at 16, 20, 24, 32, 48 and 64 px (20 and 24 px cover the tray at 125 % and 150 %). At every size all 26 coordinates land on whole pixels and both cuts are 45° "/" (checked by the build). The channel is 94.3–106.1 % of the stroke. |
| With three stacked horizontals in 16 px, TecHaust's rule (horizontal = vertical below 40 px) leaves a 1 px opening next to the spur. | **Exception at 16 px only:** horizontals are 2 px against 3 px stems. This needs the owner's yes (§4). |

### 2.4 Wordmark
| Finding | Fix |
|---|---|
| The wordmark carried no family detail. | The f crossbar takes the one-stroke 45° "/" cut (15.43 across and 15.43 down). |
| Uneven spacing. Measured with TecHaust's white-area method, reconstructed to within 0.4 of TecHaust's four published values. The reference "no" is 20.7. | Sh 22.4 → 21.1, lf 22.4 → 20.4, yn 22.5 → 21.4, fS 24.3 → 24.9, Sy 26.0 → 25.0. fS and Sy stay above the reference on purpose: about 60 % of their scanlines are open counters, as with TecHaust's Te. |

### 2.5 Lockups
| Finding | Fix |
|---|---|
| The primary, symbol, wordmark and endorsed lockups weren't laid out. | Primary: the symbol at 1.28 × the cap height, centred on the caps, with a gap of two strokes. Endorsed: "BY TECHAUST" in IBM Plex Mono caps at 0.3 × cap height, one stroke below the baseline. Each comes on light, on dark and in one colour, with one stroke of clear space. |
| **Open:** 05's 96 px minimum for the primary makes its symbol 12.94 px, under the symbol's own 16 px minimum. | Proposed new minimum: **119 px**. Needs the owner's yes (§4). |
| **Open:** the endorsed lockup needs 266 px for a 12 px endorsement, but the installer's side panel is 164 px wide. | P3.3 designs a stacked endorsed lockup, or a smaller endorsement for the installer. |

### 2.6 Colour and contrast (all on the Patina tokens)
| Pair | Ratio |
|---|---|
| Ink-900 / verdigris-700 on white | 16.28 / 6.34 |
| Ink-900 / verdigris-700 on stone-50 | 15.15 / 5.90 |
| Mist / verdigris-300 on ink-900 | 13.44 / 7.86 |
| Mist / verdigris-300 on ink-950 | 15.19 / 8.89 |
| Taskbar mock, light / dark (accent) | 5.66 / 7.87 |
| One colour (ink on white) | 16.28 |
| The two halves against each other: ink-900 / verdigris-700 on light | **2.57** |
| The two halves against each other: mist / verdigris-300 on dark | **1.71** |

Every mark-on-background pair is above 3:1 for graphics and 4.5:1 for text. The two halves against each other are not, and needn't be: the channel separates them, not colour (§2.2). The cost is that at 16 px on light the accent is only about 12 px at 2.57:1, so it's felt more than seen.

## 3. Scorecard
The lead scored first. The `reviewer` then scored independently: round 1 was SEND BACK; round 2, the re-check of the fixes, was **APPROVE** (findings in [the run file](runs/p3.2-logo-refine.md) §5). The current score is the reviewer's round 2.

| Aspect | Lead | Reviewer R1 | **Reviewer R2** | Reason (now) | What a 10 needs |
|---|---|---|---|---|---|
| Mark construction | 9 | 9 | **9** | Every 05 rule and owner decision passes; the build guards the grid, the channel, both "/" cuts, the f cut and the horizontal ratio | The owner accepts the 16 px horizontal exception |
| Colour logic | 10 | 8 | **8** | Verdigris at 10.6 % is the cut piece, and on dark the shape doesn't depend on colour. At 16 px on light the accent is 11 px at 2.57:1, felt more than seen | The owner's call: accept the trade-off, or use verdigris-500 at 24 px and below (3.93:1), which 05 doesn't allow today |
| Small sizes | 8 | 7 | **8** | Fitted and guarded at 16/20/24/32/48/64 px; reads as an S; the tray mock is now correct | A check on the real Windows 11 taskbar at 1:1 (P3.3 ICO); "not a 5" rests on a pixel count, with no user test |
| Wordmark | 8 | 8 | **8** | f cut added and reads clearly. Sh, lf and yn are within 3.3 % of the reference "no" (yn 21.36 against 20.67); fS and Sy stay about 20 % above it on purpose (open counters) | The spacing method is a reconstruction (agrees within 0.4); a final look at print size |
| Lockups | 7 | 7 | **7** | The primary is balanced, in three colour versions with clear space | The primary minimum (119 px) approved; an installer-sized endorsed lockup (P3.3) |
| Contrast | 10 | 9 | **10** | The mark's pairs pass AA; every text element on both boards passes (lowest 5.90 light, 7.61 dark) | — |
| Reproducibility | 8 | 7 | **7** | One command, deterministic, with guards. After round 2 the plate labels and pair notes are generated too (not re-reviewed; the lead checked the build passes) | Those labels generated; the real pipeline and its tests in `brand/` (P3.3, then CI from M1a); not borrowing TecHaust's installed HarfBuzz |
| Documentation | 7 | 6 | **7** | This audit and the run file, corrected after both rounds | 05 §1.2–1.4 updated once the owner approves |

## 3a. P3.3: the pipeline and assets
The logo's source moved from `brand/draft/` to the real pipeline in `brand/`:
- **Packages:** ShelfSync's own five packages, pinned exactly. No sharp: PNG, ICO and BMP are written by our own code.
- **Tests:** 221 vitest tests, which fail on a hand edit.
- **`npm audit`:** 0.
- **Assets:** every asset in [05 §1.4](05-design-system.md).

**Status: APPROVED** by the owner 2026-10-26. Three review rounds ran (round 1 at Opus high, then two re-checks at medium); the last was APPROVE with nothing open ([runs/p3.3-brand-pipeline.md](runs/p3.3-brand-pipeline.md) §5).

| Aspect (P3.3) | Reviewer, final | Reason | What a 10 needs |
|---|---|---|---|
| Pipeline / reproducibility | 9 | One command, own pinned packages, a drift guard on decoded pixels and ICO bytes | CI from M1a; a pinned Node minor version |
| Tests | 9 | 221, including known-answer byte checks for PNG, BMP and ICO, and the badge clearance at every size | Running in CI (M1a) |
| Tokens | 9.5 | A byte copy of TecHaust's Patina file, with its source; the CSS is generated | The Tailwind theme (M1) |
| Icons (tray, favicon, app) | 9 | Pixel-fitted; badges differ in shape; the 16 px ICO frame has a 14 px fit and an ink rim | Seen in the real Windows tray and File Explorer (M1, with the tray app) |
| Installer art | 8.5 | Stacked and compact endorsed lockups keep "BY TECHAUST" at 12 px | NSIS checked at 150 % and 200 % scaling (M1) |
| GitHub images | 8.5 | Social preview and README header, light and dark | Seen rendered on GitHub (M1a) |
| Review page | 9 | Every asset at real size, light and dark, AA text | — |
| Documentation | 9 | 05, this audit and the run file are corrected | — |

With P3.3, the P3.2 scores that waited on it move: **Lockups 7 → 9** (the installer lockups exist; the minimums are approved) and **Reproducibility 7 → 9** (the real pipeline and tests, no borrowed HarfBuzz). These are the lead's re-scores, based on the P3.3 reviewer's checks.

## 4. Owner actions
Answered 2026-10-26 ([11](11-decisions.md)): variant A; the 16 px exception; a 119 px primary minimum; verdigris-700 at every size.

Still open:
1. Done 2026-10-26: the owner approved the refined logo, and 05 §1.2–1.4 is updated.
2. **Optional, $0:** a trademark search for "ShelfSync" before wide use. TecHaust's audit flags the same for its own name.
