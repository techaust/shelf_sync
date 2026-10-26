// Text -> vector outlines with HarfBuzz (shaping, kerning, variable axes). Mirrors TecHaust's
// packages/ui/src/brand/outline.ts. P3.2 only: the HarfBuzz, fontverter and font copies are the ones already
// installed in techaust_platform's node_modules. They are only read and run; nothing there is written.
// P3.3 replaces this with ShelfSync's own dev libraries (owner decision, docs/11 2026-10-26).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

export const TECHAUST_MODULES =
  "D:/BUSINESS/1. PARENT PROJECT/TECHAUST TECHNOLOGIES/WEBSITE/techaust_platform/node_modules/.pnpm/";
const P = TECHAUST_MODULES;
const hb = await import(pathToFileURL(P + "harfbuzzjs@1.6.2/node_modules/harfbuzzjs/dist/index.mjs").href);
const require = createRequire(P + "fontverter@2.0.0/node_modules/fontverter/index.js");
const fontverter = require(P + "fontverter@2.0.0/node_modules/fontverter/index.js");
const { Blob, Face, Font, Buffer: HbBuffer, shape, Variation } = hb;

export const FONTS = {
  archivo: P + "@fontsource-variable+archivo@5.3.0/node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2",
  plexMono500: P + "@fontsource+ibm-plex-mono@5.3.0/node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2",
};

const round = (v) => Math.round(v * 100) / 100;

/** Applies x' = sx*x + dx, y' = sy*y + dy to an absolute path (M/L/Q/C/Z, as HarfBuzz emits). */
export function transformPath(d, sx, sy, dx, dy) {
  const tokens = d.match(/[MLQCZ]|-?\d*\.?\d+(?:e-?\d+)?/gi) ?? [];
  const pairs = { M: 1, L: 1, Q: 2, C: 3, Z: 0 };
  let out = "";
  let i = 0;
  while (i < tokens.length) {
    const cmd = tokens[i++].toUpperCase();
    const pts = [];
    for (let k = 0; k < (pairs[cmd] ?? 0); k++) {
      const x = Number(tokens[i++]);
      const y = Number(tokens[i++]);
      pts.push(`${round(sx * x + dx)} ${round(sy * y + dy)}`);
    }
    out += cmd + pts.join(" ");
  }
  return out;
}

export function pathBounds(d) {
  const n = (d.match(/-?\d*\.?\d+/g) ?? []).map(Number);
  const xs = n.filter((_, i) => i % 2 === 0);
  const ys = n.filter((_, i) => i % 2 === 1);
  return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
}

const fonts = new Map();
async function loadFont(file, axes) {
  const key = file + JSON.stringify(axes);
  if (!fonts.has(key)) {
    const sfnt = await fontverter.convert(readFileSync(file), "sfnt");
    const face = new Face(new Blob(sfnt), 0);
    const font = new Font(face);
    font.setVariations(Object.entries(axes).map(([tag, v]) => new Variation(tag, v)));
    fonts.set(key, { font, upem: face.upem });
  }
  return fonts.get(key);
}

/**
 * Outlines `text` so the cap height (of "H") is `cap`, baseline at y = cap, ink starting at x = 0.
 * `tracking` is in font units per glyph; `extra[i]` (master units) moves glyph i and everything after it
 * left (positive = tighter). Returns one path per glyph plus the font's own metrics in master units.
 */
export async function outlineText(file, text, { axes = {}, cap = 100, tracking = 0, trackingEm, extra = {} } = {}) {
  const { font, upem } = await loadFont(file, axes);
  if (trackingEm !== undefined) tracking = trackingEm * upem;
  const run = (s) => {
    const b = new HbBuffer();
    b.addText(s);
    b.guessSegmentProperties();
    shape(font, b);
    return b.getGlyphInfosAndPositions();
  };
  const H = run("H")[0];
  const hBox = pathBounds(font.glyphToPath(H.codepoint));
  const s = cap / (hBox.y1 - hBox.y0);
  const x = run("x")[0];
  const xBox = pathBounds(font.glyphToPath(x.codepoint));
  let pen = 0;
  let shift = 0;
  const glyphs = [];
  run(text).forEach((g, i) => {
    shift += extra[i] ?? 0;
    const p = font.glyphToPath(g.codepoint);
    glyphs.push(p ? transformPath(p, s, -s, (pen + (g.xOffset ?? 0)) * s - shift, cap - (g.yOffset ?? 0) * s) : "");
    pen += (g.xAdvance ?? 0) + tracking;
  });
  const x0 = pathBounds(glyphs.filter(Boolean).join("")).x0;
  const out = glyphs.map((p) => (p ? transformPath(p, 1, 1, -x0, 0) : p));
  return { glyphs: out, scale: s, upem, xHeight: round(xBox.y1 * s), emSize: round(upem * s) };
}
