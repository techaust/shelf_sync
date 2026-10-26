// Lockup layouts (one description per lockup, used by the SVG files and the rasters alike) and the vector files.
import { COMPACT, ENDORSE, LOCKUP, LOCKUPS, MARK, MINIMUM, STACKED, STROKE, VERSIONS, mark } from "../geometry.mjs";
import { hex } from "./tokens.mjs";
import { drawEndorsement, drawWordmark } from "./wordmark.mjs";

const r = (n) => Math.round(n * 100) / 100;
const r4 = (n) => Math.round(n * 10000) / 10000;
export const TITLE = "ShelfSync";
const LABELS = {
  primary: "ShelfSync", symbol: "ShelfSync", wordmark: "ShelfSync",
  endorsed: "ShelfSync by TecHaust", stacked: "ShelfSync by TecHaust", compact: "ShelfSync by TecHaust",
};

/**
 * Every lockup in wordmark master units (cap height 100, wordmark baseline at y = 100 where there is one).
 * parts: mark { x, y, size }, word { x, y }, endorse { x, y, d } (y = the top of the endorsement's caps).
 * `unitPx` (stacked, compact): the pixel size of one unit at the installer size the lockup was designed for.
 */
export async function layouts() {
  const word = await drawWordmark();
  const W = word.bounds.x1;
  const lockStroke = STROKE * LOCKUP.markScale; // 24.32
  const markSize = MARK.size * LOCKUP.markScale; // 128
  const wx = r(markSize + LOCKUP.gap); // 176.64
  const out = {};

  // Primary and endorsed (P3.2, unchanged).
  const pY0 = Math.min(LOCKUP.markY, Math.floor(word.bounds.y0));
  const pY1 = Math.max(LOCKUP.markY + markSize, Math.ceil(word.bounds.y1));
  const pW = r(wx + W);
  const markPart = { kind: "mark", x: 0, y: LOCKUP.markY, size: markSize };
  const wordPart = { kind: "word", x: wx, y: 0 };
  out.primary = { vb: [0, pY0, pW, r(pY1 - pY0)], parts: [markPart, wordPart] };
  out.symbol = { vb: [0, 0, 100, 100], parts: [{ kind: "mark", x: 0, y: 0, size: 100 }] };
  out.wordmark = { vb: [0, Math.floor(word.bounds.y0), r(W), r(Math.ceil(word.bounds.y1) - Math.floor(word.bounds.y0))], parts: [{ kind: "word", x: 0, y: 0 }] };
  const e = await drawEndorsement();
  const eTop = r(100 + ENDORSE.gapStrokes * lockStroke);
  out.endorsed = {
    vb: [0, pY0, pW, r(Math.max(pY1, eTop + e.cap) - pY0)],
    parts: [markPart, wordPart, { kind: "endorse", x: wx, y: eTop, d: e.d, width: e.width, cap: e.cap, emSize: e.emSize }],
  };

  // Stacked endorsed (side panel): sizes come from the installer panel, in px, converted to units.
  {
    const unitPx = STACKED.wordWidthPx / W; // px per unit (cap height = 100 units)
    const sym = STACKED.symbolPx / unitPx; // symbol size in units
    const capTop = r(sym + STACKED.gapStrokes * STROKE * (sym / MARK.size));
    const base = capTop + 100;
    const se = await drawEndorsement(r4((STACKED.captionPx * e.capPerEm) / unitPx));
    const seTop = r(base + (word.bounds.y1 - 100) + STACKED.endorseGapStrokes * lockStroke);
    out.stacked = {
      unitPx,
      vb: [0, 0, r(Math.max(W, sym)), r(seTop + se.cap)],
      parts: [{ kind: "mark", x: 0, y: 0, size: sym }, { kind: "word", x: 0, y: capTop }, { kind: "endorse", x: 0, y: seTop, d: se.d, width: se.width, cap: se.cap, emSize: se.emSize }],
    };
  }
  // Compact endorsed (header): the primary at its minimum, endorsement 12 px under the wordmark.
  {
    const unitPx = COMPACT.symbolPx / markSize;
    const ce = await drawEndorsement(r4((COMPACT.captionPx * e.capPerEm) / unitPx));
    const ceTop = r(word.bounds.y1 + COMPACT.endorseGapStrokes * lockStroke);
    out.compact = {
      unitPx,
      vb: [0, pY0, pW, r(ceTop + ce.cap - pY0)],
      parts: [markPart, wordPart, { kind: "endorse", x: wx, y: ceTop, d: ce.d, width: ce.width, cap: ce.cap, emSize: ce.emSize }],
    };
  }
  return { word, layouts: out, lockStroke };
}

