// ShelfSync brand: every number of the mark, the wordmark, the lockups and every generated asset lives here.
// `npm run build` draws every file in brand/assets/ (and the review page) from this file; nothing is hand-edited.
//
// The mark, wordmark and lockups are carried over unchanged from brand/draft/geometry.mjs (P3.2, approved by the
// owner 2026-10-26, docs/11): the S-cut, variant A (verdigris on the cut piece), the 16 px exception, the f-crossbar
// cut, the cut always "/", verdigris-700 at every size. The only change is MINIMUM.primaryWidth, 96 -> 119 px (owner,
// 2026-10-26). Construction follows TecHaust's packages/ui/src/brand/geometry.ts (read-only reference).
//
// Why .mjs and not .ts: this pipeline has no TypeScript compiler (only the five approved packages), so type
// annotations would never be checked; plain ES modules run as-is on Node 24 and in vitest, with JSDoc for intent.

const r = (n) => Math.round(n * 100) / 100;

// ---------------------------------------------------------------------------------------------------------------
// The mark (unchanged from P3.2)
// ---------------------------------------------------------------------------------------------------------------

/** The vector mark on its 100-unit grid. */
export const MARK = {
  size: 100,
  v: 19, // vertical stroke (stems, spurs)
  h: 17.5, // horizontal stroke (top bar, spine, bottom bar): 7.9 % thinner than v
  cy: 48.5, // centre line of the spine, 1.5 above the geometric centre
  spur: 9, // "not a 5": the top-right and bottom-left terminals turn down / up by this much
};
/** Clear space on every side, and the unit for the lockup gap. */
export const STROKE = MARK.v;

/**
 * Pixel fitting at `px`, TecHaust's pixelMark rule: v = round(0.19 px), at least 2; below 40 px the horizontals
 * equal the verticals, above it h = round(0.175 px); the channel's horizontal run is round(v * sqrt 2) so both cut
 * ends land on whole pixels. Two additions for the S, which stacks three horizontals where TecHaust's TH has two:
 * - the spur is round(0.09 px) but at least 2 px, so it reads as a turned terminal, not a thicker bar end;
 * - if the opening between the spur and the spine would fall under 2 px, the horizontals lose 1 px (16 px only:
 *   the owner's exception, docs/11 2026-10-26).
 */
export const PIXEL = { minSpur: 2, minOpening: 2 };
/** The sizes the mark is fitted and guarded at (05 1.4). 20 and 24: the tray at 125 % and 150 %. */
export const FIT_SIZES = [16, 20, 24, 32, 48, 64];

export function params(px) {
  if (!px) return { ...MARK, ch: MARK.v * Math.SQRT2, q: r, pixel: false };
  const v = Math.max(2, Math.round(px * 0.19));
  const cy = px * 0.485;
  const spur = Math.max(PIXEL.minSpur, Math.round(px * 0.09));
  let h = px < 40 ? v : Math.round(px * 0.175);
  const opening = (hh) => Math.round(cy - hh / 2) - hh - spur;
  if (opening(h) < PIXEL.minOpening) h -= 1;
  return { size: px, v, h, cy, spur, ch: Math.round(v * Math.SQRT2), q: Math.round, pixel: true, thinned: h < (px < 40 ? v : Math.round(px * 0.175)) };
}

/** The S as named pieces. The channel crosses the spine with its centre line on the spine's centre point. */
function frame(p) {
  const { size: S, h, cy, ch, q } = p;
  const y0 = q(cy - h / 2);
  const y1 = r(y0 + h);
  const a = q(S / 2 + cy - ch / 2 - y0); // ink cut: top end of the "/" edge
  const g = r(a + ch); // verdigris cut, one channel further right
  return { S, v: p.v, h, sp: p.spur, y0, y1, a, g, b0: r(S - h) };
}

