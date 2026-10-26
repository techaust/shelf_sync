// Writes the three concept SVGs and the comparison board into the P3.1 folder.
import { readFileSync, writeFileSync } from "node:fs";
import { CONCEPTS, params } from "./geometry.mjs";
import { COPY } from "./copy.mjs";

const OUT = process.argv[2];
const word = JSON.parse(readFileSync(new URL("./wordmark.json", import.meta.url), "utf8"));
const r = (n) => Math.round(n * 100) / 100;

// Lockup: as TecHaust's (geometry.ts LOCKUP): mark 1.28 × cap height, centred on the caps, gap two mark strokes.
const MARK_SCALE = 1.28, MARK_Y = -14, GAP = r(2 * 19 * MARK_SCALE);
const WX = r(100 * MARK_SCALE + GAP);
const WORD_W = r(word.bounds.x1);
const VB_Y0 = MARK_Y, VB_Y1 = Math.ceil(Math.max(114, word.bounds.y1));
const LOCKUP_VB = `0 ${VB_Y0} ${r(WX + WORD_W)} ${VB_Y1 - VB_Y0}`;
const glyphs = word.glyphs.map((d) => `<path d="${d}"/>`).join("");

const PALETTE = [
  ["ink-950", "#0D1613"], ["ink-900", "#14231F"], ["ink-800", "#15211D"], ["ink-750", "#111C18"],
  ["ink-700", "#1B2924"], ["ink-600", "#26352F"], ["ink-500", "#61796F"], ["ink-400", "#485752"],
  ["ink-300", "#9DB0A8"], ["verdigris-900", "#1F4A40"], ["verdigris-700", "#1E6B5C"], ["verdigris-500", "#2E8B77"],
  ["verdigris-300", "#6CC4AE"], ["verdigris-100", "#D7ECE5"], ["stone-50", "#F6F7F5"], ["stone-100", "#ECEFEB"],
  ["stone-200", "#E1E6E2"], ["stone-300", "#D3DBD6"], ["stone-500", "#75867F"], ["mist", "#E4EBE7"],
  ["white", "#FFFFFF"], ["black", "#000000"],
];

