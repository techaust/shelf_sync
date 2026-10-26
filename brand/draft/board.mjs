// The P3.2 review board (index.html). Every number on it comes from measure.mjs; every colour from PALETTE tokens.
import { ENDORSE, LOCKUP, MARK, RECOMMENDED, SPACING, VARIANTS, WORDMARK, mark } from "./geometry.mjs";
import { PALETTE } from "./measure.mjs";
import { lockupInner } from "./svg.mjs";
import { pathBounds } from "./outline.mjs";

const r = (n) => Math.round(n * 100) / 100;
const f1 = (n) => (Math.round(n * 10) / 10).toFixed(1);
const pct = (n) => `${f1(n)} %`;
const letter = (id) => id[0].toUpperCase();
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

// ---------- small builders ----------
const markPaths = (m) => `<path class="b" d="${m.base}"/><path class="a" d="${m.accent}"/>`;
const grid10 = () => { let g = ""; for (let i = 10; i < 100; i += 10) g += `M${i} 0V100M0 ${i}H100`; return g; };

/** Construction plate of the final mark with its dimensions (100-unit grid). */
function plate(m) {
  const { a, y0 } = m.f;
  const { size: S, v, h, spur: sp } = MARK; // every label and dimension below comes from MARK
  const d = MARK.v / Math.SQRT2;
  const t = MARK.h / 2;
  const p1 = [r(a - t), r(y0 + t)], p2 = [r(a - t + d), r(y0 + t + d)];
  const tick = (p) => `M${r(p[0] - 2.5)} ${r(p[1] + 2.5)}L${r(p[0] + 2.5)} ${r(p[1] - 2.5)}`;
  const hTick = (x, y) => `M${x - 2} ${y}H${x + 2}`;
  const vTick = (x, y) => `M${x} ${y - 2}V${y + 2}`;
  return `<svg class="plate" viewBox="-23 -11 141 120" role="img" aria-label="The final symbol on its 100-unit grid: vertical stroke 19, horizontal 17.5, spur 9, channel 19 measured square to the cut, spine centre 48.5">
    <path class="grid" d="${grid10()}"/><rect class="frame" x="0" y="0" width="100" height="100"/>
    ${markPaths(m)}
    <g class="dim">
      <path d="M${S - v} -4H${S}${vTick(S - v, -4)}${vTick(S, -4)}"/>
      <path d="M-6 0V${h}${hTick(-6, 0)}${hTick(-6, h)}"/>
      <path d="M${S + 6} ${h}V${r(h + sp)}${hTick(S + 6, h)}${hTick(S + 6, r(h + sp))}"/>
      <path d="M-6 ${MARK.cy}H-2" />
      <path class="centre" d="M0 ${MARK.cy}H100"/>
      <path d="M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}${tick(p1)}${tick(p2)}"/>
    </g>
    <g class="dim-label">
      <text x="${S - v - 3}" y="-2.5" text-anchor="end">${v}</text>
      <text x="-8" y="${r(h / 2 + 2.25)}" text-anchor="end">${h}</text>
      <text x="${S + 9}" y="${r(h + sp / 2 + 2)}">${sp}</text>
      <text x="-8" y="${r(MARK.cy + 1.6)}" text-anchor="end">${MARK.cy}</text>
      <text x="${r(p2[0] + 3)}" y="${r(p2[1] + 6)}">${v}</text>
    </g>
  </svg>`;
}

const smallPlate = (m, label) => `<svg class="vplate" viewBox="-4 -4 108 108" role="img" aria-label="${label}"><path class="grid" d="${grid10()}"/>${markPaths(m)}</svg>`;

/** Canvas raster, drawn by the page script from the coverage data. */
const zoom = (key, tone, size, label, gridOn = true) =>
  `<canvas class="rz tone-${tone}" data-r="${key}" data-size="${size}"${gridOn ? " data-grid" : ""} width="${size}" height="${size}" style="width:${size}px;height:${size}px" role="img" aria-label="${label}"></canvas>`;
const actual = (key, tone, px, label) =>
  `<canvas class="ra tone-${tone}" data-r="${key}" data-px="${px}" width="${px}" height="${px}" role="img" aria-label="${label}"></canvas>`;

const verdict = (v) => `<span class="verdict verdict--${v.toLowerCase()}">${v}</span>`;

// ---------- the spacing chart (dot plot: before ring, after dot, reference band) ----------
function spacingChart(s) {
  const rows = s.pairs;
  const W = 640, rowH = 34, top = 34, left = 56, right = 76, H = top + rows.length * rowH + 30;
  const x0 = 18, x1 = 28;
  const X = (v) => r(left + ((Math.min(Math.max(v, x0), x1) - x0) / (x1 - x0)) * (W - left - right));
  const lo = s.reference * (1 - s.tolerance), hi = s.reference * (1 + s.tolerance);
  let ticks = "";
  for (let v = x0; v <= x1; v += 2) ticks += `<path class="ch-grid" d="M${X(v)} ${top - 6}V${H - 26}"/><text class="ch-tick" x="${X(v)}" y="${H - 10}" text-anchor="middle">${v}</text>`;
  const marks = rows.map((p, i) => {
    const y = top + i * rowH + rowH / 2;
    const moved = Math.abs(p.after - p.before) >= 0.05;
    return `<g class="ch-row">
      <text class="ch-label" x="${left - 14}" y="${y + 5}" text-anchor="end">${p.pair}</text>
      ${moved ? `<path class="ch-link" d="M${X(p.before)} ${y}H${X(p.after)}"/>` : ""}
      <circle class="ch-before" cx="${X(p.before)}" cy="${y}" r="5.5"><title>${p.pair} before: ${f1(p.before)} (${p.beforeOff > 0 ? "+" : ""}${f1(p.beforeOff)} % against "no")</title></circle>
      <circle class="ch-after" cx="${X(p.after)}" cy="${y}" r="5"><title>${p.pair} after: ${f1(p.after)} (${p.afterOff > 0 ? "+" : ""}${f1(p.afterOff)} %)${p.kern ? `, tightened ${p.kern}` : ""}</title></circle>
      <text class="ch-value" x="${W - right + 12}" y="${y + 5}">${f1(p.after)}</text>
      <rect class="ch-hit" x="0" y="${y - rowH / 2}" width="${W}" height="${rowH}"><title>${p.pair}: before ${f1(p.before)}, after ${f1(p.after)}${p.kern ? `, tightened ${p.kern} units` : ""}</title></rect>
    </g>`;
  }).join("");
  return `<figure class="chart">
    <div class="legend" aria-hidden="true"><span><i class="lg-before"></i>Before (P3.1)</span><span><i class="lg-after"></i>After</span><span><i class="lg-band"></i>"no" rhythm ${f1(s.reference)} ± ${Math.round(s.tolerance * 100)} %</span></div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="White area per letter pair, before and after re-spacing, against the font's own rhythm. The table below gives every value.">
      <rect class="ch-band" x="${X(lo)}" y="${top - 6}" width="${r(X(hi) - X(lo))}" height="${H - 26 - top + 6}"/>
      <path class="ch-band-edge" d="M${X(lo)} ${top - 6}V${H - 26}M${X(hi)} ${top - 6}V${H - 26}"/>
      ${ticks}
      <path class="ch-ref" d="M${X(s.reference)} ${top - 10}V${H - 26}"/>
      <text class="ch-tick" x="${X(s.reference)}" y="${top - 16}" text-anchor="middle">no ${f1(s.reference)}</text>
      ${marks}
    </svg>
    <figcaption>Mean white per scanline between each pair (master units, cap height 100), measured from the baseline to the x-height and capped at ${SPACING.depth} per line. Open counters count as the cap, which is why fS and Sy stay high. The table below the chart has every value.</figcaption>
  </figure>`;
}

