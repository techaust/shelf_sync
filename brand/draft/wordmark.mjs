// The "ShelfSync" wordmark and the "BY TECHAUST" endorsement as outlines, with the bespoke edits from geometry.mjs.
import { ENDORSE, WORDMARK } from "./geometry.mjs";
import { FONTS, outlineText, pathBounds } from "./outline.mjs";

const r = (n) => Math.round(n * 100) / 100;

/**
 * 45 degree "/" cut on the f crossbar's right end, as TecHaust's T bar (master.ts): the bar's lower-right corner
 * moves left by the bar height, so the cut runs across one full horizontal stroke.
 */
export function cutCrossbar(f, barLine) {
  // Parse into commands with their on-curve end points (absolute M/L/Q/C/Z, as HarfBuzz emits).
  const tok = f.match(/[MLQCZ]|-?\d*\.?\d+(?:e-?\d+)?/gi) ?? [];
  const n = { M: 1, L: 1, Q: 2, C: 3, Z: 0 };
  const cmds = [];
  for (let i = 0; i < tok.length; ) {
    const c = tok[i++].toUpperCase();
    const pts = [];
    for (let k = 0; k < n[c]; k++) pts.push([Number(tok[i++]), Number(tok[i++])]);
    cmds.push({ c, pts });
  }
  const end = (k) => cmds[k].pts[cmds[k].pts.length - 1];
  // The crossbar's right end: an L that runs straight down from the bar line (the f's crossbar top sits on the
  // x-height line), followed by an L that runs left along the bar bottom. Not found by "the rightmost x", which
  // the hook shares.
  const found = [];
  for (let k = 1; k + 1 < cmds.length; k++) {
    if (cmds[k].c !== "L" || cmds[k + 1].c !== "L" || !cmds[k - 1].pts.length) continue;
    const [x0, y0] = end(k - 1), [x1, y1] = end(k), [x2, y2] = end(k + 1);
    if (x0 === x1 && y1 > y0 && Math.abs(y0 - barLine) < 1.5 && y2 === y1 && x2 < x1) found.push({ k, x: x1, top: y0, bottom: y1 });
  }
  if (found.length !== 1) throw new Error(`f crossbar end: expected 1 candidate, found ${found.length}; the font outline changed`);
  const { k, x: maxX, top: barTop, bottom: barBottom } = found[0];
  const height = r(barBottom - barTop);
  const cutX = r(maxX - height);
  cmds[k].pts[0] = [cutX, barBottom];
  const d = cmds.map(({ c, pts }) => c + pts.map(([x, y]) => `${x} ${y}`).join(" ")).join("");
  // What the build guards: the new edge runs from (maxX, barTop) to (cutX, barBottom).
  const edge = { dx: r(cutX - maxX), dy: r(barBottom - barTop) };
  return { d, barTop, barBottom, height, maxX, cutX, edge };
}

/** `edits: false` gives P3.1's wordmark (font kerning and tracking only), for the before / after views. */
export async function drawWordmark({ edits = true } = {}) {
  const { glyphs, xHeight, scale } = await outlineText(FONTS.archivo, WORDMARK.text, {
    axes: WORDMARK.axes, cap: WORDMARK.cap, tracking: WORDMARK.tracking, extra: edits ? WORDMARK.pairs : {},
  });
  let cut = null;
  if (edits && WORDMARK.fCut) {
    const i = WORDMARK.text.indexOf("f");
    cut = cutCrossbar(glyphs[i], r(WORDMARK.cap - xHeight));
    glyphs[i] = cut.d;
  }
  const b = pathBounds(glyphs.join(""));
  return { glyphs, xHeight, scale, cut, bounds: { x0: r(b.x0), x1: r(b.x1), y0: r(b.y0), y1: r(b.y1) } };
}

/** The endorsement in IBM Plex Mono 500 caps, cap height = capRatio x the wordmark's, baseline at y = cap. */
export async function drawEndorsement() {
  const cap = r(WORDMARK.cap * ENDORSE.capRatio);
  const { glyphs, emSize } = await outlineText(FONTS.plexMono500, ENDORSE.text, { cap, trackingEm: ENDORSE.tracking });
  const d = glyphs.filter(Boolean).join("");
  const b = pathBounds(d);
  return { d, cap, emSize, width: r(b.x1) };
}