// ---- standalone SVGs (100-unit viewBox, ink + verdigris) ----
for (const c of CONCEPTS) {
  const g = c.fn(params(100));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="ShelfSync concept: ${c.name}">
  <title>ShelfSync concept ${c.id.split("-")[0]}: ${c.name} (P3.1, not final)</title>
  <!-- Patina colours from techaust_platform packages/ui/tokens/tokens.json (read-only); brand/tokens.json replaces them at P3.3. -->
  <style>
    svg { --ink-900: #14231F; /* token palette.ink-900 (brand ink) */ --verdigris-700: #1E6B5C; /* token palette.verdigris-700 (brand verdigris) */ }
    .base { fill: var(--ink-900); }
    .accent { fill: var(--verdigris-700); }
  </style>
  <!-- 100-unit grid. Vertical stroke 19, horizontal 17.5, channel 19 square to the 45° cut (26.87 across). -->
  <path class="base" d="${g.base}"/>
  <path class="accent" d="${g.accent}"/>
</svg>
`;
  writeFileSync(`${OUT}/concept-${c.id}.svg`, svg);
}

// ---- board pieces ----
const markSvg = (c, size, { pixel = false, cls = "", label = "" } = {}) => {
  const p = pixel ? params(size, true) : params(100);
  const g = c.fn(p);
  const vb = pixel ? size : 100;
  const aria = label ? `role="img" aria-label="${label}"` : `aria-hidden="true"`;
  return `<svg class="mk ${cls}" viewBox="0 0 ${vb} ${vb}" width="${size}" height="${size}" ${aria}><path class="b" d="${g.base}"/><path class="a" d="${g.accent}"/></svg>`;
};

const lockup = (c, label) => {
  const g = c.fn(params(100));
  return `<svg class="lockup" viewBox="${LOCKUP_VB}" role="img" aria-label="${label}"><g transform="translate(0 ${MARK_Y}) scale(${MARK_SCALE})"><path class="b" d="${g.base}"/><path class="a" d="${g.accent}"/></g><g class="w" transform="translate(${WX} 0)"><use href="#wordmark"/></g></svg>`;
};

// Construction plate: the 100-unit mark over a 10-unit grid, with the channel measured square to the cut.
const plate = (c, t) => {
  const g = c.fn(params(100));
  const { a, y0 } = g.channel;
  const d = 19 / Math.SQRT2;
  const p1 = [r(a - t), r(y0 + t)], p2 = [r(a - t + d), r(y0 + t + d)];
  const tick = (p) => `M${r(p[0] - 3)} ${r(p[1] + 3)}L${r(p[0] + 3)} ${r(p[1] - 3)}`;
  let grid = "";
  for (let i = 10; i < 100; i += 10) grid += `M${i} 0V100M0 ${i}H100`;
  return `<svg class="plate" viewBox="-6 -6 112 112" role="img" aria-label="${c.name} on the 100-unit grid, channel measured at 19 units">
    <path class="grid" d="${grid}"/><rect class="frame" x="0" y="0" width="100" height="100"/>
    <path class="b" d="${g.base}"/><path class="a" d="${g.accent}"/>
    <path class="dim" d="M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}${tick(p1)}${tick(p2)}"/>
    <text class="dim-label" x="${r((p1[0] + p2[0]) / 2 + 5)}" y="${r((p1[1] + p2[1]) / 2 - 4)}">19</text>
  </svg>`;
};

const taskbar = (c, tone) => `
  <div class="taskbar taskbar--${tone}" role="img" aria-label="Sample Windows 11 taskbar, ${tone}, with the ${c.name} tray icon at 16 px">
    <span class="tb-neighbour" aria-hidden="true"></span>
    <span class="tb-neighbour tb-neighbour--wide" aria-hidden="true"></span>
    <span class="tb-slot">${markSvg(c, 16, { pixel: true })}</span>
    <span class="tb-neighbour" aria-hidden="true"></span>
    <span class="tb-clock" aria-hidden="true"><span>14:05</span><span>26/10/2026</span></span>
  </div>`;

const checks = (list) =>
  `<ul class="checks">${list.map(([verdict, rule, note]) => `<li><span class="verdict verdict--${verdict === "Pass" ? "pass" : "note"}">${verdict}</span><p><span class="rule">${rule}.</span> <span class="note">${note}</span></p></li>`).join("")}</ul>`;

const column = (c, i) => {
  const k = COPY[c.id];
  return `
  <article class="concept" aria-labelledby="h-${c.id}">
    <header class="cell cell--head">
      <h2 id="h-${c.id}"><span class="num">${i + 1}</span> ${c.name}</h2>
      <p class="idea">${k.idea}</p>
      <p class="file"><a href="concept-${c.id}.svg">concept-${c.id}.svg</a></p>
    </header>
    <figure class="cell cell--plate">
      <div class="plate-row">
        ${plate(c, k.dimT)}
        <div class="sizes">
          <span class="size">${markSvg(c, 64, { pixel: true, label: `${c.name} at 64 px` })}<span class="px">64</span></span>
          <span class="size">${markSvg(c, 32, { pixel: true, label: `${c.name} at 32 px` })}<span class="px">32</span></span>
          <span class="size">${markSvg(c, 16, { pixel: true, label: `${c.name} at 16 px` })}<span class="px">16</span></span>
        </div>
      </div>
      <figcaption>${k.plate} Right: pixel-fitted at 64, 32 and 16 px.</figcaption>
    </figure>
    <figure class="cell cell--lockups">
      <div class="lockup-panel tone-light">${lockup(c, `ShelfSync primary lockup, ${c.name}, on light`)}<span class="min">${lockup(c, `The same lockup at its 96 px minimum`)}</span></div>
      <div class="lockup-panel tone-dark">${lockup(c, `ShelfSync primary lockup, ${c.name}, on dark`)}<span class="min">${lockup(c, `The same lockup at its 96 px minimum, on dark`)}</span></div>
      <figcaption>Primary lockup on white and on the ink-900 app bar, full size and at the 96 px minimum.</figcaption>
    </figure>
    <figure class="cell cell--tray">
      ${taskbar(c, "light")}
      ${taskbar(c, "dark")}
      <div class="zoom-pair">
        <canvas class="zoom tone-light" width="16" height="16" data-concept="${i}" role="img" aria-label="${c.name} rendered at 16 px, light, enlarged six times"></canvas>
        <canvas class="zoom tone-dark" width="16" height="16" data-concept="${i}" role="img" aria-label="${c.name} rendered at 16 px, dark, enlarged six times"></canvas>
      </div>
      <figcaption>Tray icon at 16 px between placeholder icons on a mock taskbar, light and dark. Below, the real 16 px raster enlarged 6×.</figcaption>
    </figure>
    <section class="cell cell--small" aria-label="${c.name} at small size">
      <h3>At small size</h3>
      <p><strong>Strongest:</strong> ${k.strong}</p>
      <p><strong>Weakest:</strong> ${k.weak}</p>
    </section>
    <section class="cell cell--checks" aria-label="${c.name} rule checks">
      <h3>Rule checks</h3>
      ${checks(k.checks)}
    </section>
  </article>`;
};

const zoomData = CONCEPTS.map((c) => c.fn(params(16, true)));

const html = `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShelfSync logo concepts (P3.1)</title>
<style>
/* Patina tokens, copied once from techaust_platform packages/ui/tokens/tokens.json (identity "Patina", 2026-10-06).
   brand/tokens.json does not exist yet (P3.3); every colour on this board comes from these custom properties. */
:root {
${PALETTE.map(([k, v]) => `  --${k}: ${v}; /* palette.${k} */`).join("\n")}
  /* Mock Windows 11 taskbar surfaces, mixed from the white and black tokens (no Patina token matches Windows' neutral greys). */
  --taskbar-light: color-mix(in srgb, var(--white) 95%, var(--black));
  --taskbar-dark: color-mix(in srgb, var(--black) 87.5%, var(--white));
  /* Type and space, from tokens.json text / space (docs/05 §3–4). */
  --text-display-2: 36px; --text-h2: 28px; --text-h4: 20px; --text-body: 16px; --text-sm: 14px; --text-caption: 12px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px; --space-12: 48px; --space-16: 64px;
  --radius-sm: 4px; --radius-md: 8px;
}
@font-face { font-family: "Archivo"; src: url("fonts/archivo-latin.woff2") format("woff2"); font-weight: 400 600; font-stretch: 100% 116%; font-display: swap; }
@font-face { font-family: "IBM Plex Mono"; src: url("fonts/ibm-plex-mono-latin.woff2") format("woff2"); font-weight: 400; font-display: swap; }

/* Semantic tokens (docs/05 §2.2). The board follows the system theme; the button overrides it. */
:root, [data-theme="light"] {
  color-scheme: light;
  --color-bg: var(--stone-50); --color-surface: var(--white); --color-surface-alt: var(--stone-100);
  --color-text: var(--ink-900); --color-text-muted: var(--ink-400); --color-text-accent: var(--verdigris-700);
  --color-border: var(--stone-300); --color-border-control: var(--stone-500); --color-focus: var(--verdigris-700);
  --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --color-bg: var(--ink-950); --color-surface: var(--ink-800); --color-surface-alt: var(--ink-750);
    --color-text: var(--mist); --color-text-muted: var(--ink-300); --color-text-accent: var(--verdigris-300);
    --color-border: var(--ink-600); --color-border-control: var(--ink-500); --color-focus: var(--verdigris-300);
    --mark-base: var(--mist); --mark-accent: var(--verdigris-300);
  }
}
[data-theme="dark"] {
  color-scheme: dark;
  --color-bg: var(--ink-950); --color-surface: var(--ink-800); --color-surface-alt: var(--ink-750);
  --color-text: var(--mist); --color-text-muted: var(--ink-300); --color-text-accent: var(--verdigris-300);
  --color-border: var(--ink-600); --color-border-control: var(--ink-500); --color-focus: var(--verdigris-300);
  --mark-base: var(--mist); --mark-accent: var(--verdigris-300);
}
/* Fixed tones, whatever the board theme: the brief asks for every lockup and tray icon on light and on dark. */
.tone-light { --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700); --mark-text: var(--ink-900); }
.tone-dark { --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --mark-text: var(--mist); }