// Outlines, one closed path per connected piece of one colour (so no seams appear inside a colour).
const top = ({ S, v, h, sp, y0, y1, a }) => `M0 0H${S}V${r(h + sp)}H${r(S - v)}V${h}H${v}V${y0}H${a}L${r(a - h)} ${y1}H0Z`;
const spineEnd = ({ S, y0, y1, g, h }) => `M${g} ${y0}H${S}V${y1}H${r(g - h)}Z`;
const stemBarSpur = ({ S, v, sp, y1, b0 }) => `M${S} ${y1}V${S}H0V${r(b0 - sp)}H${v}V${b0}H${r(S - v)}V${y1}Z`;

/** Variant A, "cut piece" (owner, 2026-10-26): ink is the base; verdigris is only the spine end the channel cuts off. */
export const VARIANT = { id: "a-cut-piece", name: "Cut piece", what: "only the spine end the channel cuts off" };

/** The mark's two paths at `px` (pixel-fitted) or as the 100-unit vector (px omitted). */
export function mark(px) {
  const p = params(px);
  const f = frame(p);
  return { base: top(f) + stemBarSpur(f), accent: spineEnd(f), f, p };
}

// ---------------------------------------------------------------------------------------------------------------
// Wordmark, lockups, endorsement (unchanged from P3.2)
// ---------------------------------------------------------------------------------------------------------------

/** Wordmark: Archivo, TecHaust's settings, outlined with HarfBuzz; bespoke edits as numbers. */
export const WORDMARK = {
  text: "ShelfSync",
  axes: { wght: 620, wdth: 116 },
  cap: 100, // cap height in master units
  tracking: -6, // font units per glyph, as TecHaust's wordmark
  fCut: true, // the f crossbar's right end is cut at 45 degrees, "/", across the full bar height
  /** Extra tightening before glyph i (master units, positive = closer): Sh, lf, fS, Sy, yn (P3.2, docs/14 2.4). */
  pairs: { 1: 2, 4: 2, 5: 3, 6: 3, 7: 2 },
  /** Open pairs stop when the closest approach would fall below this (master units). */
  minApproach: 7.8,
};

/** Horizontal lockup, as TecHaust's LOCKUP: mark 1.28 x cap height, centred on the caps, gap two mark strokes. */
const MARK_SCALE = 1.28;
export const LOCKUP = {
  markScale: MARK_SCALE,
  markY: r((-(MARK_SCALE - 1) * MARK.size) / 2), // centred on the caps (cap height 100): -14
  gap: r(2 * STROKE * MARK_SCALE), // two strokes at lockup scale: 48.64
};

/** Endorsement: "BY TECHAUST" in IBM Plex Mono 500 caps. */
export const ENDORSE = {
  text: "BY TECHAUST",
  tracking: 0.08, // em, as text-caption
  capRatio: 0.3, // endorsement cap height / wordmark cap height (the endorsed lockup)
  gapStrokes: 1, // from the wordmark's baseline to the endorsement's cap line, in lockup mark strokes (19 x 1.28)
  captionPx: 12, // caption size (05 3): the endorsed lockup's minimum is where the endorsement reaches 12 px
};

/** Minimums from 05 1.3, in CSS px. The primary is 119 px (owner, 2026-10-26), so its symbol stays at 16 px. */
export const MINIMUM = { primaryWidth: 119, symbol: 16 };

// ---------------------------------------------------------------------------------------------------------------
// P3.3: installer-sized endorsed lockups
// ---------------------------------------------------------------------------------------------------------------
// The endorsed lockup needs 266 px for a 12 px endorsement; the NSIS side panel is 164 px and the header 150 px.
// Two smaller endorsed lockups keep the caption at 12 px. Both keep the approved symbol, wordmark and endorsement
// shapes, and align the endorsement with the wordmark's left edge as the endorsed lockup does. What changes is
// the endorsement's size relative to the wordmark: it is set by the 12 px caption at the installer size, not by
// the 0.3 cap ratio (which would give 7 px there).

