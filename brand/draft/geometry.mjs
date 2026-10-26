// ShelfSync logo, P3.2 draft: every number of the mark, the wordmark and the lockups lives here.
// Every output (SVGs, the board, the measurements) is generated from this file by build.mjs; nothing is hand-edited.
// Construction follows TecHaust's packages/ui/src/brand/geometry.ts (read-only reference): vertical stroke 19,
// horizontal 17.5 (8 % thinner), spine centre 48.5 (1.5 above centre), one 45 degree channel exactly one stroke
// wide measured square to the cut, and the cut always runs "/" (owner decision, docs/11 2026-10-26).

const r = (n) => Math.round(n * 100) / 100;

/** The vector mark on its 100-unit grid. */
export const MARK = {
  size: 100,
  v: 19, // vertical stroke (stems, spurs)
  h: 17.5, // horizontal stroke (top bar, spine, bottom bar): 7.9 % thinner than v
  cy: 48.5, // centre line of the spine, 1.5 above the geometric centre
  spur: 9, // P3.2 "not a 5": the top-right and bottom-left terminals turn down / up by this much
};
/** Clear space on every side, and the unit for the lockup gap. */
export const STROKE = MARK.v;

/**
 * Pixel fitting at `px`, TecHaust's pixelMark rule: v = round(0.19 px), at least 2; below 40 px the horizontals
 * equal the verticals (a 1 px correction would be far more than 8 %), above it h = round(0.175 px); the channel's
 * horizontal run is round(v * sqrt 2) so both cut ends land on whole pixels.
 * Two additions for the S, which stacks three horizontals where TecHaust's TH has two:
 * - the spur is round(0.09 px) but at least 2 px, so it reads as a turned terminal, not a thicker bar end;
 * - if the opening between the spur and the spine would fall under 2 px, the horizontals lose 1 px (at 16 px only).
 */
export const PIXEL = { minSpur: 2, minOpening: 2 };
export function params(px, { legacy = false } = {}) {
  if (!px) return { ...MARK, ch: MARK.v * Math.SQRT2, q: r, pixel: false };
  const v = Math.max(2, Math.round(px * 0.19));
  const cy = px * 0.485;
  const spur = Math.max(PIXEL.minSpur, Math.round(px * 0.09));
  let h = px < 40 ? v : Math.round(px * 0.175);
  const opening = (hh) => Math.round(cy - hh / 2) - hh - spur;
  if (!legacy && opening(h) < PIXEL.minOpening) h -= 1; // legacy: P3.1's fit, for the before views
  return { size: px, v, h, cy, spur, ch: Math.round(v * Math.SQRT2), q: Math.round, pixel: true, thinned: h < (px < 40 ? v : Math.round(px * 0.175)) };
}

/** The S as named pieces. The channel crosses the spine with its centre line on the spine's centre point. */
function frame(p, { spurs = true } = {}) {
  const { size: S, v, h, cy, ch, q } = p;
  const sp = spurs ? p.spur : 0;
  const y0 = q(cy - h / 2);
  const y1 = r(y0 + h);
  const a = q(S / 2 + cy - ch / 2 - y0); // ink cut: top end of the "/" edge
  const g = r(a + ch); // verdigris cut, one channel further right
  return { S, v, h, sp, y0, y1, a, g, b0: r(S - h) };
}

// Outlines, one closed path per connected piece of one colour (so no seams appear inside a colour).
const top = ({ S, v, h, sp, y0, y1, a }) => `M0 0H${S}V${r(h + sp)}H${r(S - v)}V${h}H${v}V${y0}H${a}L${r(a - h)} ${y1}H0Z`;
const lowerAll = ({ S, v, sp, y0, y1, g, h, b0 }) => `M${g} ${y0}H${S}V${S}H0V${r(b0 - sp)}H${v}V${b0}H${r(S - v)}V${y1}H${r(g - h)}Z`;
const spineEnd = ({ S, y0, y1, g, h }) => `M${g} ${y0}H${S}V${y1}H${r(g - h)}Z`;
const stemBarSpur = ({ S, v, sp, y1, b0 }) => `M${S} ${y1}V${S}H0V${r(b0 - sp)}H${v}V${b0}H${r(S - v)}V${y1}Z`;
const bowl = ({ S, v, y0, y1, g, h, b0 }) => `M${g} ${y0}H${S}V${b0}H${r(S - v)}V${y1}H${r(g - h)}Z`;
const barSpur = ({ S, v, sp, b0 }) => `M0 ${r(b0 - sp)}H${v}V${b0}H${S}V${S}H0Z`;
const bowlCorner = ({ S, v, y0, y1, g, h }) => `M${g} ${y0}H${S}V${S}H${r(S - v)}V${y1}H${r(g - h)}Z`;
const terminal = ({ S, v, sp, b0 }) => `M0 ${r(b0 - sp)}H${v}V${b0}H${r(S - v)}V${S}H0Z`;