* { box-sizing: border-box; }
html { background: var(--color-bg); color: var(--color-text); }
body { margin: 0; font-family: "Archivo", Arial, Helvetica, sans-serif; font-size: var(--text-body); line-height: 1.6; }
.b { fill: var(--mark-base); }
.a { fill: var(--mark-accent); }
.w { fill: var(--mark-text, var(--mark-base)); }
a { color: var(--color-text); text-underline-offset: 3px; }
a:hover { color: var(--color-text-accent); }
:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; border-radius: 2px; }

.board { padding: var(--space-12) var(--space-8) var(--space-16); max-width: 1440px; }
.board-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-8); margin-bottom: var(--space-10); }
h1 { font-size: var(--text-display-2); font-stretch: 116%; font-weight: 560; line-height: 1.1; margin: 0 0 var(--space-3); letter-spacing: -0.01em; }
.lede { margin: 0; max-width: 68ch; color: var(--color-text-muted); }
.lede + .lede { margin-top: var(--space-2); }
.theme-btn {
  flex: none; min-height: 44px; padding: 0 var(--space-4); border-radius: var(--radius-md);
  border: 1px solid var(--color-border-control); background: var(--color-surface); color: var(--color-text);
  font: 500 var(--text-sm)/1 "Archivo", Arial, sans-serif; cursor: pointer; display: inline-flex; align-items: center; gap: var(--space-2);
}
.theme-btn:hover { border-color: var(--color-text); }
.theme-btn svg { width: 16px; height: 16px; }