/**
 * Stacked endorsed lockup (side panel, About): symbol above the wordmark, endorsement below, all flush left.
 * Sizes are given in pixels at the installer panel, where the symbol lands on a pixel-fitted size.
 */
export const STACKED = {
  symbolPx: 32, // the symbol, pixel-fitted
  wordWidthPx: 124, // the wordmark (cap height follows: 124 / 7.73 = 16.04 px, so the symbol is 2.0 x the cap)
  gapStrokes: 1, // symbol to the wordmark's cap line: one symbol stroke (19 units at symbol scale)
  captionPx: 12, // the endorsement's font size at this size
  endorseGapStrokes: 1, // from the wordmark's lowest ink (the y descender) to the endorsement's cap line, in lockup strokes
};

/**
 * Compact endorsed lockup (installer header): the primary lockup at its 119 px minimum (symbol 16 px, fitted),
 * with the endorsement at 12 px under the wordmark, clear of the y descender.
 */
export const COMPACT = {
  symbolPx: 16,
  captionPx: 12,
  endorseGapStrokes: 1, // from the wordmark's lowest ink to the endorsement's cap line, in lockup strokes
};

// ---------------------------------------------------------------------------------------------------------------
// P3.3: colour versions (TecHaust's five, by token name; hex values come from tokens.json)
// ---------------------------------------------------------------------------------------------------------------
export const VERSIONS = {
  color: { base: "ink-900", accent: "verdigris-700", text: "ink-900", label: "full colour, on light", on: "white" },
  dark: { base: "mist", accent: "verdigris-300", text: "mist", label: "full colour, on dark", on: "ink-900" },
  ink: { base: "ink-900", accent: "ink-900", text: "ink-900", label: "one colour, ink", on: "white" },
  white: { base: "white", accent: "white", text: "white", label: "one colour, white", on: "ink-900" },
  black: { base: "black", accent: "black", text: "black", label: "one colour, black", on: "white" },
};
export const LOCKUPS = ["primary", "symbol", "wordmark", "endorsed", "stacked", "compact"];

// ---------------------------------------------------------------------------------------------------------------
// P3.3: icons
// ---------------------------------------------------------------------------------------------------------------

/**
 * App icon plate (shelfsync.ico, favicon.ico): a Windows icon sits on light and dark surfaces alike (desktop, Start,
 * Explorer, browser tabs), and the mark's ink or mist disappears on one of them. So the icon is the dark version
 * of the symbol on an ink-900 plate. Wherever the symbol inside is 64 px or smaller it is pixel-fitted at one of
 * FIT_SIZES (the 96 px frame holds the 64 px fit), never under 16 px except in the 16 px frame; in the 128 and 256 px frames it is
 * the smooth vector at 2/3 of the plate.
 * At 16 px the symbol is fitted at 14 px inside a 1 px ink rim (square plate, no radius), so the frame keeps its
 * edge on white: the owner's exception to the 16 px symbol minimum, for this ICO frame only (docs/11, 2026-10-26).
 * The rule itself gives the 14 px fit: strokes 3 and 2 (the 16 px exception's horizontals), spur 2, openings 2.
 */
export const APP_ICON = {
  plate: "ink-900",
  version: "dark",
  radius: 0.1875, // corner radius / plate size (3 px at 16-px scale); 0 at 16 px
  smoothRatio: 2 / 3,
  sizes: [16, 20, 24, 32, 48, 64, 96, 128, 256],
  /** The fitted symbol size inside each plate at 64 px and below (96: 64 is fitted too). */
  fittedSymbol: { 16: 14, 20: 16, 24: 16, 32: 24, 48: 32, 64: 48, 96: 64 },
  /** The one fitted size outside FIT_SIZES, used only in the 16 px ICO frame (owner, 2026-10-26): fittedSymbol[16]. */
  get rimFit() {
    return this.fittedSymbol[16];
  },
  /** Frames stored as uncompressed 32-bit DIBs (every Windows API reads them); larger frames as PNG. */
  dibMax: 48,
};
export const FAVICON_ICO_SIZES = [16, 32, 48];

