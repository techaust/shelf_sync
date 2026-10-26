// One command rebuilds every P3.2 output from geometry.mjs:
//   node "brand/draft/build.mjs"            (from the project folder; writes to docs/05-design-system-appendix/p3.2-logo-refine/)
// It writes the SVGs, index.html and measurements.json, then prints the key numbers and fails on a broken rule.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { board } from "./board.mjs";
import { MARK, RECOMMENDED, VARIANTS, WORDMARK, mark } from "./geometry.mjs";
import { all, fivePath } from "./measure.mjs";
import { coverage } from "./raster.mjs";
import { files, layout } from "./svg.mjs";
import { drawEndorsement, drawWordmark } from "./wordmark.mjs";

const OUT = process.argv[2] ?? fileURLToPath(new URL("../../docs/05-design-system-appendix/p3.2-logo-refine/", import.meta.url));
mkdirSync(OUT, { recursive: true });

const data = await all();
const word = await drawWordmark();
const wordBefore = await drawWordmark({ edits: false });
const endorse = await drawEndorsement();
const L = layout(word, endorse);

// Coverage grids for the board's rasters.
const r2 = (n) => Math.round(n * 100) / 100;
const cov = (d, px) => [...coverage(d, px, px <= 32 ? 16 : 8)].map(r2);
const grid = (m, px) => ({ base: cov(m.base, px), accent: cov(m.accent, px) });
const rasters = {};
for (const px of [16, 20, 24, 32, 48, 64]) rasters[`final-${px}`] = grid(mark(RECOMMENDED, px), px);
for (const v of VARIANTS) rasters[`var-${v.id}-16`] = grid(mark(v.id, 16), 16);
for (const px of [16, 32]) {
  rasters[`p31-${px}`] = grid(mark("p3.1", px), px);
  rasters[`five-${px}`] = { base: cov(fivePath("p3.1", px), px), accent: new Array(px * px).fill(0) };
  rasters[`five-new-${px}`] = { base: cov(fivePath(RECOMMENDED, px), px), accent: new Array(px * px).fill(0) };
}

// Files.
const svgs = files(word, endorse, L);
for (const [name, body] of Object.entries(svgs)) writeFileSync(join(OUT, name), body);
writeFileSync(join(OUT, "index.html"), board({ data, word, wordBefore, endorse, L, rasters }));
const json = { generatedBy: "brand/draft/build.mjs", recommended: RECOMMENDED, wordmark: { pairs: WORDMARK.pairs, tracking: WORDMARK.tracking, fCut: word.cut && { ...word.cut, d: undefined }, width: word.bounds.x1, widthBefore: wordBefore.bounds.x1 }, lockup: { ...L, vb: L.vb }, endorsement: { cap: endorse.cap, emSize: endorse.emSize, width: endorse.width }, ...data };
writeFileSync(join(OUT, "measurements.json"), JSON.stringify(json, null, 2) + "\n");

// Guards: the build fails if a rule breaks.
const fail = [];
for (const f of data.pixelFit) {
  if (!f.whole) fail.push(`${f.px} px: an edge is off the pixel grid`);
  if (!f.diagonals45slash || f.diagonals !== 2) fail.push(`${f.px} px: a cut is not 45 degrees "/"`);
  if (f.upperOpening < 2 || f.lowerOpening < 2) fail.push(`${f.px} px: a counter opening is under 2 px`);
  if (f.spur < 2) fail.push(`${f.px} px: the spur is under 2 px`);
}
const rec = data.shares.find((s) => s.id === RECOMMENDED);
if (!(rec.share < 50)) fail.push("verdigris is not the smaller part");
if (data.darkSplit[RECOMMENDED].minClear < 2) fail.push("the 16 px channel has fewer than 2 clear pixels on a spine row");
if (data.calibration.maxDiff > 0.5) fail.push(`white-area method drifted from TecHaust's published values by ${data.calibration.maxDiff}`);
// Vector construction: horizontals about 8 % thinner (7 to 9 %), channel exactly one stroke square to the cut.
const thinner = (MARK.v - MARK.h) / MARK.v;
if (thinner < 0.07 || thinner > 0.09) fail.push(`horizontals are ${(100 * thinner).toFixed(1)} % thinner, not about 8 %`);
if (Math.abs(mark().p.ch / Math.SQRT2 - MARK.v) > 1e-9) fail.push("the vector channel is not one stroke square to the cut");
for (const f of data.pixelFit) if (f.px >= 40 && !(f.h < f.v)) fail.push(`${f.px} px: horizontals not thinner than verticals`);
// f-crossbar cut: ends at the bar's full height, at 45 degrees, running "/" (down-left from the bar's top-right corner).
const c = word.cut;
if (!c) fail.push("the f crossbar is not cut");
else {
  if (Math.abs(c.edge.dy - c.height) > 0.01) fail.push("the f cut does not span the full bar height");
  if (Math.abs(Math.abs(c.edge.dx) - c.edge.dy) > 0.01) fail.push("the f cut is not 45 degrees");
  if (!(c.edge.dx < 0 && c.edge.dy > 0)) fail.push('the f cut does not run "/"');
  if (!word.glyphs[WORDMARK.text.indexOf("f")].includes(`L${c.maxX} ${c.barTop}L${c.cutX} ${c.barBottom}`)) fail.push("the f cut edge is not in the outline");
}
for (const p of data.spacing.pairs) if (p.closestAfter < WORDMARK.minApproach - 0.05) fail.push(`${p.pair} closer than ${WORDMARK.minApproach}`);

console.log(`wrote ${Object.keys(svgs).length} SVGs, index.html and measurements.json to ${OUT}`);
console.log("verdigris share:", data.shares.map((s) => `${s.id} ${s.share} % (16 px ${s.share16} %)`).join("; "));
console.log("pixel fit:", data.pixelFit.map((f) => `${f.px}px v${f.v} h${f.h} spur${f.spur} ch${f.channelRun} open${f.upperOpening}/${f.lowerOpening} (${f.channelVsStroke} %) whole=${f.whole} 45/=${f.diagonals45slash}`).join("; "));
console.log("dark split 16 px:", JSON.stringify(data.darkSplit[RECOMMENDED].rows), "joint", data.darkSplit[RECOMMENDED].jointEdges);
console.log("not a 5 (pixels differing from a square 5):", JSON.stringify(data.notFive), JSON.stringify(data.notFive32));
console.log("spacing (ref", data.spacing.reference + "):", data.spacing.pairs.map((p) => `${p.pair} ${p.before}->${p.after} (k${p.kern}, min ${p.closestAfter})`).join("; "));
console.log("calibration:", data.calibration.rows.map((x) => `${x.pair} ${x.published}/${x.ours}`).join("; "));
console.log("f cut:", JSON.stringify({ height: c?.height, edge: c?.edge, from: [c?.maxX, c?.barTop], to: [c?.cutX, c?.barBottom] }), "wordmark width", word.bounds.x1);
console.log("lockup:", JSON.stringify(L.minimum));
if (fail.length) { console.error("FAILED:\n- " + fail.join("\n- ")); process.exit(1); }
console.log("all guards passed");