.concepts { display: grid; grid-template-columns: repeat(3, 304px); column-gap: var(--space-6); grid-template-rows: repeat(6, auto); }
@media (min-width: 1360px) { .board { padding-left: var(--space-16); padding-right: var(--space-16); } .concepts { grid-template-columns: repeat(3, 416px); column-gap: var(--space-8); } }
@media (max-width: 1000px) { .concepts { grid-template-columns: minmax(0, 416px); } .concept + .concept { margin-top: var(--space-16); } }
.concept { display: grid; grid-row: span 6; grid-template-rows: subgrid; min-width: 0; }
.cell { margin: 0; padding: var(--space-6) 0; border-top: 1px solid var(--color-border); min-width: 0; }
.cell--head { border-top: 2px solid var(--color-text); padding-top: var(--space-4); }
h2 { font-size: var(--text-h2); font-stretch: 116%; font-weight: 560; line-height: 1.15; margin: 0 0 var(--space-3); display: flex; align-items: baseline; gap: var(--space-3); }
h2 .num { font-size: var(--text-sm); font-stretch: 100%; font-weight: 500; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.idea { margin: 0 0 var(--space-3); }
.file { margin: 0; font: 400 var(--text-sm)/1.5 "IBM Plex Mono", Consolas, monospace; }
figcaption { margin-top: var(--space-3); font-size: var(--text-sm); line-height: 1.45; color: var(--color-text-muted); }
h3 { font-size: var(--text-h4); font-weight: 600; line-height: 1.3; margin: 0 0 var(--space-3); }

.plate-row { display: flex; gap: var(--space-6); align-items: flex-start; }
.plate { display: block; flex: none; width: 200px; height: 200px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.plate .grid { stroke: var(--color-border); stroke-width: 1; vector-effect: non-scaling-stroke; fill: none; }
.plate .frame { stroke: var(--color-border-control); stroke-width: 1; vector-effect: non-scaling-stroke; fill: none; }
.plate .dim { stroke: var(--color-text); stroke-width: 1.5; vector-effect: non-scaling-stroke; fill: none; }
.plate .dim-label { font: 400 5px "IBM Plex Mono", Consolas, monospace; fill: var(--color-text); text-anchor: middle; paint-order: stroke; stroke: var(--color-surface); stroke-width: 1.2px; }

.sizes { display: flex; flex-direction: column; gap: var(--space-4); }
.size { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-2); }
.mk { display: block; flex: none; }
.px { font-size: var(--text-caption); line-height: 16px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.px::after { content: " px"; }
.zoom-pair { display: inline-flex; margin-top: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
.zoom { display: block; width: 96px; height: 96px; image-rendering: pixelated; padding: 16px; box-sizing: content-box; }
.zoom.tone-light { background: var(--white); }
.zoom.tone-dark { background: var(--ink-900); }

.lockup-panel { border-radius: var(--radius-md); padding: var(--space-6) var(--space-6) var(--space-5); display: flex; flex-direction: column; gap: var(--space-5); }
.lockup-panel + .lockup-panel { margin-top: var(--space-3); }
.lockup-panel.tone-light { background: var(--white); border: 1px solid var(--color-border); }
.lockup-panel.tone-dark { background: var(--ink-900); border: 1px solid var(--ink-600); }
.lockup { display: block; width: 100%; height: auto; }
.min .lockup { width: 96px; }

.taskbar { height: 48px; display: flex; align-items: center; justify-content: flex-end; gap: 0; padding: 0 var(--space-3); border-radius: var(--radius-sm); }
.taskbar + .taskbar { margin-top: var(--space-2); }
.taskbar--light { background: var(--taskbar-light); color: var(--ink-900); border: 1px solid var(--stone-300); --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700); --neighbour: var(--stone-500); }
.taskbar--dark { background: var(--taskbar-dark); color: var(--mist); border: 1px solid var(--ink-600); --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --neighbour: var(--ink-500); }
.tb-slot, .tb-neighbour { width: 32px; height: 32px; display: grid; place-items: center; flex: none; }
.tb-neighbour::before { content: ""; width: 16px; height: 12px; border: 2px solid var(--neighbour); border-radius: 3px; }
.tb-neighbour--wide::before { width: 14px; height: 14px; border-radius: 50%; }
.tb-clock { display: flex; flex-direction: column; align-items: flex-end; margin-left: var(--space-3); font-size: var(--text-caption); line-height: 16px; font-variant-numeric: tabular-nums; }

.cell--small p { margin: 0 0 var(--space-2); font-size: var(--text-sm); line-height: 1.5; }
.checks { list-style: none; margin: 0; padding: 0; font-size: var(--text-sm); line-height: 1.45; }
.checks li { display: grid; grid-template-columns: 64px 1fr; column-gap: var(--space-3); padding: var(--space-2) 0; border-top: 1px solid var(--color-border); }
.checks p { margin: 0; }
.checks li:first-child { border-top: 0; padding-top: 0; }
.verdict { font-weight: 600; }
.verdict--pass::before { content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 6px; background: currentColor; vertical-align: 1px; }
.verdict--note::before { content: ""; display: inline-block; width: 6px; height: 6px; margin-right: 6px; border: 1px solid currentColor; vertical-align: 1px; }
.rule { font-weight: 500; }
.note { color: var(--color-text-muted); }

.board-foot { margin-top: var(--space-12); padding-top: var(--space-6); border-top: 1px solid var(--color-border); max-width: 80ch; font-size: var(--text-sm); color: var(--color-text-muted); }
.board-foot p { margin: 0 0 var(--space-2); }
.mono { font-family: "IBM Plex Mono", Consolas, monospace; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><symbol id="wordmark" overflow="visible">${glyphs}</symbol></svg>
<div class="board">
  <header class="board-head">
    <div>
      <h1>ShelfSync logo concepts</h1>
      <p class="lede">Three directions for the ShelfSync symbol, drawn on the TecHaust mark's construction: solid blocks on a 100-unit grid, one 45° channel exactly one stroke wide, ink with a verdigris accent. Pick one; P3.2 refines and audits it.</p>
      <p class="lede">The wordmark is Archivo at weight 620 and 116 % width, outlined from the font with its own kerning. Bespoke letter edits come in P3.2.</p>
    </div>
    <button class="theme-btn" id="theme" type="button" aria-pressed="false"><svg viewBox="0 0 16 16" aria-hidden="true"><path class="b" d="M8 1a7 7 0 1 0 0 14Z"/><path d="M8 1a7 7 0 0 1 0 14" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><span>Dark board</span></button>
  </header>
  <main class="concepts">
${CONCEPTS.map(column).join("\n")}
  </main>
  <footer class="board-foot">
    <p>Colours: the Patina palette from TecHaust's <span class="mono">packages/ui/tokens/tokens.json</span>, set once at the top of this page. The two taskbar greys are mixed from the white and black tokens to stand in for Windows 11; the real taskbar is checked when the tray icons are built (P3.3).</p>
    <p>Sample content: the taskbar clock and the neighbouring tray icons are placeholders.</p>
    <p>Fonts: Archivo and IBM Plex Mono, SIL Open Font License 1.1 (<a href="fonts/LICENSES.md">fonts/LICENSES.md</a>).</p>
  </footer>
</div>
<script>
(() => {
  const root = document.documentElement;
  const btn = document.getElementById("theme");
  const label = btn.querySelector("span");
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => root.dataset.theme ? root.dataset.theme === "dark" : sysDark.matches;
  const sync = () => { const d = isDark(); btn.setAttribute("aria-pressed", String(d)); label.textContent = d ? "Light board" : "Dark board"; };
  btn.addEventListener("click", () => { root.dataset.theme = isDark() ? "light" : "dark"; sync(); });
  sysDark.addEventListener("change", sync);
  sync();

  // The real 16 px raster: draw the pixel-fitted SVG into a 16 × 16 canvas, then show it enlarged with no smoothing.
  const marks = ${JSON.stringify(zoomData.map(({ base, accent }) => ({ base, accent })))};
  for (const cv of document.querySelectorAll("canvas.zoom")) {
    const cs = getComputedStyle(cv);
    const m = marks[Number(cv.dataset.concept)];
    const fill = (v) => cs.getPropertyValue(v).trim();
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">' +
      '<path fill="' + fill("--mark-base") + '" d="' + m.base + '"/><path fill="' + fill("--mark-accent") + '" d="' + m.accent + '"/></svg>';
    const img = new Image();
    img.onload = () => cv.getContext("2d").drawImage(img, 0, 0, 16, 16);
    img.src = "data:image/svg+xml," + encodeURIComponent(svg);
  }
})();
</script>
</body>
</html>
`;
writeFileSync(`${OUT}/index.html`, html);
console.log("lockup viewBox", LOCKUP_VB);
for (const c of CONCEPTS) for (const s of [16, 32, 64]) console.log(c.id, s, JSON.stringify(c.fn(params(s, true))));