/**
 * Tray icons: the bare symbol, pixel-fitted, full bleed, on a transparent background, in the colour version on a
 * light taskbar and the dark version on a dark one. States are a badge in the bottom-right corner (Windows'
 * overlay corner), cut out of the mark with a clear gap so it never touches the ink:
 * - paused: two vertical bars (the pause sign), status "info";
 * - attention: a round dot (the warning dot), status "warning".
 * The two badges differ in shape (two bars against a dot), so the state never relies on colour. The badge and its
 * gap sit wholly below the spine, so the verdigris cut piece is never clipped and no stray fragments are left. Every
 * edge of the bars is on a whole pixel; the dot's edge is the only curve.
 */
export const TRAY = {
  sizes: [16, 20, 24, 32],
  taskbars: { light: "color", dark: "dark" }, // taskbar theme -> mark version
  states: ["normal", "paused", "attention"],
  status: { paused: "info", attention: "warning" },
  /** Per size: badge box (px, the largest that keeps box + gap below the spine), clear gap, pause bar width. */
  badge: {
    16: { box: 6, gap: 1, bar: 2 },
    20: { box: 7, gap: 1, bar: 2 },
    24: { box: 9, gap: 1, bar: 3 },
    32: { box: 11, gap: 2, bar: 3 },
  },
};

/** Mock Windows 11 taskbar greys for the contrast checks (no Patina token is a Windows grey): mixed from white
 * and black as in the P3.2 board (95 % white; 87.5 % black). */
export const TASKBAR_MIX = { light: 0.95, dark: 0.875 };

// ---------------------------------------------------------------------------------------------------------------
// P3.3: installer art (NSIS Modern UI) and GitHub images
// ---------------------------------------------------------------------------------------------------------------
export const INSTALLER = {
  /** Welcome / finish side panel: ink plate, the stacked endorsed lockup (dark), and the symbol tone-on-tone. */
  panel: {
    width: 164, height: 314, bg: "ink-900", version: "dark",
    x: 20, y: 28, // top-left of the stacked lockup (the wordmark is 124 px, so 20 px either side)
    watermark: { tone: "ink-700", size: 260, x: -110, y: 150 }, // the symbol's right half, cut channel and all, cropped by the panel
  },
  /** Inner-page header: white (the NSIS header is white), the compact endorsed lockup (colour), right-aligned. */
  header: { width: 150, height: 57, bg: "white", version: "color", right: 12 },
};

export const GITHUB = {
  /** Repository social preview: ink plate, the endorsed lockup (dark), the symbol tone-on-tone bleeding off the right. */
  social: { width: 1280, height: 640, bg: "ink-900", version: "dark", x: 112, lockupWidth: 600, watermark: { tone: "ink-700", size: 720, x: 820, y: -40 } },
  /** README header, transparent, drawn at 2x for a 640 x 160 display: the endorsed lockup, flush left. */
  readme: { width: 1280, height: 320, lockupWidth: 720, x: 0 },
};

// ---------------------------------------------------------------------------------------------------------------
// P3.3: file-size limits (bytes), guarded by the tests
// ---------------------------------------------------------------------------------------------------------------
export const SIZE_LIMIT = {
  logoSvg: 12_000, // a lockup with every glyph outlined
  faviconSvg: 1_500,
  faviconIco: 20_000,
  trayIco: 12_000,
  appIco: 40_000, // 9 frames: DIBs up to 48 px, PNG above
  installerBmp: 160_000, // uncompressed 24-bit: 164 x 314 x 3 plus padding and headers (155 KB)
  installerPng: 20_000,
  socialPng: 60_000,
  readmePng: 40_000,
};