/**
 * Colour splits (P3.2 step 2). Ink stays the base; verdigris is one piece of the lower block.
 * `joint` names the edge where verdigris meets ink without the channel (a butt joint), for the dark-mode check.
 */
export const VARIANTS = [
  { id: "a-cut-piece", name: "Cut piece", what: "only the spine end the channel cuts off",
    paths: (f) => ({ base: top(f) + stemBarSpur(f), accent: spineEnd(f) }) },
  { id: "b-lower-bowl", name: "Lower bowl", what: "the spine end and the lower stem",
    paths: (f) => ({ base: top(f) + barSpur(f), accent: bowl(f) }) },
  { id: "c-lower-terminal", name: "Lower terminal", what: "the bottom bar's free end and its spur",
    paths: (f) => ({ base: top(f) + bowlCorner(f), accent: terminal(f) }) },
];
export const RECOMMENDED = "a-cut-piece";

/** The mark's two paths for a variant, at `px` (pixel-fitted) or as the 100-unit vector (px omitted). */
export function mark(variantId = RECOMMENDED, px, opts = {}) {
  const p = params(px, { legacy: variantId === "p3.1" });
  // "p3.1" is the P3.1 concept unchanged (no spurs, verdigris on the whole lower block), for before / after views.
  const f = frame(p, variantId === "p3.1" ? { spurs: false } : opts);
  if (variantId === "p3.1") return { base: top(f), accent: lowerAll(f), f, p };
  const vt = VARIANTS.find((x) => x.id === variantId);
  return { ...vt.paths(f), f, p };
}

/** Wordmark (P3.2 step 6): Archivo, TecHaust's settings, outlined with HarfBuzz; bespoke edits as numbers. */
export const WORDMARK = {
  text: "ShelfSync",
  axes: { wght: 620, wdth: 116 },
  cap: 100, // cap height in master units
  tracking: -6, // font units per glyph, as TecHaust's wordmark
  fCut: true, // the f crossbar's right end is cut at 45 degrees, "/", across the full bar height (as TecHaust's T bar)
  /**
   * Extra tightening before glyph i (master units, positive = closer), set from the white-area measurement:
   * 1 Sh, 4 lf, 7 yn bring the pair onto the "no" rhythm; 5 fS and 6 Sy are open by nature (most scanlines hit
   * the depth cap, as TecHaust's Te) and are tightened only until their closest approach nears the word's
   * tightest pair, so they stay above the rhythm on purpose.
   */
  pairs: { 1: 2, 4: 2, 5: 3, 6: 3, 7: 2 },
  /** Open pairs stop when the closest approach would fall below this (master units). */
  minApproach: 7.8,
};

/**
 * White-area measurement (TecHaust docs/11 2.3, "depth-capped scanlines"; TecHaust publishes the numbers, not the
 * code). Reproduced in measure.mjs as: on scanlines every 0.25 units between the baseline and the x-height, the
 * white between the two glyphs, capped at `depth` (open counters and missing ink count as the cap), averaged.
 * The depth was fitted to TecHaust's published values; measure.mjs re-runs that check on every build.
 */
export const SPACING = {
  depth: 27.5, // per-scanline cap, master units
  step: 0.25,
  reference: "no", // the font's own rhythm, set with the same axes and tracking
  tolerance: 0.08, // a pair more than 8 % off the reference is re-spaced (TecHaust left 4 % and 6 % alone, fixed 14 %+)
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
  capRatio: 0.3, // endorsement cap height / wordmark cap height
  gapStrokes: 1, // from the wordmark's baseline to the endorsement's cap line, in lockup mark strokes (19 x 1.28)
  captionPx: 12, // caption size (05 3): the endorsed lockup's minimum is where the endorsement reaches 12 px
};

/** Minimums from 05 1.3, in CSS px. */
export const MINIMUM = { primaryWidth: 96, symbol: 16 };