/** The colours of one version, as hex. */
export const colours = (version) => {
  const v = VERSIONS[version];
  return { base: hex(v.base), accent: hex(v.accent), text: hex(v.text) };
};

/** SVG markup of a lockup's parts (no wrapper). */
export function lockupBody(L, word, k) {
  const m = mark();
  return L.parts.map((p) => {
    if (p.kind === "mark") {
      const s = r4(p.size / MARK.size);
      const t = p.x || p.y || s !== 1 ? ` transform="translate(${p.x} ${p.y})${s !== 1 ? ` scale(${s})` : ""}"` : "";
      return `<g${t}><path fill="${k.base}" d="${m.base}"/><path fill="${k.accent}" d="${m.accent}"/></g>`;
    }
    if (p.kind === "word") return `<g fill="${k.text}"${p.x || p.y ? ` transform="translate(${p.x} ${p.y})"` : ""}>${word.glyphs.filter(Boolean).map((d) => `<path d="${d}"/>`).join("")}</g>`;
    return `<path fill="${k.text}" transform="translate(${p.x} ${p.y})" d="${p.d}"/>`;
  }).join("");
}

/** A standalone SVG for one lockup + version. */
export function lockupSvg(kind, version, L, word) {
  const v = VERSIONS[version];
  const k = colours(version);
  const label = `${LABELS[kind]}, ${kind === "symbol" ? "symbol" : `${kind} lockup`}, ${v.label}`;
  const note = `Colours: palette.${v.base}${v.accent !== v.base ? `, palette.${v.accent}` : ""}${v.text !== v.base ? `, palette.${v.text}` : ""} (brand/tokens.json).`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${L.vb.join(" ")}" role="img" aria-label="${label}">` +
    `<title>${label}</title><!-- Generated by brand/scripts/build.mjs from brand/geometry.mjs. Do not edit. ${note} -->` +
    `${lockupBody(L, word, k)}</svg>\n`;
}

/** logo-<lockup>-<version>.svg for every lockup and version. */
export async function logoFiles() {
  const { word, layouts: all } = await layouts();
  const files = {};
  for (const kind of LOCKUPS) for (const version of Object.keys(VERSIONS)) files[`logo-${kind}-${version}.svg`] = lockupSvg(kind, version, all[kind], word);
  return files;
}

/** Minimum widths in CSS px (05 1.3 and the two installer lockups). */
export async function minimums() {
  const { layouts: L } = await layouts();
  const e = L.endorsed.parts[2];
  const pxPerUnitAt12 = ENDORSE.captionPx / e.emSize;
  const st = L.stacked, cp = L.compact;
  return {
    primary: { width: MINIMUM.primaryWidth, symbolPx: r((MINIMUM.primaryWidth / L.primary.vb[2]) * 128) },
    endorsed: { width: r(L.endorsed.vb[2] * pxPerUnitAt12), captionPx: ENDORSE.captionPx },
    stacked: { width: r(st.vb[2] * st.unitPx), height: r(st.vb[3] * st.unitPx), captionPx: r(st.parts[2].emSize * st.unitPx), symbolPx: r(st.parts[0].size * st.unitPx), capPx: r(100 * st.unitPx), ratio: r(st.parts[2].cap / 100) },
    compact: { width: r(cp.vb[2] * cp.unitPx), height: r(cp.vb[3] * cp.unitPx), captionPx: r(cp.parts[2].emSize * cp.unitPx), symbolPx: r(128 * cp.unitPx), capPx: r(100 * cp.unitPx), ratio: r(cp.parts[2].cap / 100) },
    // With the endorsed lockup's own 0.3 ratio, the largest caption the 164 px panel allows (1 stroke clear space):
    endorsedInPanelCaptionPx: r((164 / (L.endorsed.vb[2] + 2 * STROKE * LOCKUP.markScale)) * e.emSize),
  };
}
