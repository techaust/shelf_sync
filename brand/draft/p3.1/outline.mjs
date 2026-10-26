// Outlines "ShelfSync" in Archivo (wght 620, wdth 116) with the HarfBuzz + fontverter copies already
// installed in techaust_platform (read-only use; nothing there is written). Mirrors TecHaust outline.ts.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
const P = "D:/BUSINESS/1. PARENT PROJECT/TECHAUST TECHNOLOGIES/WEBSITE/techaust_platform/node_modules/.pnpm/";
const hb = await import(pathToFileURL(P + "harfbuzzjs@1.6.2/node_modules/harfbuzzjs/dist/index.mjs").href);
const require = createRequire(P + "fontverter@2.0.0/node_modules/fontverter/index.js");
const fontverter = require(P + "fontverter@2.0.0/node_modules/fontverter/index.js");
const FONT = P + "@fontsource-variable+archivo@5.3.0/node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2";
const { Blob, Face, Font, Buffer: HbBuffer, shape, Variation } = hb;
const round = (v) => Math.round(v * 100) / 100;
function transformPath(d, sx, sy, dx, dy) {
  const tokens = d.match(/[MLQCZ]|-?\d*\.?\d+(?:e-?\d+)?/gi) ?? [];
  const pairs = { M: 1, L: 1, Q: 2, C: 3, Z: 0 };
  let out = "", i = 0;
  while (i < tokens.length) {
    const cmd = tokens[i++].toUpperCase(); const pts = [];
    for (let k = 0; k < (pairs[cmd] ?? 0); k++) { const x = Number(tokens[i++]); const y = Number(tokens[i++]); pts.push(`${round(sx * x + dx)} ${round(sy * y + dy)}`); }
    out += cmd + pts.join(" ");
  }
  return out;
}
function bounds(d) {
  const n = (d.match(/-?\d*\.?\d+/g) ?? []).map(Number);
  const xs = n.filter((_, i) => i % 2 === 0), ys = n.filter((_, i) => i % 2 === 1);
  return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
}
const sfnt = await fontverter.convert(readFileSync(FONT), "sfnt");
const face = new Face(new Blob(sfnt), 0);
const font = new Font(face);
font.setVariations([new Variation("wght", 620), new Variation("wdth", 116)]);
const run = (s) => { const b = new HbBuffer(); b.addText(s); b.guessSegmentProperties(); shape(font, b); return b.getGlyphInfosAndPositions(); };
const H = run("H")[0];
const hb0 = bounds(font.glyphToPath(H.codepoint));
const cap = 100, tracking = -6, s = cap / (hb0.y1 - hb0.y0);
let x = 0; const glyphs = [];
for (const g of run("ShelfSync")) {
  const p = font.glyphToPath(g.codepoint);
  if (p) glyphs.push(transformPath(p, s, -s, (x + (g.xOffset ?? 0)) * s, cap - (g.yOffset ?? 0) * s));
  x += (g.xAdvance ?? 0) + tracking;
}
const x0 = bounds(glyphs.join("")).x0;
const out = glyphs.map((p) => transformPath(p, 1, 1, -x0, 0));
const b = bounds(out.join(""));
writeFileSync(process.argv[2], JSON.stringify({ glyphs: out, bounds: b }));
console.log("glyphs", out.length, "bounds", b);