// ---------- page ----------
export function board({ data, word, wordBefore, endorse, L, rasters }) {
  const final = mark();
  const s = data.spacing;
  const share = Object.fromEntries(data.shares.map((x) => [x.id, x]));
  const rec = share[RECOMMENDED];
  const fit = data.pixelFit;
  const ds = data.darkSplit;
  const nf = data.notFive, nf32 = data.notFive32;
  const c = Object.fromEntries(data.contrasts.map((x) => [x.label, x.ratio]));
  const fitRow = Object.fromEntries(fit.map((x) => [x.px, x]));
  const lockSvg = (kind, label, cls = "") => `<svg class="lk lk--${kind} ${cls}" viewBox="${kind === "symbol" ? "0 0 100 100" : L.vb[kind]}" role="img" aria-label="${label}">${lockupInner(kind, word, endorse, L)}</svg>`;
  const wordSvg = (w, cls, label) => `<svg class="${cls}" viewBox="0 -10 ${r(w.bounds.x1)} 142" role="img" aria-label="${label}"><g class="w">${w.glyphs.filter(Boolean).map((d) => `<path d="${d}"/>`).join("")}</g></svg>`;
  const fi = WORDMARK.text.indexOf("f");
  const fDetail = (w, label) => {
    const fb = pathBounds(w.glyphs[fi]);
    const x0 = r(fb.x0 - 14), wd = r(fb.x1 - fb.x0 + 44);
    return `<svg class="fdetail" viewBox="${x0} -14 ${wd} 128" role="img" aria-label="${label}"><path class="ch-grid" d="M${x0} 100H${r(x0 + wd)}M${x0} 0H${r(x0 + wd)}"/><g class="w">${w.glyphs.filter(Boolean).map((d) => `<path d="${d}"/>`).join("")}</g></svg>`;
  };

  const f16 = mark(RECOMMENDED, 16).f;
  const variantCard = (v) => {
    const x = share[v.id];
    const isRec = v.id === RECOMMENDED;
    const copy = {
      "a-cut-piece": ["Verdigris is only the piece of the spine that the channel cuts off: the colour changes exactly at the cut, as it does in TecHaust's mark.", "the accent and the device say one thing, and the S reads as one ink letter with a lit cut.", `at 16 px the accent is a small flick, ${f16.h} rows of ${16 - f16.g} to ${16 - f16.g + f16.h} px, so it is felt more than seen.`],
      "b-lower-bowl": ["Verdigris turns the lower bowl: the spine end after the cut and the lower stem.", "still a clear shape at 16 px, and it starts at the cut.", "the verdigris hook reads as a second figure, a reversed 7, and pulls the weight to the lower right."],
      "c-lower-terminal": ["Verdigris is the bottom bar's free end and its spur, the shelf the S stands on.", "the clearest shelf idea of the three.", "the channel now splits ink from ink, so the colour change is a butt joint away from the cut, and it is the largest share."],
    }[v.id];
    return `<article class="variant${isRec ? " variant--rec" : ""}" aria-labelledby="v-${v.id}">
      <h3 id="v-${v.id}"><span class="vletter">${letter(v.id)}</span> ${v.name}${isRec ? ' <span class="rec-tag">Recommended</span>' : ""}</h3>
      <div class="variant-art">
        ${smallPlate(mark(v.id), `Variant ${letter(v.id)}, ${v.name}, vector`)}
        <div class="pair16">${zoom(`var-${v.id}-16`, "light", 96, `Variant ${letter(v.id)} at 16 px on light, enlarged`, false)}${zoom(`var-${v.id}-16`, "dark", 96, `Variant ${letter(v.id)} at 16 px on dark, enlarged`, false)}</div>
      </div>
      <dl class="facts">
        <div><dt>Verdigris share</dt><dd>${pct(x.share)}</dd></div>
        <div><dt>At 16 px</dt><dd>${pct(x.share16)}</dd></div>
        <div><dt>Ink to verdigris without a gap</dt><dd>${ds[v.id].jointEdges} px at 16 px</dd></div>
      </dl>
      <p>${copy[0]}</p>
      <p><strong>Strongest:</strong> ${copy[1]}</p>
      <p><strong>Weakest:</strong> ${copy[2]}</p>
      <p class="file"><a href="variant-${v.id}.svg">variant-${v.id}.svg</a></p>
    </article>`;
  };

  const sizesRow = [64, 48, 32, 24, 20, 16].map((px) => {
    return `<figure class="fitcell">
      <div class="fit-zoom">${zoom(`final-${px}`, "light", 192, `Final symbol at ${px} px, light, enlarged`, px <= 32)}${zoom(`final-${px}`, "dark", 192, `Final symbol at ${px} px, dark, enlarged`, px <= 32)}</div>
      <div class="fit-actual"><span class="tone-light-bg">${actual(`final-${px}`, "light", px, `Final symbol at ${px} device pixels, light`)}</span><span class="tone-dark-bg">${actual(`final-${px}`, "dark", px, `Final symbol at ${px} device pixels, dark`)}</span></div>
      <figcaption><strong>${px} px</strong>${px === 20 || px === 24 ? ` (the tray icon at ${px === 20 ? 125 : 150} % display scale)` : ""}, enlarged by a whole number of device pixels per pixel${px <= 32 ? ", with the pixel grid" : ""}. Right: drawn at exactly ${px} device pixels.</figcaption>
    </figure>`;
  }).join("");

  const fitTable = `<table class="data"><caption>Pixel fit per size (all values in pixels; "/" = the cut runs bottom-left to top-right)</caption>
    <thead><tr><th scope="col">Size</th><th scope="col">Vertical</th><th scope="col">Horizontal</th><th scope="col">Spur</th><th scope="col">Channel run</th><th scope="col">Channel square to cut</th><th scope="col">Against the stroke</th><th scope="col">Counters, upper / lower</th><th scope="col">Every edge on a whole pixel</th><th scope="col">Both cuts 45° "/"</th></tr></thead>
    <tbody>${fit.map((x) => `<tr><th scope="row">${x.px}</th><td>${x.v}</td><td>${x.h}${x.thinned ? " (1 px thinner, see above)" : ""}</td><td>${x.spur}</td><td>${x.channelRun}</td><td>${x.channelSquare.toFixed(2)}</td><td>${f1(x.channelVsStroke)} %</td><td>${x.upperCounter} / ${x.lowerCounter}</td><td>${x.whole ? "Yes" : "No"} (${x.coords} coordinates)</td><td>${x.diagonals45slash ? "Yes" : "No"} (${x.diagonals} edges)</td></tr>`).join("")}</tbody></table>`;

  const pairTable = `<table class="data"><caption>White area per pair, master units (cap height 100). Reference "no" = ${f1(s.reference)}; outliers are more than ${Math.round(s.tolerance * 100)} % off.</caption>
    <thead><tr><th scope="col">Pair</th><th scope="col">Before</th><th scope="col">Off "no"</th><th scope="col">Tightened by</th><th scope="col">After</th><th scope="col">Off "no"</th><th scope="col">Scanlines open (after)</th><th scope="col">Closest approach, before / after</th></tr></thead>
    <tbody>${s.pairs.map((p) => `<tr><th scope="row">${p.pair}</th><td>${f1(p.before)}</td><td>${p.beforeOff > 0 ? "+" : ""}${f1(p.beforeOff)} %</td><td>${p.kern || "–"}</td><td>${f1(p.after)}</td><td>${p.afterOff > 0 ? "+" : ""}${f1(p.afterOff)} %</td><td>${p.openAfter} %</td><td>${f1(p.closestBefore)} / ${f1(p.closestAfter)}</td></tr>`).join("")}</tbody></table>`;

  const contrastTable = `<table class="data"><caption>Contrast ratios (WCAG 2.2 formula, from the token values)</caption>
    <thead><tr><th scope="col">Pair</th><th scope="col">Ratio</th><th scope="col">Needed (non-text, 1.4.11)</th></tr></thead>
    <tbody>${data.contrasts.map((x) => `<tr><th scope="row">${x.label}</th><td>${x.ratio.toFixed(2)} : 1</td><td>${x.label.startsWith("Halves") ? "not required: the halves are told apart by the channel" : x.ratio >= 3 ? "3 : 1, passes" : "3 : 1, misses"}</td></tr>`).join("")}</tbody></table>`;

  const ratiosTable = `<table class="data"><caption>Construction ratios (vector, 100-unit grid)</caption><tbody>
    <tr><th scope="row">Vertical stroke</th><td>${MARK.v}</td></tr>
    <tr><th scope="row">Horizontal stroke</th><td>${MARK.h} (${f1(data.ratios.horizontalThinner)} % thinner)</td></tr>
    <tr><th scope="row">Channel, square to the cut / horizontal run</th><td>${MARK.v} / ${data.ratios.channelRun} (100 % of the stroke)</td></tr>
    <tr><th scope="row">Cut ends (ink / verdigris)</th><td>${final.f.a} / ${final.f.g}</td></tr>
    <tr><th scope="row">Spine centre</th><td>${MARK.cy} (1.5 above centre)</td></tr>
    <tr><th scope="row">Spur</th><td>${MARK.spur} (${f1(data.ratios.spurVsStroke)} % of the stroke); openings ${r(final.f.y0 - MARK.h - MARK.spur)} upper / ${r(final.f.b0 - final.f.y1 - MARK.spur)} lower</td></tr>
    <tr><th scope="row">Lockup</th><td>symbol ${LOCKUP.markScale} × cap height, centred on the caps; gap ${LOCKUP.gap} (two strokes); clear space ${L.stroke} (one stroke)</td></tr>
    <tr><th scope="row">Wordmark</th><td>Archivo wght ${WORDMARK.axes.wght}, wdth ${WORDMARK.axes.wdth}; tracking ${WORDMARK.tracking} font units; f-crossbar cut ${word.cut.height} (the full bar); width ${f1(word.bounds.x1)} (was ${f1(wordBefore.bounds.x1)})</td></tr>
    <tr><th scope="row">Endorsement</th><td>IBM Plex Mono 500 caps, cap height ${endorse.cap} (${ENDORSE.capRatio} × the wordmark's), tracking ${ENDORSE.tracking} em, cap line one stroke below the baseline</td></tr>
  </tbody></table>`;

  const calTable = `<table class="data"><caption>Method check: the same measurement on TecHaust's own wordmark against its published values (docs/11 §2.3)</caption>
    <thead><tr><th scope="col">Pair</th><th scope="col">TecHaust published</th><th scope="col">This method</th><th scope="col">Difference</th></tr></thead>
    <tbody>${data.calibration.rows.map((x) => `<tr><th scope="row">${x.pair}</th><td>${f1(x.published)}</td><td>${f1(x.ours)}</td><td>${x.diff > 0 ? "+" : ""}${f1(x.diff)}</td></tr>`).join("")}</tbody></table>`;

  const checks = [
    ["Pass", "Solid blocks on a 100-unit grid", `Every edge is on the grid except the two cut ends (${final.f.a} and ${final.f.g}), which follow from a one-stroke channel at 45°, as TecHaust's 73.13 does.`],
    ["Pass", "One decorative device: the 45° cut, one stroke wide", `One channel, ${MARK.v} square to the cut at every vector size; ${fit.map((x) => `${f1(x.channelVsStroke)} %`).join(", ")} of the stroke at ${fit.map((x) => x.px).join(", ")} px (the build checks the vector channel equals the stroke). The spurs are square letter terminals, not a second device.`],
    ["Note", "Horizontals about 8 % thinner", `${MARK.h} against ${MARK.v} (${f1(data.ratios.horizontalThinner)} %). Pixel-fitted: ${fitRow[64].h}/${fitRow[64].v} at 64 px, ${fitRow[48].h}/${fitRow[48].v} at 48 px, equal at 32 px (TecHaust's rule), and ${fitRow[16].h}/${fitRow[16].v} at 16 px, where the S needs the room for its spurs (step 5). The build checks 7 to 9 % in the vector and thinner horizontals at 40 px and above.`],
    ["Pass", "Ink base, verdigris accent, never swapped", `Verdigris is ${pct(rec.share)} of the inked area (was ${pct(share["p3.1"].share)}).`],
    ["Pass", "On dark: mist and verdigris-300", `${c["Mist on ink-900 (dark app bar)"]} and ${c["Verdigris-300 on ink-900"]} : 1 on ink-900.`],
    ["Pass", "Works at 16 px, pixel-fitted at 64 px and below", `Every coordinate is a whole pixel at ${fit.map((x) => x.px).join(", ")} px, both cuts are 45° "/", and every spur and opening is at least 2 px; the build checks all of it.`],
    ["Pass", "No arrows, circles of arrows, clouds or tick boxes", "None. The channel crosses the spine, so it never makes an arrowhead."],
    ["Pass", "Wordmark: Archivo 620 / 116 %, outlined, f-crossbar cut", `Outlined with HarfBuzz; the f crossbar is cut "/" at 45° across its full ${word.cut.height}-unit height (checked by the build); tracking and five pair kerns are numbers in the geometry.`],
    ["Pass", "Endorsement in IBM Plex Mono caps at caption size", `Outlined; it reaches 12 px (caption size) when the endorsed lockup is ${Math.ceil(L.minimum.endorsedWidth)} px wide, so that is its minimum.`],
    ["Pass", "Clear space of one stroke", `${L.stroke} units at lockup scale (19 × ${LOCKUP.markScale}), shown below.`],
    ["Misses", "Minimum sizes: primary 96 px wide, symbol 16 px", `At 96 px wide the primary's symbol is only ${L.minimum.markAtPrimaryMin} px and its cap height ${L.minimum.capAtPrimaryMin} px, under the symbol's own 16 px minimum. The primary needs ${Math.ceil(L.minimum.primaryWidthForSymbolMin)} px for a 16 px symbol (suggested change to 05, not made).`],
    ["Pass", "Colour versions: on light, on dark, one colour", "All three are drawn for all four lockups; the white and black one-colour files come with the asset set (P3.3)."],
    ["Pass", "Owner: concept 2, S-cut, is the logo", "Refined, not redrawn: same blocks, channel and proportions as P3.1."],
    ["Pass", "Owner: verdigris clearly the smaller part", `${pct(rec.share)} (variant A, recommended); the alternatives are ${pct(share["b-lower-bowl"].share)} and ${pct(share["c-lower-terminal"].share)}.`],
    ["Pass", "Owner: the f crossbar carries the 45° cut, one stroke wide", `The cut runs across the whole bar (${word.cut.height} units), the same construction as TecHaust's T bar.`],
    ["Pass", "Owner: the cut always runs \"/\"", `The build checks both channel edges at every pixel size, and the f cut's direction ("/"), angle (45°) and height (the full ${word.cut.height}-unit bar). The vector channel edges are drawn from the same frame and are checked visually on the plate.`],
    ["Pass", "Owner: HarfBuzz and fontverter from techaust_platform, read and run only", "Imported from its node_modules by path; nothing written there, nothing installed."],
  ];

  const tray = (tone) => `<div class="taskbar taskbar--${tone}" role="img" aria-label="Sample Windows 11 taskbar, ${tone}, with the ShelfSync tray icon">
      <span class="tb-neighbour" aria-hidden="true"></span><span class="tb-neighbour tb-neighbour--round" aria-hidden="true"></span>
      <span class="tb-slot">${actual("tray", tone, 16, "")}</span>
      <span class="tb-neighbour" aria-hidden="true"></span>
      <span class="tb-clock" aria-hidden="true"><span>14:05</span><span>26/10/2026</span></span>
    </div>`;

  const raster = JSON.stringify(rasters);

  return `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShelfSync logo, refined (P3.2)</title>
<style>
/* Patina tokens, copied once from techaust_platform packages/ui/tokens/tokens.json (identity "Patina", 2026-10-06).
   brand/tokens.json does not exist yet (P3.3); every colour on this board comes from these custom properties. */
:root {
${Object.entries(PALETTE).map(([k, v]) => `  --${k}: ${v}; /* palette.${k} */`).join("\n")}
  /* Mock Windows 11 taskbar surfaces, mixed from the white and black tokens (no Patina token matches Windows' greys). */
  --taskbar-light: color-mix(in srgb, var(--white) 95%, var(--black));
  --taskbar-dark: color-mix(in srgb, var(--black) 87.5%, var(--white));
  /* Type and space, from tokens.json text / space (docs/05 3-4). */
  --text-display-2: 36px; --text-h2: 28px; --text-h3: 24px; --text-h4: 20px; --text-body: 16px; --text-sm: 14px; --text-caption: 12px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px; --space-12: 48px; --space-16: 64px;
  --radius-sm: 4px; --radius-md: 8px;
}
@font-face { font-family: "Archivo"; src: url("fonts/archivo-latin.woff2") format("woff2"); font-weight: 400 600; font-stretch: 100% 116%; font-display: swap; }
@font-face { font-family: "IBM Plex Mono"; src: url("fonts/ibm-plex-mono-latin.woff2") format("woff2"); font-weight: 400; font-display: swap; }

/* Semantic tokens (docs/05 2.2). The board follows the system theme; the button overrides it. */
:root, [data-theme="light"] {
  color-scheme: light;
  --color-bg: var(--stone-50); --color-surface: var(--white); --color-surface-alt: var(--stone-100); --color-fill-subtle: var(--stone-200);
  --color-text: var(--ink-900); --color-text-muted: var(--ink-400); --color-text-accent: var(--verdigris-700);
  --color-border: var(--stone-300); --color-border-control: var(--stone-500); --color-focus: var(--verdigris-700);
  --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700); --mark-text: var(--ink-900);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --color-bg: var(--ink-950); --color-surface: var(--ink-800); --color-surface-alt: var(--ink-750); --color-fill-subtle: var(--ink-750);
    --color-text: var(--mist); --color-text-muted: var(--ink-300); --color-text-accent: var(--verdigris-300);
    --color-border: var(--ink-600); --color-border-control: var(--ink-500); --color-focus: var(--verdigris-300);
    --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --mark-text: var(--mist);
  }
}
[data-theme="dark"] {
  color-scheme: dark;
  --color-bg: var(--ink-950); --color-surface: var(--ink-800); --color-surface-alt: var(--ink-750); --color-fill-subtle: var(--ink-750);
  --color-text: var(--mist); --color-text-muted: var(--ink-300); --color-text-accent: var(--verdigris-300);
  --color-border: var(--ink-600); --color-border-control: var(--ink-500); --color-focus: var(--verdigris-300);
  --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --mark-text: var(--mist);
}
/* Fixed tones, whatever the board theme: the brief asks for light, dark and one colour side by side. */
.tone-light { --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700); --mark-text: var(--ink-900); --raster-bg: var(--white); --raster-grid: var(--stone-300);
  --color-text: var(--ink-900); --color-text-muted: var(--ink-400); --color-border: var(--stone-300); }
.tone-dark { --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --mark-text: var(--mist); --raster-bg: var(--ink-900); --raster-grid: var(--ink-600);
  --color-text: var(--mist); --color-text-muted: var(--ink-300); --color-border: var(--ink-600); }
/* Text inside a fixed-tone panel follows the panel, not the board theme (AA in both). */
.panel.tone-light, .panel.tone-mono { color: var(--ink-900); --color-text: var(--ink-900); --color-text-muted: var(--ink-400); }
.panel.tone-dark { color: var(--mist); }
.tone-mono { --mark-base: var(--ink-900); --mark-accent: var(--ink-900); --mark-text: var(--ink-900); --raster-bg: var(--white); --raster-grid: var(--stone-300); }
.tone-mono-dark { --mark-base: var(--mist); --mark-accent: var(--mist); --mark-text: var(--mist); --raster-bg: var(--ink-900); --raster-grid: var(--ink-600); }

* { box-sizing: border-box; }
html { background: var(--color-bg); color: var(--color-text); }
body { margin: 0; font-family: "Archivo", Arial, Helvetica, sans-serif; font-size: var(--text-body); line-height: 1.6; font-variant-numeric: tabular-nums; }
.b { fill: var(--mark-base); }
.a { fill: var(--mark-accent); }
.w { fill: var(--mark-text); }
a { color: var(--color-text); text-underline-offset: 3px; }
a:hover { color: var(--color-text-accent); }
:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; border-radius: 2px; }
.skip { position: absolute; left: -9999px; top: var(--space-2); }
.skip:focus { left: var(--space-2); background: var(--color-surface); padding: var(--space-2) var(--space-3); z-index: 2; }

.board { padding: var(--space-12) var(--space-8) var(--space-16); max-width: 1376px; }
@media (min-width: 1360px) { .board { padding-left: var(--space-16); padding-right: var(--space-16); } }
.board-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-8); margin-bottom: var(--space-10); }
h1 { font-size: var(--text-display-2); font-stretch: 116%; font-weight: 560; line-height: 1.1; margin: 0 0 var(--space-3); letter-spacing: -0.01em; }
.lede { margin: 0; max-width: 72ch; color: var(--color-text-muted); }
.theme-btn { flex: none; min-height: 44px; padding: 0 var(--space-4); border-radius: var(--radius-md); border: 1px solid var(--color-border-control); background: var(--color-surface); color: var(--color-text); font: 500 var(--text-sm)/1 "Archivo", Arial, sans-serif; cursor: pointer; display: inline-flex; align-items: center; gap: var(--space-2); }
.theme-btn:hover { border-color: var(--color-text); }
.theme-btn svg { width: 16px; height: 16px; }

section { border-top: 2px solid var(--color-text); padding-top: var(--space-4); margin-top: var(--space-16); }
h2 { font-size: var(--text-h2); font-stretch: 116%; font-weight: 560; line-height: 1.15; margin: 0 0 var(--space-3); display: flex; gap: var(--space-3); align-items: baseline; }
h2 .step { font-size: var(--text-sm); font-stretch: 100%; font-weight: 500; color: var(--color-text-muted); min-width: 2ch; }
.intro { max-width: 72ch; margin: 0 0 var(--space-8); }
.intro + .intro { margin-top: calc(-1 * var(--space-6)); }
h3 { font-size: var(--text-h4); font-weight: 600; line-height: 1.3; margin: 0 0 var(--space-3); }
figure { margin: 0; }
figcaption { margin-top: var(--space-3); font-size: var(--text-sm); line-height: 1.45; color: var(--color-text-muted); max-width: 72ch; }
.file, .mono { font-family: "IBM Plex Mono", Consolas, monospace; font-size: var(--text-sm); }
.file { margin: var(--space-3) 0 0; }

/* hero */
.hero { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: var(--space-8); align-items: start; }
.plate { display: block; width: 100%; max-width: 440px; height: auto; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.plate .grid, .vplate .grid { stroke: var(--color-border); stroke-width: 1; vector-effect: non-scaling-stroke; fill: none; }
.plate .frame { stroke: var(--color-border-control); stroke-width: 1; vector-effect: non-scaling-stroke; fill: none; }
.plate .dim path { stroke: var(--color-text); stroke-width: 1.25; vector-effect: non-scaling-stroke; fill: none; }
.plate .dim .centre { stroke-dasharray: 3 3; stroke: var(--color-text-muted); }
.plate .dim-label { font: 500 4.8px "Archivo", Arial, sans-serif; fill: var(--color-text); paint-order: stroke; stroke: var(--color-surface); stroke-width: 1.4px; }
.panels { display: grid; gap: var(--space-3); }
.panel { border-radius: var(--radius-md); padding: var(--space-8); }
.panel.tone-light { background: var(--white); border: 1px solid var(--color-border); }
.panel.tone-dark { background: var(--ink-900); border: 1px solid var(--ink-600); }
.panel.tone-mono { background: var(--white); border: 1px solid var(--color-border); }
.lk { display: block; height: auto; overflow: visible; }
.hero .lk--primary { width: 100%; }

/* variants */
.variants { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-8); }
.variant { border-top: 1px solid var(--color-border); padding-top: var(--space-4); min-width: 0; }
.variant--rec { border-top: 3px solid var(--color-text-accent); padding-top: calc(var(--space-4) - 2px); }
.variant h3 { display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
.vletter { color: var(--color-text-muted); font-weight: 500; }
.rec-tag { font-size: var(--text-caption); font-weight: 600; letter-spacing: 0.02em; color: var(--color-text-accent); border: 1px solid currentColor; border-radius: var(--radius-sm); padding: 0 var(--space-2); line-height: 20px; }
.variant-art { display: flex; gap: var(--space-4); align-items: flex-start; flex-wrap: wrap; }
.vplate { width: 120px; height: 120px; flex: none; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.pair16 { display: inline-flex; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
.facts { display: grid; grid-template-columns: repeat(3, auto); gap: var(--space-2) var(--space-6); margin: var(--space-4) 0; justify-content: start; }
.facts dt { font-size: var(--text-caption); color: var(--color-text-muted); line-height: 1.4; }
.facts dd { margin: 0; font-size: var(--text-h4); font-weight: 600; line-height: 1.3; }
.variant p { font-size: var(--text-sm); line-height: 1.5; margin: 0 0 var(--space-2); }
.before-note { margin-top: var(--space-6); font-size: var(--text-sm); color: var(--color-text-muted); display: flex; gap: var(--space-4); align-items: center; }
.before-note .vplate { width: 72px; height: 72px; }

/* rasters */
canvas.rz, canvas.ra { display: block; image-rendering: pixelated; }
canvas.rz { box-sizing: content-box; padding: var(--space-4); background: var(--raster-bg); }
.pair16 canvas.rz { padding: var(--space-3); }
.compare { display: flex; flex-wrap: wrap; gap: var(--space-8); }
.compare figure { flex: none; }
.compare .pairz { display: inline-flex; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
.compare figcaption { max-width: 384px; }
.fits { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-8) var(--space-8); }
.fitcell { min-width: 0; }
.fit-zoom { display: inline-flex; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; vertical-align: top; }
.fit-actual { display: inline-flex; flex-direction: column; gap: 0; margin-left: var(--space-4); vertical-align: top; border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
.fit-actual span { display: grid; place-items: center; padding: var(--space-3); }
.tone-light-bg { background: var(--white); }
.tone-dark-bg { background: var(--ink-900); }

/* rows for the dark split */
.rows { list-style: none; padding: 0; margin: var(--space-3) 0 0; font-size: var(--text-sm); }

/* wordmark */
.wm-pair { display: grid; gap: var(--space-3); }
.wm { display: block; width: 100%; height: auto; }
.wm-row { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: var(--space-4); align-items: center; }
.wm-row .label { font-size: var(--text-sm); color: var(--color-text-muted); }
.fdetails { display: flex; gap: var(--space-4); margin-top: var(--space-6); flex-wrap: wrap; }
.fdetails figure { flex: none; }
.fdetail { display: block; width: 280px; height: auto; background: var(--white); border: 1px solid var(--color-border); border-radius: var(--radius-md); --mark-text: var(--ink-900); }
.fdetail .ch-grid { stroke: var(--stone-300); }
.side { margin: 0 0 var(--space-4); max-width: 60ch; }
.split2 { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); gap: var(--space-8); align-items: start; margin-top: var(--space-8); }

/* chart (dataviz: thin marks, recessive grid, legend, direct labels for values, table view below) */
.chart { overflow-x: auto; }
.chart svg { display: block; width: 100%; min-width: 560px; height: auto; max-width: 640px; font-family: "Archivo", Arial, sans-serif; }
.ch-grid { stroke: var(--color-border); stroke-width: 1; }
.ch-band { fill: var(--color-fill-subtle); }
.ch-band-edge { stroke: var(--color-border-control); stroke-width: 1; }
.ch-ref { stroke: var(--color-text-muted); stroke-width: 1.5; stroke-dasharray: 4 3; }
.ch-tick { fill: var(--color-text-muted); font-size: 14px; }
.ch-label { fill: var(--color-text); font-size: 15px; font-weight: 600; }
.ch-value { fill: var(--color-text); font-size: 15px; }
.ch-link { stroke: var(--color-text-muted); stroke-width: 2; }
.ch-before { fill: var(--color-bg); stroke: var(--color-text-muted); stroke-width: 2; }
.ch-after { fill: var(--color-text); stroke: var(--color-bg); stroke-width: 2; }
.ch-hit { fill: transparent; }
.ch-row:hover .ch-label { text-decoration: underline; }
.legend { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-6); font-size: var(--text-sm); margin-bottom: var(--space-2); }
.legend span { display: inline-flex; align-items: center; gap: var(--space-2); }
.legend i { display: inline-block; width: 12px; height: 12px; }
.lg-before { border: 2px solid var(--color-text-muted); border-radius: 50%; }
.lg-after { background: var(--color-text); border-radius: 50%; }
.lg-band { background: var(--color-fill-subtle); border: 1px solid var(--color-border-control); width: 16px !important; }

/* lockups */
.lockgrid { display: grid; grid-template-columns: 160px repeat(3, minmax(0, 1fr)); gap: var(--space-3); align-items: stretch; }
.lockgrid .rowhead { font-size: var(--text-sm); font-weight: 600; align-self: center; }
.lockgrid .colhead { font-size: var(--text-sm); color: var(--color-text-muted); }
.lockgrid .panel { padding: var(--space-6); display: grid; place-items: center start; min-height: 120px; }
.lockgrid .lk--primary { width: 100%; max-width: 300px; }
.lockgrid .lk--endorsed { width: 100%; max-width: 300px; min-width: ${Math.ceil(L.minimum.endorsedWidth)}px; } /* never below its own minimum */
.lockgrid .lk--wordmark { width: 100%; max-width: 240px; }
.lockgrid .lk--symbol { width: 56px; }
.clear { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); gap: var(--space-8); margin-top: var(--space-10); align-items: start; }
.clearsvg { display: block; width: 100%; height: auto; background: var(--white); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.clearsvg .zone { fill: var(--verdigris-100); }
.clearsvg .edge { fill: none; stroke: var(--verdigris-700); stroke-width: 1; vector-effect: non-scaling-stroke; stroke-dasharray: 4 3; }
.clearsvg .lbl { font: 500 14px "Archivo", Arial, sans-serif; fill: var(--ink-900); }
.mins { display: grid; gap: var(--space-4); }
.mins .panel { padding: var(--space-6); display: flex; align-items: center; gap: var(--space-6); flex-wrap: wrap; }
.mins .m96 { width: 96px; }
.mins .m121 { width: ${Math.ceil(L.minimum.primaryWidthForSymbolMin)}px; }
.mins .m16 { width: 16px; }
.mins .cap { font-size: var(--text-sm); color: var(--ink-400); }

/* taskbar */
.taskbars { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-6); max-width: 880px; }
.taskbar { height: 48px; display: flex; align-items: center; justify-content: flex-end; padding: 0 var(--space-3); border-radius: var(--radius-sm); }
.taskbar--light { background: var(--taskbar-light); color: var(--ink-900); border: 1px solid var(--stone-300); --mark-base: var(--ink-900); --mark-accent: var(--verdigris-700); --raster-bg: var(--taskbar-light); --neighbour: var(--stone-500); }
.taskbar--dark { background: var(--taskbar-dark); color: var(--mist); border: 1px solid var(--ink-600); --mark-base: var(--mist); --mark-accent: var(--verdigris-300); --raster-bg: var(--taskbar-dark); --neighbour: var(--ink-500); }
.tb-slot, .tb-neighbour { width: 32px; height: 32px; display: grid; place-items: center; flex: none; }
.taskbar .tb-slot canvas { --raster-bg: inherit; } /* the icon's background is the taskbar, not the tone panel colour */
.tb-neighbour::before { content: ""; width: 16px; height: 12px; border: 2px solid var(--neighbour); border-radius: 3px; }
.tb-neighbour--round::before { width: 14px; height: 14px; border-radius: 50%; }
.tb-clock { display: flex; flex-direction: column; align-items: flex-end; margin-left: var(--space-3); font-size: var(--text-caption); line-height: 16px; }

/* tables */
.tables { display: grid; gap: var(--space-10); }
table.data { border-collapse: collapse; width: 100%; font-size: var(--text-sm); line-height: 1.45; }
table.data caption { text-align: left; font-weight: 600; font-size: var(--text-body); padding-bottom: var(--space-3); }
table.data th, table.data td { text-align: left; padding: var(--space-2) var(--space-3) var(--space-2) 0; border-top: 1px solid var(--color-border); vertical-align: top; }
table.data thead th { font-size: var(--text-caption); font-weight: 500; color: var(--color-text-muted); border-top: 0; letter-spacing: 0.02em; }
table.data tbody th { font-weight: 500; }
.scroll { overflow-x: auto; }

/* rule checks */
.checks { list-style: none; margin: 0; padding: 0; font-size: var(--text-sm); line-height: 1.5; max-width: 112ch; }
.checks li { display: grid; grid-template-columns: 88px minmax(0, 1fr); column-gap: var(--space-4); padding: var(--space-3) 0; border-top: 1px solid var(--color-border); }
.checks p { margin: 0; }
.rule { font-weight: 600; }
.note { color: var(--color-text-muted); }
.verdict { font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
.verdict::before { content: ""; display: inline-block; width: 8px; height: 8px; }
.verdict--pass::before { background: currentColor; }
.verdict--note::before { border: 2px solid currentColor; width: 8px; height: 8px; }
.verdict--misses::before { border: 2px solid currentColor; transform: rotate(45deg); width: 7px; height: 7px; }

.board-foot { margin-top: var(--space-16); padding-top: var(--space-6); border-top: 1px solid var(--color-border); max-width: 80ch; font-size: var(--text-sm); color: var(--color-text-muted); }
.board-foot p { margin: 0 0 var(--space-2); }

@media (max-width: 1180px) {
  .variants { grid-template-columns: minmax(0, 1fr); max-width: 640px; }
  .split2 { grid-template-columns: minmax(0, 1fr); }
  .lockgrid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .lockgrid .corner { display: none; }
  .lockgrid .rowhead { grid-column: 1 / -1; margin-top: var(--space-3); }
  .lockgrid .panel { padding: var(--space-4); }
}
@media (max-width: 1000px) {
  .hero, .split2, .clear, .fits { grid-template-columns: minmax(0, 1fr); }
  .taskbars { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 900px) {
  .lockgrid { grid-template-columns: minmax(0, 1fr); }
  .lockgrid .colhead { display: none; }
  .board { padding-left: var(--space-4); padding-right: var(--space-4); }
}
@media (max-width: 600px) {
  .board-head { flex-direction: column; gap: var(--space-4); }
  .compare figure { flex: 1 1 100%; min-width: 0; }
  .compare .pairz, .fit-zoom { display: flex; flex-wrap: wrap; width: fit-content; max-width: 100%; }
  .fit-actual { margin: var(--space-3) 0 0; }
  .compare figcaption { max-width: none; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<a class="skip" href="#main">Skip to the board</a>
<div class="board">
  <header class="board-head">
    <div>
      <h1>ShelfSync logo, refined</h1>
      <p class="lede">P3.2 refines concept 2, S-cut. Verdigris becomes the accent, the S stops reading as a 5, the split holds on dark at 16 px, every size is pixel-fitted, and the wordmark takes the f-crossbar cut. Every number and shape on this page is generated from <span class="mono">brand/draft/geometry.mjs</span>.</p>
    </div>
    <button class="theme-btn" id="theme" type="button" aria-pressed="false"><svg viewBox="0 0 16 16" aria-hidden="true"><path class="b" d="M8 1a7 7 0 1 0 0 14Z"/><path d="M8 1a7 7 0 0 1 0 14" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><span>Dark board</span></button>
  </header>

  <main id="main">
  <div class="hero">
    <figure>
      ${plate(final)}
      <figcaption>The final symbol (variant A) on its 100-unit grid. Strokes ${MARK.v} and ${MARK.h}; the channel is ${MARK.v} measured square to the "/" cut; the spurs turn ${MARK.spur}; the spine is centred ${r(MARK.size / 2 - MARK.cy)} above the middle. File: <a class="mono" href="symbol.svg">symbol.svg</a>.</figcaption>
    </figure>
    <div class="panels">
      <div class="panel tone-light">${lockSvg("primary", "ShelfSync primary lockup on light")}</div>
      <div class="panel tone-dark">${lockSvg("primary", "ShelfSync primary lockup on dark")}</div>
    </div>
  </div>

  <section aria-labelledby="s2">
    <h2 id="s2"><span class="step">2</span> Colour split</h2>
    <p class="intro">P3.1 gave verdigris ${pct(share["p3.1"].share)} of the inked area. Three ways to make it the accent, all with ink as the base and the channel unchanged. Share is measured on the vector (exact polygon areas) and on the 16 px raster.</p>
    <div class="variants">${VARIANTS.map(variantCard).join("")}</div>
    <p class="before-note">${smallPlate(mark("p3.1"), "P3.1 concept 2, before")}<span>Before: P3.1 concept 2, verdigris on the whole lower block, ${pct(share["p3.1"].share)}.</span></p>
    <p class="intro" style="margin-top:var(--space-6)"><strong>Recommended: A, cut piece.</strong> It is the only split where verdigris is exactly what the cut produces, so the one device and the one accent coincide, as in TecHaust's mark; at ${pct(rec.share)} it is clearly an accent; and on dark nothing about the S's shape depends on the colour. The rest of the board carries A.</p>
  </section>

  <section aria-labelledby="s3">
    <h2 id="s3"><span class="step">3</span> Not a 5</h2>
    <p class="intro">A square S drawn from blocks is the same figure as a square 5. The fix stays inside the construction: the top terminal turns down and the bottom terminal turns up, by a spur of ${MARK.spur} units (round(0.09 × size) px, at least 2 px so it reads as a turn and not as a thicker bar end). A 5 never turns its top bar down, and the turned ends make the S point-symmetric. At 16 px that needs room: see the pixel-fitting rule in step 5. Shown in one colour, so only the shape is compared.</p>
    <div class="compare">
      <figure><div class="pairz">${zoom("five-16", "mono", 160, "A square 5 with P3.1's strokes at 16 px, enlarged")}${zoom("p31-16", "mono", 160, "P3.1 S at 16 px, enlarged")}</div><figcaption><strong>Before, 16 px.</strong> Left, a square 5 with the same strokes; right, P3.1's S. They differ in ${nf.before} pixels, all of them the channel.</figcaption></figure>
      <figure><div class="pairz">${zoom("five-new-16", "mono", 160, "A square 5 with P3.2's strokes at 16 px, enlarged")}${zoom("final-16", "mono", 160, "P3.2 S at 16 px, enlarged")}</div><figcaption><strong>After, 16 px.</strong> The same comparison at P3.2's fit: ${nf.after} pixels differ, the channel plus two spurs of ${fitRow[16].v} × ${fitRow[16].spur} px. The openings are ${fitRow[16].upperOpening} and ${fitRow[16].lowerOpening} px tall.</figcaption></figure>
      <figure><div class="pairz">${zoom("five-new-32", "mono", 160, "A square 5 at 32 px, enlarged")}${zoom("final-32", "mono", 160, "P3.2 S at 32 px, enlarged")}</div><figcaption><strong>After, 32 px.</strong> ${nf32.after} pixels differ (P3.1: ${nf32.before}); spurs ${fitRow[32].v} × ${fitRow[32].spur} px, openings ${fitRow[32].upperOpening} and ${fitRow[32].lowerOpening} px.</figcaption></figure>
    </div>
  </section>

  <section aria-labelledby="s4">
    <h2 id="s4"><span class="step">4</span> The split on dark at 16 px</h2>
    <p class="intro">Mist against verdigris-300 is ${c["Halves against each other, dark (verdigris-300 / mist)"]} : 1 (lightness L* ${data.deltaE.lightness.mist} against ${data.deltaE.lightness["verdigris-300"]}; they differ mainly in hue, ΔE2000 ${data.deltaE.dark}). So the split must not depend on colour. With variant A, the top and lower blocks are both mist on dark and are separated only by the channel, which at 16 px leaves <strong>${ds[RECOMMENDED].minClear} fully clear background pixels on every spine row</strong> (coverage at most 2 %), edged at ${c["Mist on ink-900 (dark app bar)"]} : 1 and ${c["Verdigris-300 on ink-900"]} : 1 against the ink-900 bar. Both cut edges run through pixel corners, so each edge pixel is exactly half covered and none of them bridges the gap. Verdigris touches mist only along a ${ds[RECOMMENDED].jointEdges} px joint inside the lower block, which the S does not need in order to read.</p>
    <div class="compare">
      <figure><div class="pairz">${zoom("p31-16", "dark", 160, "P3.1 at 16 px on dark, enlarged")}</div><figcaption>Before: the halves are split by colour and gap together; ${ds["p3.1"].minClear} clear pixels per spine row, but half the mark depends on telling mist from verdigris-300.</figcaption></figure>
      <figure><div class="pairz">${zoom("final-16", "dark", 160, "P3.2 variant A at 16 px on dark, enlarged")}</div><figcaption>After: rows ${ds[RECOMMENDED].rows.map((x) => x.row).join(", ")} (the spine) have ${ds[RECOMMENDED].rows.map((x) => x.clear).join(", ")} clear pixels. The channel is ${ds[RECOMMENDED].channelSquare} px square to the cut (${f1(fitRow[16].channelVsStroke)} % of the ${fitRow[16].v} px stroke).</figcaption></figure>
      <figure><div class="pairz">${zoom("final-16", "mono-dark", 160, "P3.2 at 16 px on dark in one colour, enlarged")}</div><figcaption>The same raster with verdigris removed: the S and its channel are unchanged, which is the test that the split does not lean on colour.</figcaption></figure>
    </div>
  </section>

  <section aria-labelledby="s5">
    <h2 id="s5"><span class="step">5</span> Pixel fitting</h2>
    <p class="intro">TecHaust's <span class="mono">pixelMark</span> rule, applied to the S: vertical = round(0.19 × size), at least 2; below 40 px horizontals equal verticals, above it round(0.175 × size); the channel's run is round(vertical × √2), so both cut ends land on whole pixels and the cut stays exactly 45°. The spine top is round(0.485 × size − horizontal / 2). One difference from TecHaust, at 16 px only: the S stacks three horizontals in 16 pixels where TecHaust's TH stacks two, so with 3 px horizontals a 2 px spur would leave a 1 px opening, which closes up at true size. The rule is: if the opening between spur and spine would fall under 2 px, the horizontals lose 1 px. That happens only at 16 px (horizontals 2, verticals 3); at 20, 24, 32, 48 and 64 px TecHaust's rule holds unchanged. The owner's screen runs at 125 %, so each raster is shown enlarged (with its pixel grid up to 32 px) and once at true device size.</p>
    <div class="fits">${sizesRow}</div>
    <div class="scroll" style="margin-top:var(--space-8)">${fitTable}</div>
  </section>

  <section aria-labelledby="s6">
    <h2 id="s6"><span class="step">6</span> Wordmark</h2>
    <p class="intro">Archivo at weight ${WORDMARK.axes.wght} and width ${WORDMARK.axes.wdth} %, tracking ${WORDMARK.tracking} font units, outlined with HarfBuzz. The f crossbar's right end is cut "/" across its whole ${word.cut.height}-unit height, the construction of TecHaust's T bar. Spacing was measured with TecHaust's method (white area per pair against the font's own "no") and five pairs were tightened.</p>
    <div class="wm-pair panel tone-light">
      <div class="wm-row"><span class="label">Before (P3.1)</span>${wordSvg(wordBefore, "wm", "Wordmark before: P3.1, font kerning only")}</div>
      <div class="wm-row"><span class="label">After</span>${wordSvg(word, "wm", "Wordmark after: f-crossbar cut and five re-spaced pairs")}</div>
    </div>
    <div class="fdetails">
      <figure>${fDetail(wordBefore, "The f and S before, enlarged")}<figcaption>f before.</figcaption></figure>
      <figure>${fDetail(word, "The f with its 45 degree crossbar cut, enlarged")}<figcaption>f after: the cut runs ${word.cut.height} across and ${word.cut.height} down.</figcaption></figure>
    </div>
    <div class="split2">
      ${spacingChart(s)}
      <div>
        <p class="side"><strong>How the pairs were set.</strong> Sh, lf and yn were ${f1(s.pairs[0].beforeOff)}, ${f1(s.pairs[3].beforeOff)} and ${f1(s.pairs[6].beforeOff)} % loose and now sit within ${f1(Math.max(Math.abs(s.pairs[0].afterOff), Math.abs(s.pairs[3].afterOff), Math.abs(s.pairs[6].afterOff)))} % of "no" (computed before rounding; from the table's rounded values it is ${f1(Math.max(...[0, 3, 6].map((i) => Math.abs((100 * (Number(f1(s.pairs[i].after)) - Number(f1(s.reference)))) / Number(f1(s.reference))))))} %). fS and Sy are open by nature (${s.pairs[4].openAfter} and ${s.pairs[5].openAfter} % of their scanlines hit the cap, like TecHaust's Te), so they were tightened in whole units only while their closest approach stayed at or above ${WORDMARK.minApproach} units, the tightest in-rhythm pair (yn). They stopped at ${f1(s.pairs[4].closestAfter)} and ${f1(s.pairs[5].closestAfter)}; one more unit would take them to ${f1(s.pairs[4].closestAfter - 1)} and ${f1(s.pairs[5].closestAfter - 1)}, under ${WORDMARK.minApproach}.</p>
        <p class="side">The method was checked first on TecHaust's own wordmark: it reproduces the published values within ${f1(data.calibration.maxDiff)} units (table below).</p>
      </div>
    </div>
    <div class="scroll" style="margin-top:var(--space-6)">${pairTable}</div>
  </section>

  <section aria-labelledby="s7">
    <h2 id="s7"><span class="step">7</span> Lockups</h2>
    <p class="intro">Primary: the symbol at ${LOCKUP.markScale} × the cap height, centred on the caps, then a gap of two strokes (${LOCKUP.gap} units), as TecHaust's lockup. Endorsed: "BY TECHAUST" in IBM Plex Mono 500 caps, cap height ${ENDORSE.capRatio} × the wordmark's, aligned to the wordmark's left edge with its cap line one stroke below the baseline.</p>
    <div class="lockgrid" role="table" aria-label="Lockups in three colour versions">
      <div role="row" style="display:contents"><span class="corner" role="columnheader"></span><span class="colhead" role="columnheader">On light</span><span class="colhead" role="columnheader">On dark</span><span class="colhead" role="columnheader">One colour (ink)</span></div>
      ${[["primary", "Primary"], ["symbol", "Symbol"], ["wordmark", "Wordmark"], ["endorsed", "Endorsed"]].map(([k, n]) => `<div role="row" style="display:contents"><span class="rowhead" role="rowheader">${n}</span>${["light", "dark", "mono"].map((t) => `<div class="panel tone-${t}" role="cell">${lockSvg(k, `${n} lockup, ${t === "mono" ? "one colour" : `on ${t}`}`)}</div>`).join("")}</div>`).join("")}
    </div>
    <div class="clear">
      <figure>
        <svg class="clearsvg" viewBox="${r(-L.stroke - 20)} ${r(L.y0 - L.stroke - 20)} ${r(L.width + 2 * L.stroke + 40)} ${r(L.y1 - L.y0 + 2 * L.stroke + 40)}" role="img" aria-label="Clear space: one mark stroke on every side of the primary lockup">
          <path class="zone" fill-rule="evenodd" d="M${-L.stroke} ${r(L.y0 - L.stroke)}H${r(L.width + L.stroke)}V${r(L.y1 + L.stroke)}H${-L.stroke}ZM0 ${L.y0}V${L.y1}H${L.width}V${L.y0}Z"/>
          <rect class="edge" x="${-L.stroke}" y="${r(L.y0 - L.stroke)}" width="${r(L.width + 2 * L.stroke)}" height="${r(L.y1 - L.y0 + 2 * L.stroke)}"/>
          <g class="tone-light">${lockupInner("primary", word, endorse, L)}</g>
        </svg>
        <figcaption>Clear space: one mark stroke (${L.stroke} units at lockup scale) on every side, shaded.</figcaption>
      </figure>
      <div class="mins">
        <div class="panel tone-light"><svg class="lk m96" viewBox="${L.vb.primary}" role="img" aria-label="Primary lockup at 96 px wide">${lockupInner("primary", word, endorse, L)}</svg><span class="cap">96 px wide (05 minimum): symbol ${L.minimum.markAtPrimaryMin} px</span></div>
        <div class="panel tone-light"><svg class="lk m121" viewBox="${L.vb.primary}" role="img" aria-label="Primary lockup at ${Math.ceil(L.minimum.primaryWidthForSymbolMin)} px wide">${lockupInner("primary", word, endorse, L)}</svg><span class="cap">${Math.ceil(L.minimum.primaryWidthForSymbolMin)} px wide: symbol 16 px (suggested minimum)</span></div>
        <div class="panel tone-light"><span class="tone-light-bg">${actual("final-16", "light", 16, "Symbol at 16 device pixels")}</span><span class="cap">Symbol at 16 px</span></div>
      </div>
    </div>
  </section>

  <section aria-labelledby="s8">
    <h2 id="s8"><span class="step">8</span> Tray icon</h2>
    <p class="intro">Mock Windows 11 taskbars. Windows picks the tray icon by display scale (16 px at 100 %, 20 px at 125 %, 24 px at 150 %, 32 px at 200 %), so the mock draws the fit for this screen's scale from the same rule, at device pixels. The neighbouring icons and the clock are placeholders.</p>
    <div class="taskbars">${tray("light")}${tray("dark")}</div>
    <p class="figcap-like" id="trayfit" style="font-size:var(--text-sm);color:var(--color-text-muted)"></p>
  </section>

  <section aria-labelledby="s9">
    <h2 id="s9">Measurements</h2>
    <div class="tables">
      <div class="scroll">${contrastTable}</div>
      <div class="scroll"><table class="data"><caption>Verdigris share of the inked area</caption><thead><tr><th scope="col">Version</th><th scope="col">Verdigris on</th><th scope="col">Ink (units²)</th><th scope="col">Verdigris (units²)</th><th scope="col">Share, vector</th><th scope="col">Share, 16 px raster</th></tr></thead><tbody>${data.shares.map((x) => `<tr><th scope="row">${x.id === "p3.1" ? x.name : `${letter(x.id)} ${x.name}`}</th><td>${x.what}</td><td>${f1(x.ink)}</td><td>${f1(x.verdigris)}</td><td>${pct(x.share)}</td><td>${pct(x.share16)}</td></tr>`).join("")}</tbody></table></div>
      <div class="scroll">${ratiosTable}</div>
      <div class="scroll">${calTable}</div>
    </div>
  </section>

  <section aria-labelledby="s10">
    <h2 id="s10">Rule checks</h2>
    <p class="intro">Every rule in 05 §1.2–1.3 and every owner decision for P3.2.</p>
    <ul class="checks">${checks.map(([v, rule, note]) => `<li>${verdict(v)}<p><span class="rule">${rule}.</span> <span class="note">${note}</span></p></li>`).join("")}</ul>
  </section>
  </main>

  <footer class="board-foot">
    <p>Files: <a class="mono" href="symbol.svg">symbol.svg</a>, <a class="mono" href="lockup-primary.svg">lockup-primary.svg</a>, <a class="mono" href="lockup-endorsed.svg">lockup-endorsed.svg</a>, <a class="mono" href="lockup-wordmark.svg">lockup-wordmark.svg</a>, the on-dark and one-colour versions, <span class="mono">symbol-16px.svg</span> to <span class="mono">symbol-64px.svg</span> and <a class="mono" href="measurements.json">measurements.json</a>.</p>
    <p>Colours: the Patina palette from TecHaust's <span class="mono">packages/ui/tokens/tokens.json</span>, set once at the top of this page. The two taskbar greys are mixed from the white and black tokens to stand in for Windows 11; the real taskbar is checked with the tray icons (P3.3).</p>
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

  // Rasters: per-pixel coverage computed by brand/draft/raster.mjs (16 x 16 samples per pixel up to 32 px, 8 x 8 above).
  const R = ${raster};
  const dpr = window.devicePixelRatio || 1;
  const col = (el, v) => getComputedStyle(el).getPropertyValue(v).trim();
  function paint(cv, data, px, W, gridOn) {
    const ctx = cv.getContext("2d");
    const bg = col(cv, "--raster-bg"), base = col(cv, "--mark-base"), acc = col(cv, "--mark-accent");
    const e = (i) => Math.round((i * W) / px);
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, W);
    for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
      const i = y * px + x, b = data.base[i], a = data.accent[i];
      const x0 = e(x), y0 = e(y), w = e(x + 1) - x0, h = e(y + 1) - y0;
      if (b > 0) { ctx.globalAlpha = b; ctx.fillStyle = base; ctx.fillRect(x0, y0, w, h); }
      if (a > 0) { ctx.globalAlpha = a; ctx.fillStyle = acc; ctx.fillRect(x0, y0, w, h); }
    }
    ctx.globalAlpha = 1;
    if (gridOn) {
      ctx.fillStyle = col(cv, "--raster-grid"); ctx.globalAlpha = 0.35;
      for (let i = 1; i < px; i++) { ctx.fillRect(e(i), 0, 1, W); ctx.fillRect(0, e(i), W, 1); }
      ctx.globalAlpha = 1;
    }
  }
  for (const cv of document.querySelectorAll("canvas.rz")) {
    const data = R[cv.dataset.r]; const px = Math.round(Math.sqrt(data.base.length));
    // A whole number of device pixels per raster pixel, so every enlarged cell is the same size.
    const size = Number(cv.dataset.size); const W = px * Math.max(1, Math.round((size * dpr) / px));
    cv.width = W; cv.height = W; cv.style.width = W / dpr + "px"; cv.style.height = W / dpr + "px";
    paint(cv, data, px, W, cv.hasAttribute("data-grid"));
  }
  // True size: one raster pixel per device pixel. The tray picks the fit Windows would use at this scale.
  const trayPx = [16, 20, 24, 32].reduce((best, s) => Math.abs(s - 16 * dpr) < Math.abs(best - 16 * dpr) ? s : best, 16);
  for (const cv of document.querySelectorAll("canvas.ra")) {
    const key = cv.dataset.r === "tray" ? "final-" + trayPx : cv.dataset.r;
    const data = R[key]; const px = Math.round(Math.sqrt(data.base.length));
    cv.width = px; cv.height = px; cv.style.width = px / dpr + "px"; cv.style.height = px / dpr + "px";
    paint(cv, data, px, px, false);
    if (cv.dataset.r === "tray") cv.setAttribute("aria-label", "ShelfSync tray icon, the " + px + " px fit at device pixels");
  }
  document.getElementById("trayfit").textContent = "This screen's scale is " + Math.round(dpr * 100) + " %, so the taskbars show the " + trayPx + " px fit, drawn at device pixels.";
})();
</script>
</body>
</html>
`;
}
