// The P3.3 asset review page: docs/05-design-system-appendix/p3.3-brand-assets/index.html, with copies of every
// asset (the appendix server can't reach brand/), the icon frames as PNGs, and the fonts with their OFL licences.
// Every colour on the page is a token from the generated tokens.css; every number comes from the build.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { APP_ICON, FAVICON_ICO_SIZES, GITHUB, INSTALLER, LOCKUPS, MINIMUM, SIZE_LIMIT, TRAY, VERSIONS, mark } from "../geometry.mjs";
import { decodeBmp, decodeIco, decodePng, encodePng } from "./formats.mjs";
import { FONTS } from "./outline.mjs";
import { Canvas } from "./render.mjs";
import { tokens } from "./tokens.mjs";

export const REVIEW_DIR = fileURLToPath(new URL("../../docs/05-design-system-appendix/p3.3-brand-assets/", import.meta.url));

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const f1 = (n) => (Math.round(n * 10) / 10).toFixed(1);
const f2 = (n) => (Math.round(n * 100) / 100).toFixed(2);
const kb = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);
const bytes = (b) => (typeof b === "string" ? Buffer.byteLength(b) : b.length);
const pngOf = (c) => encodePng(c.w, c.h, c.pixels());

const LOCKUP_NAMES = { primary: "Primary", symbol: "Symbol", wordmark: "Wordmark", endorsed: "Endorsed", stacked: "Stacked endorsed", compact: "Compact endorsed" };
/** Display width (CSS px) of each lockup on the page: at or above its minimum. */
const SHOW_WIDTH = { primary: 140, symbol: 48, wordmark: 130, endorsed: 280, stacked: 124, compact: 119 };
const STATE_NAMES = { normal: "Normal", paused: "Paused", attention: "Needs attention" };

/** The size limit that applies to a generated file, for the files table and the tests. */
export function limitFor(f) {
  if (f.startsWith("assets/logo/")) return SIZE_LIMIT.logoSvg;
  if (f.endsWith("favicon.svg")) return SIZE_LIMIT.faviconSvg;
  if (f.endsWith("favicon.ico")) return SIZE_LIMIT.faviconIco;
  if (f.startsWith("assets/tray/")) return SIZE_LIMIT.trayIco;
  if (f.endsWith("shelfsync.ico")) return SIZE_LIMIT.appIco;
  if (f.endsWith(".bmp")) return SIZE_LIMIT.installerBmp;
  if (f.startsWith("assets/installer/")) return SIZE_LIMIT.installerPng;
  if (f.endsWith("social-preview.png")) return SIZE_LIMIT.socialPng;
  if (f.includes("readme-header")) return SIZE_LIMIT.readmePng;
  return null;
}

/** What a file is, read back from its bytes (dimensions, frames). */
export function describe(f, b) {
  if (f.endsWith(".ico")) return decodeIco(b).map((x) => `${x.size}${x.kind === "png" ? " png" : ""}`).join(", ");
  if (f.endsWith(".png")) { const p = decodePng(b); return `${p.width} × ${p.height}${p.colourType === 6 ? ", alpha" : ""}`; }
  if (f.endsWith(".bmp")) { const p = decodeBmp(b); return `${p.width} × ${p.height}, ${p.bpp}-bit`; }
  if (f.endsWith(".svg")) return `viewBox ${/viewBox="([^"]+)"/.exec(b)?.[1] ?? ""}`;
  return "";
}

export async function review({ files, frames, art, facts }) {
  const out = {};
  // Copies of the assets and tokens.css, the frames, the fonts.
  for (const [f, b] of Object.entries(files)) if (f.startsWith("assets/")) out[f] = b;
  out["assets/tokens.css"] = files["generated/tokens.css"];
  for (const [k, fr] of Object.entries(frames)) out[`frames/${k}.png`] = pngOf(fr.canvas);
  { // what favicon.svg shows in a dark browser (the same fitted paths, dark colours)
    const m = mark(16);
    const c = new Canvas(16, 16);
    c.draw([{ d: m.base, color: VERSIONS.dark.base }, { d: m.accent, color: VERSIONS.dark.accent }]);
    out["frames/favicon-dark-16.png"] = pngOf(c);
    const l = new Canvas(16, 16);
    l.draw([{ d: m.base, color: VERSIONS.color.base }, { d: m.accent, color: VERSIONS.color.accent }]);
    out["frames/favicon-light-16.png"] = pngOf(l);
  }
  out["fonts/archivo-latin-wdth-normal.woff2"] = readFileSync(FONTS.archivo);
  out["fonts/ibm-plex-mono-latin-400-normal.woff2"] = readFileSync(FONTS.plexMono400);
  out["fonts/ibm-plex-mono-latin-500-normal.woff2"] = readFileSync(FONTS.plexMono500);
  out["fonts/LICENSE-archivo.txt"] = readFileSync(FONTS.archivoLicence);
  out["fonts/LICENSE-ibm-plex-mono.txt"] = readFileSync(FONTS.plexMonoLicence);
  out["fonts/README.md"] = "# Fonts on this review page\n\nCopied by brand/scripts/build.mjs from the pinned Fontsource packages (@fontsource-variable/archivo 5.3.0, @fontsource/ibm-plex-mono 5.3.0). Both are under the SIL Open Font License 1.1; the licence files sit next to the fonts. The brand assets themselves contain outlines, not font files.\n";
  out["index.html"] = page({ files, facts, art });
  return out;
}

function page({ files, facts, art }) {
  const versions = ["color", "ink", "black", "dark", "white"]; // light backgrounds first, so a wrapped row splits light | dark
  const M = facts.minimums;
  const fit = facts.pixelFit;

  // ---------- logos ----------
  const logoRows = LOCKUPS.map((kind) => `
      <div class="lg-row">
        <div class="lg-head"><h3>${LOCKUP_NAMES[kind]}</h3><p class="note">${kind === "symbol" ? `min ${MINIMUM.symbol} px` : kind === "primary" ? `min ${MINIMUM.primaryWidth} px` : kind === "endorsed" ? `min ${Math.ceil(M.endorsed.width)} px` : kind === "stacked" ? `${M.stacked.width} px in the installer panel` : kind === "compact" ? `${f1(M.compact.width)} px in the installer header` : "where the symbol is near"}</p></div>
        <div class="lg-cells" style="--cell: ${SHOW_WIDTH[kind] + 34}px">${versions.map((v) => `<figure class="lg-cell on-${VERSIONS[v].on}"><img src="assets/logo/logo-${kind}-${v}.svg" alt="${esc(LOCKUP_NAMES[kind])}, ${esc(VERSIONS[v].label)}" style="width:${SHOW_WIDTH[kind]}px"><figcaption><a class="mono" href="assets/logo/logo-${kind}-${v}.svg">${v}</a></figcaption></figure>`).join("")}</div>
      </div>`).join("");

  // ---------- enlarged frames ----------
  const zoom = (key, size, k, label, bg) => `<span class="zoomcell bg-${bg}"><img class="zoom" data-k="${k}" data-size="${size}" src="frames/${key}.png" width="${size * k}" height="${size * k}" alt="${esc(label)}"></span>`;
  const real = (key, size, label) => `<img class="dp" data-size="${size}" src="frames/${key}.png" width="${size}" height="${size}" alt="${esc(label)}">`;

  // ---------- tray ----------
  const trayMock = (taskbar) => `
      <div class="taskbar taskbar--${taskbar}" role="group" aria-label="Sample Windows 11 taskbar, ${taskbar}, with the three ShelfSync tray states">
        <span class="tb-neighbour" aria-hidden="true"></span><span class="tb-neighbour tb-neighbour--round" aria-hidden="true"></span>
        ${TRAY.states.map((s) => `<span class="tb-slot" title="${STATE_NAMES[s]}"><img class="tray-live" data-state="${s}" data-taskbar="${taskbar}" src="frames/tray-${s}-${taskbar}-16.png" width="16" height="16" alt="${STATE_NAMES[s]}"></span>`).join("")}
        <span class="tb-clock" aria-hidden="true"><span>14:05</span><span>26/10/2026</span></span>
      </div>`;
  const trayGrid = (taskbar) => `
      <table class="framegrid tray-${taskbar}">
        <caption>For a ${taskbar} taskbar: <span class="mono">tray-&lt;state&gt;-${taskbar}.ico</span>, every frame at 5 device pixels per pixel</caption>
        <thead><tr><th scope="col">State</th>${TRAY.sizes.map((px) => `<th scope="col">${px} px</th>`).join("")}</tr></thead>
        <tbody>${TRAY.states.map((s) => `<tr><th scope="row">${STATE_NAMES[s]}<a class="mono file-sm" href="assets/tray/tray-${s}-${taskbar}.ico">tray-${s}-${taskbar}.ico</a></th>${TRAY.sizes.map((px) => `<td>${zoom(`tray-${s}-${taskbar}-${px}`, px, 5, `${STATE_NAMES[s]}, ${px} px, ${taskbar} taskbar`, `taskbar-${taskbar}`)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>`;

  // ---------- app icon ----------
  const appSmall = APP_ICON.sizes.filter((px) => px <= 64);
  const BG_NAMES = { white: "On white", "stone-50": "On stone-50", "ink-950": "On ink-950", "taskbar-dark": "On the dark taskbar mock" };
  const appReal = (bg, sizes) => `<figure class="realfig"><div class="realrow bg-${bg}">${sizes.map((px) => `<figure>${real(`app-${px}`, px, `shelfsync.ico, ${px} px frame`)}<figcaption>${px}</figcaption></figure>`).join("")}</div><figcaption>${BG_NAMES[bg]}</figcaption></figure>`;

  // ---------- installer ----------
  const P = INSTALLER.panel, H = INSTALLER.header;
  const nsisWelcome = `
      <div class="nsis" role="group" aria-label="Mock NSIS welcome page with the side panel at 1 image pixel per CSS pixel">
        <div class="nsis-title"><img src="frames/app-16.png" width="16" height="16" alt=""><span>ShelfSync Setup</span></div>
        <div class="nsis-body nsis-body--welcome">
          <img class="nsis-panel" src="assets/installer/installer-panel.png" width="${P.width}" height="${P.height}" alt="Installer side panel: the stacked endorsed lockup on ink, with the symbol tone on tone">
          <div class="nsis-text"><p class="nsis-h">Welcome to ShelfSync Setup</p><p>Setup will guide you through the installation of ShelfSync.</p><p>Click Next to continue.</p></div>
        </div>
        <div class="nsis-foot"><span class="nsis-btn" aria-hidden="true">&lt; Back</span><span class="nsis-btn nsis-btn--default" aria-hidden="true">Next &gt;</span><span class="nsis-btn" aria-hidden="true">Cancel</span></div>
      </div>`;
  const nsisInner = `
      <div class="nsis" role="group" aria-label="Mock NSIS inner page with the header image at 1 image pixel per CSS pixel">
        <div class="nsis-title"><img src="frames/app-16.png" width="16" height="16" alt=""><span>ShelfSync Setup</span></div>
        <div class="nsis-header"><div><p class="nsis-h2">Choose Install Location</p><p class="nsis-sub">Choose the folder in which to install ShelfSync.</p></div><img src="assets/installer/installer-header.png" width="${H.width}" height="${H.height}" alt="Installer header: the compact endorsed lockup on white"></div>
        <div class="nsis-body nsis-body--inner"><p>Setup will install ShelfSync in the following folder.</p><span class="nsis-field mono" aria-hidden="true">%LOCALAPPDATA%\\Programs\\ShelfSync</span></div>
        <div class="nsis-foot"><span class="nsis-btn" aria-hidden="true">&lt; Back</span><span class="nsis-btn nsis-btn--default" aria-hidden="true">Install</span><span class="nsis-btn" aria-hidden="true">Cancel</span></div>
      </div>`;

  // ---------- checks ----------
  const contrastRows = facts.contrasts.map((c) => `<tr><td>${esc(c.doc)}</td><th scope="row">${esc(c.label)}</th><td class="mono">${esc(c.fgName ?? c.fg)}</td><td class="mono">${esc(c.bg)}</td><td class="num">${f2(c.ratio)}</td><td class="num">${c.stated ?? "—"}</td><td>${c.min ? `${c.min}:1` : "—"}</td><td>${c.passes ? '<span class="verdict verdict--pass">Pass</span>' : '<span class="verdict verdict--fail">Fail</span>'}${c.docMismatch ? ' <span class="verdict verdict--note">Doc value off</span>' : ""}</td></tr>`).join("");
  const fitRows = fit.map((x) => `<tr><th scope="row">${x.px} px</th><td class="num">${x.v}</td><td class="num">${x.h}${x.thinned ? " (exception)" : ""}</td><td class="num">${x.spur}</td><td class="num">${x.channelRun}</td><td class="num">${f1(x.channelVsStroke)} %</td><td class="num">${x.upperOpening} / ${x.lowerOpening}</td><td>${x.whole && x.slash45 ? '<span class="verdict verdict--pass">Pass</span>' : '<span class="verdict verdict--fail">Fail</span>'}</td></tr>`).join("");
  const fileRows = Object.entries(files).filter(([f]) => !f.startsWith("assets/logo/") || f.endsWith("-color.svg")).map(([f, b]) => {
    const lim = limitFor(f);
    const href = f.startsWith("assets/") ? f : null;
    return `<tr><th scope="row" class="mono">${href ? `<a href="${href}">${esc(f)}</a>` : esc(f)}${f.startsWith("assets/logo/") ? " <span class=\"note\">(and 4 other versions)</span>" : ""}</th><td>${esc(describe(f, b))}</td><td class="num">${kb(bytes(b))}</td><td class="num">${lim ? kb(lim) : "—"}</td></tr>`;
  }).join("");
  const palette = Object.keys(tokens.palette).map((k) => `<li><span class="sw" style="background:var(--color-${k})"></span><span class="mono">${k}</span></li>`).join("");
  const status = ["success", "warning", "danger", "info"].map((k) => `<li><span class="sw" style="background:var(--color-${k})"></span><span class="mono">${k}</span></li>`).join("");

  return `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShelfSync brand assets (P3.3)</title>
<link rel="icon" href="assets/favicon/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="assets/tokens.css">
<style>
/* Every colour, size and font below is a token from assets/tokens.css (generated from brand/tokens.json). */
@font-face { font-family: "Archivo"; src: url("fonts/archivo-latin-wdth-normal.woff2") format("woff2"); font-weight: 100 900; font-stretch: 62% 125%; font-display: swap; }
@font-face { font-family: "IBM Plex Mono"; src: url("fonts/ibm-plex-mono-latin-400-normal.woff2") format("woff2"); font-weight: 400; font-display: swap; }
@font-face { font-family: "IBM Plex Mono"; src: url("fonts/ibm-plex-mono-latin-500-normal.woff2") format("woff2"); font-weight: 500; font-display: swap; }
:root {
  /* Mock Windows 11 taskbar and GitHub surfaces, mixed from the white and black tokens (no token is a Windows grey). */
  --taskbar-light: color-mix(in srgb, var(--color-white) 95%, var(--color-black));
  --taskbar-dark: color-mix(in srgb, var(--color-black) 87.5%, var(--color-white));
}
* { box-sizing: border-box; }
html { background: var(--color-bg); color: var(--color-text); }
body { margin: 0; font-family: var(--font-sans); font-size: var(--text-body); line-height: var(--text-body--line-height); font-variant-numeric: tabular-nums; }
a { color: var(--color-link); text-underline-offset: 3px; }
a:hover { color: var(--color-link-hover); }
:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; border-radius: 2px; }
.skip { position: absolute; left: -9999px; top: var(--space-2); }
.skip:focus { left: var(--space-2); background: var(--color-surface); padding: var(--space-2) var(--space-3); z-index: 2; }
.mono { font-family: var(--font-mono); font-size: var(--text-sm); }
.note { color: var(--color-text-muted); font-size: var(--text-sm); line-height: var(--text-sm--line-height); margin: 0; }
p.note { max-width: 80ch; }
img { display: block; }

.board { padding: var(--space-12) var(--space-8) var(--space-16); max-width: 1376px; }
@media (min-width: 1360px) { .board { padding-left: var(--space-16); padding-right: var(--space-16); } }
.board-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-8); margin-bottom: var(--space-8); }
h1 { font-family: var(--font-display); font-stretch: 116%; font-size: var(--text-display-2); font-weight: var(--text-display-2--font-weight); line-height: var(--text-display-2--line-height); margin: 0 0 var(--space-3); letter-spacing: -0.01em; }
.lede { margin: 0; max-width: 72ch; color: var(--color-text-muted); }
.theme-btn { flex: none; min-height: var(--target-min); padding: 0 var(--space-4); border-radius: var(--radius-md); border: 1px solid var(--color-border-control); background: var(--color-surface); color: var(--color-text); font: 500 var(--text-sm)/1 var(--font-sans); cursor: pointer; display: inline-flex; align-items: center; gap: var(--space-2); }
.theme-btn:hover { border-color: var(--color-text); }
.theme-btn svg { width: 16px; height: 16px; }
.toc { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-6); margin: 0; padding: 0; list-style: none; font-size: var(--text-sm); }

section { border-top: 2px solid var(--color-text); padding-top: var(--space-4); margin-top: var(--space-16); }
h2 { font-family: var(--font-display); font-stretch: 116%; font-size: var(--text-h2); font-weight: var(--text-h2--font-weight); line-height: var(--text-h2--line-height); margin: 0 0 var(--space-3); }
h3 { font-size: var(--text-h4); font-weight: var(--text-h4--font-weight); line-height: var(--text-h4--line-height); margin: 0 0 var(--space-2); }
.intro { max-width: 72ch; margin: 0 0 var(--space-8); }
.intro + .intro { margin-top: calc(-1 * var(--space-6)); }
figure { margin: 0; }
figcaption { margin-top: var(--space-2); font-size: var(--text-sm); line-height: var(--text-sm--line-height); color: var(--color-text-muted); }

/* fixed-tone surfaces: the asset's own background, whatever the page theme; text inside follows the surface */
.on-white, .bg-white { background: var(--color-white); --color-text: var(--color-ink-900); --color-text-muted: var(--color-ink-400); --color-link: var(--color-ink-900); --color-border: var(--color-stone-300); color: var(--color-ink-900); }
.on-ink-900, .bg-ink-900 { background: var(--color-ink-900); --color-text: var(--color-mist); --color-text-muted: var(--color-ink-300); --color-link: var(--color-mist); --color-border: var(--color-ink-600); color: var(--color-mist); }
.bg-stone-50 { background: var(--color-stone-50); color: var(--color-ink-900); --color-text-muted: var(--color-ink-400); --color-link: var(--color-ink-900); }
.bg-ink-950 { background: var(--color-ink-950); color: var(--color-mist); --color-text-muted: var(--color-ink-300); --color-link: var(--color-mist); }
.on-white a:hover, .bg-white a:hover, .bg-stone-50 a:hover { color: var(--color-verdigris-700); }
.on-ink-900 a:hover, .bg-ink-900 a:hover, .bg-ink-950 a:hover { color: var(--color-verdigris-300); }
.bg-taskbar-light { background: var(--taskbar-light); color: var(--color-ink-900); }
/* follows the system theme, as favicon.svg does (not the page button): white in light, ink-950 in dark */
.bg-system { background: var(--color-white); border: 1px solid var(--color-stone-300); }
@media (prefers-color-scheme: dark) { .bg-system { background: var(--color-ink-950); border-color: var(--color-ink-600); } }
.bg-taskbar-dark { background: var(--taskbar-dark); color: var(--color-mist); }

/* logos */
.lg-grid { display: grid; gap: var(--space-3); }
.lg-row { display: grid; grid-template-columns: 168px minmax(0, 1fr); gap: var(--space-3); align-items: start; }
.lg-cells { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--cell), 1fr)); gap: var(--space-3); }
.lg-head { padding-top: var(--space-4); }
.lg-head h3 { font-size: var(--text-body); margin: 0; }
.lg-cell { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-4); display: flex; flex-direction: column; justify-content: space-between; gap: var(--space-3); min-height: 120px; overflow: hidden; }
.lg-cell img { height: auto; }
.lg-cell figcaption { margin: 0; }

/* rasters */
img.zoom { image-rendering: pixelated; }
.zoomcell { display: inline-grid; place-items: center; padding: var(--space-2); border-radius: var(--radius-sm); }
.realrow { display: flex; align-items: flex-end; gap: var(--space-5); padding: var(--space-5); border-radius: var(--radius-md); border: 1px solid var(--color-border); flex-wrap: wrap; }
.realrow figure { display: grid; justify-items: center; }
.realrow figcaption { margin-top: var(--space-1); font-size: var(--text-caption); color: inherit; opacity: 1; }
.realrow.bg-ink-950 figcaption, .realrow.bg-ink-900 figcaption, .realrow.bg-taskbar-dark figcaption { color: var(--color-ink-300); }
.realrow.bg-white figcaption, .realrow.bg-stone-50 figcaption { color: var(--color-ink-400); }
.stack { display: grid; gap: var(--space-4); }
.cols2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-8); align-items: start; }
.zoomrow { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: flex-end; }
.zoomrow figure { display: grid; justify-items: start; }

/* tray */
.taskbars { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-6); max-width: 880px; margin-bottom: var(--space-8); }
.taskbar { height: 48px; display: flex; align-items: center; justify-content: flex-end; gap: 2px; padding: 0 var(--space-3); border-radius: var(--radius-sm); }
.taskbar--light { background: var(--taskbar-light); color: var(--color-ink-900); border: 1px solid var(--color-stone-300); --neighbour: var(--color-stone-500); }
.taskbar--dark { background: var(--taskbar-dark); color: var(--color-mist); border: 1px solid var(--color-ink-600); --neighbour: var(--color-ink-500); }
.tb-slot, .tb-neighbour { width: 32px; height: 32px; display: grid; place-items: center; flex: none; }
.tb-neighbour::before { content: ""; width: 16px; height: 12px; border: 2px solid var(--neighbour); border-radius: 3px; }
.tb-neighbour--round::before { width: 14px; height: 14px; border-radius: 50%; }
.tb-clock { display: flex; flex-direction: column; align-items: flex-end; margin-left: var(--space-3); font-size: var(--text-caption); line-height: 16px; }
table.framegrid { width: max-content; border-collapse: separate; border-spacing: var(--space-2); margin-left: calc(-1 * var(--space-2)); }
table.framegrid caption { text-align: left; font-size: var(--text-sm); color: var(--color-text-muted); padding: 0 var(--space-2) var(--space-2); }
table.framegrid th { text-align: left; font-size: var(--text-sm); font-weight: 500; vertical-align: middle; padding-right: var(--space-3); }
table.framegrid thead th { color: var(--color-text-muted); font-weight: 500; font-size: var(--text-caption); }
table.framegrid td { vertical-align: bottom; }
.file-sm { display: block; font-size: var(--text-caption); font-weight: 400; white-space: nowrap; }
.legend-states { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-6); max-width: 880px; margin: 0 0 var(--space-8); padding: 0; list-style: none; }
.legend-states li { border-top: 1px solid var(--color-border); padding-top: var(--space-3); font-size: var(--text-sm); }
.legend-states strong { display: block; font-size: var(--text-body); }

/* installer */
.nsis { width: 499px; border: 1px solid var(--color-stone-500); background: var(--color-white); color: var(--color-ink-900); font-size: var(--text-sm); box-shadow: var(--shadow-2); }
.nsis-title { display: flex; align-items: center; gap: var(--space-2); height: 32px; padding: 0 var(--space-3); background: var(--color-white); border-bottom: 1px solid var(--color-stone-200); font-size: var(--text-caption); }
.nsis-body--welcome { display: flex; height: ${P.height}px; }
.nsis-panel { flex: none; }
.nsis-text { padding: var(--space-4) var(--space-5); }
.nsis-text p { margin: 0 0 var(--space-3); }
.nsis-h { font-size: var(--text-h4); font-weight: 600; line-height: 1.3; }
.nsis-header { display: flex; justify-content: space-between; align-items: stretch; border-bottom: 1px solid var(--color-stone-300); background: var(--color-white); }
.nsis-header > div { padding: var(--space-2) var(--space-4); }
.nsis-header p { margin: 0; }
.nsis-h2 { font-weight: 600; }
.nsis-sub { padding-left: var(--space-4); color: var(--color-ink-400); }
.nsis-body--inner { height: 200px; padding: var(--space-5) var(--space-6); background: var(--color-stone-100); }
.nsis-body--inner p { margin: 0 0 var(--space-4); }
.nsis-field { display: block; border: 1px solid var(--color-stone-500); background: var(--color-white); padding: var(--space-1) var(--space-2); }
.nsis-foot { display: flex; justify-content: flex-end; gap: var(--space-2); padding: var(--space-3); background: var(--color-stone-100); border-top: 1px solid var(--color-stone-300); }
.nsis-btn { min-width: 76px; text-align: center; padding: var(--space-1) var(--space-3); border: 1px solid var(--color-stone-500); border-radius: var(--radius-sm); background: var(--color-white); font-size: var(--text-caption); }
.nsis-btn--default { border-color: var(--color-ink-900); box-shadow: inset 0 0 0 1px var(--color-ink-900); }
.nsis-row { display: flex; flex-wrap: wrap; gap: var(--space-8); align-items: flex-start; }
.facts { display: grid; grid-template-columns: repeat(4, auto); gap: var(--space-2) var(--space-8); margin: 0 0 var(--space-8); justify-content: start; }
.facts dt { font-size: var(--text-caption); color: var(--color-text-muted); line-height: 1.4; }
.facts dd { margin: 0; font-size: var(--text-h4); font-weight: 600; line-height: 1.3; }
.lockup-zoom { display: flex; flex-wrap: wrap; gap: var(--space-4); margin-bottom: var(--space-8); }
.lockup-zoom figure { padding: var(--space-6); border-radius: var(--radius-md); border: 1px solid var(--color-border); }

/* GitHub */
.gh { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-6); }
.gh-light { background: var(--color-white); border-color: var(--color-stone-300); color: var(--color-ink-900); --color-text-muted: var(--color-ink-400); --color-link: var(--color-ink-900); --color-link-hover: var(--color-verdigris-700); }
.gh-dark { background: var(--color-ink-950); border-color: var(--color-ink-600); color: var(--color-mist); --color-text-muted: var(--color-ink-300); --color-link: var(--color-mist); --color-link-hover: var(--color-verdigris-300); }
.gh img { width: 640px; max-width: 100%; height: auto; }
.social img { width: 640px; max-width: 100%; height: auto; border-radius: var(--radius-md); }

/* tokens */
.swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-2) var(--space-4); list-style: none; margin: 0 0 var(--space-6); padding: 0; }
.swatches li { display: flex; align-items: center; gap: var(--space-2); }
.sw { width: 24px; height: 24px; border-radius: var(--radius-sm); border: 1px solid var(--color-border-control); flex: none; }

/* tables */
.scroll { overflow-x: auto; }
table.data { border-collapse: collapse; width: 100%; font-size: var(--text-sm); line-height: var(--text-sm--line-height); }
table.data caption { text-align: left; font-weight: 600; font-size: var(--text-body); padding-bottom: var(--space-3); }
table.data th, table.data td { text-align: left; padding: var(--space-2) var(--space-3) var(--space-2) 0; border-top: 1px solid var(--color-border); vertical-align: top; }
table.data thead th { font-size: var(--text-caption); font-weight: 500; color: var(--color-text-muted); border-top: 0; }
table.data tbody th { font-weight: 500; }
td.num { white-space: nowrap; }
.tables { display: grid; gap: var(--space-10); }
.verdict { font-weight: 600; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.verdict::before { content: ""; display: inline-block; width: 8px; height: 8px; }
.verdict--pass::before { background: currentColor; }
.verdict--note::before { border: 2px solid currentColor; }
.verdict--fail::before { border: 2px solid currentColor; transform: rotate(45deg); width: 7px; height: 7px; }
.board-foot { margin-top: var(--space-16); padding-top: var(--space-6); border-top: 1px solid var(--color-border); max-width: 80ch; font-size: var(--text-sm); color: var(--color-text-muted); }
.board-foot p { margin: 0 0 var(--space-2); }

@media (max-width: 1180px) {
  .lg-row { grid-template-columns: minmax(0, 1fr); }
  .lg-head { padding-top: var(--space-3); }
  .cols2 { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 900px) {
  .taskbars, .legend-states { grid-template-columns: minmax(0, 1fr); }
  .board { padding-left: var(--space-4); padding-right: var(--space-4); }
  .facts { grid-template-columns: repeat(2, auto); }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<a class="skip" href="#main">Skip to the assets</a>
<div class="board">
  <header class="board-head">
    <div>
      <h1>ShelfSync brand assets</h1>
      <p class="lede">P3.3 turns the approved S-cut into every file 05 §1.4 asks for. One command, <span class="mono">npm run build</span> in <span class="mono">brand/</span>, draws them all from <span class="mono">brand/geometry.mjs</span> and <span class="mono">brand/tokens.json</span>, and the tests fail if any file drifts from a fresh build. Rasters are written by ShelfSync's own code (Node's zlib, no sharp).</p>
    </div>
    <button class="theme-btn" id="theme" type="button" aria-pressed="false"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1a7 7 0 1 0 0 14Z" fill="currentColor"/><path d="M8 1a7 7 0 0 1 0 14" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><span>Dark page</span></button>
  </header>
  <nav aria-label="Sections"><ul class="toc"><li><a href="#logos">Logos</a></li><li><a href="#tray">Tray icons</a></li><li><a href="#app">App icon</a></li><li><a href="#favicon">Favicon</a></li><li><a href="#installer">Installer</a></li><li><a href="#github">GitHub</a></li><li><a href="#tokens">Tokens</a></li><li><a href="#checks">Checks and files</a></li></ul></nav>

  <main id="main">
  <section id="logos" aria-labelledby="h-logos">
    <h2 id="h-logos">Logos</h2>
    <p class="intro">Four lockups from 05, plus the two installer-sized endorsed lockups this task adds, each in TecHaust's five versions: colour, ink and black on white; dark and white on ink-900. File names follow TecHaust: <span class="mono">logo-&lt;lockup&gt;-&lt;version&gt;.svg</span>. Every shape is the approved P3.2 geometry; the build checks that the symbol, wordmark and endorsement outlines are the same as P3.2's.</p>
    <div class="lg-grid">${logoRows}
    </div>
  </section>

  <section id="tray" aria-labelledby="h-tray">
    <h2 id="h-tray">Tray icons</h2>
    <p class="intro">The bare symbol, pixel-fitted and full bleed, in the colour version for a light taskbar and the dark version for a dark one. A state adds a badge in the bottom-right corner, with a clear gap cut out of the mark. The badge sits wholly below the spine, so the verdigris cut piece is never clipped.</p>
    <ul class="legend-states">
      <li><strong>Normal</strong>The symbol alone.</li>
      <li><strong>Paused</strong>Two bars, the pause sign, in the info colour.</li>
      <li><strong>Needs attention</strong>A round dot in the warning colour.</li>
    </ul>
    <p class="intro">Bars and a dot are different shapes, so the state never depends on colour. Below, each taskbar shows all three states side by side at device pixels, using the frame Windows picks for this screen's scale. <span id="trayfit">16 px at 100 %, 20 px at 125 %, 24 px at 150 %, 32 px at 200 %.</span></p>
    <div class="taskbars">${trayMock("light")}${trayMock("dark")}</div>
    <div class="stack scroll">${trayGrid("light")}${trayGrid("dark")}</div>
    <p class="note">Badge sizes (box / gap): ${TRAY.sizes.map((px) => `${px} px: ${TRAY.badge[px].box} / ${TRAY.badge[px].gap}`).join("; ")}. Not checked yet: the real Windows 11 notification area, which waits for the tray app at M1.</p>
  </section>

  <section id="app" aria-labelledby="h-app">
    <h2 id="h-app">App icon</h2>
    <p class="intro"><a class="mono" href="assets/app/shelfsync.ico">shelfsync.ico</a> serves the desktop shortcut, Start, toasts and <span class="mono">Setup.exe</span>, which sit on light and dark surfaces alike. The mark's ink vanishes on dark and its mist on light, so the icon is the dark version on an ink-900 plate. Wherever the symbol inside is 64 px or smaller it is pixel-fitted at one of the approved sizes (so the 96 px frame holds the 64 px fit), and never under 16 px except in the 16 px frame (below); in the 128 and 256 px frames it is the smooth vector at two thirds of the plate. Frames: ${APP_ICON.sizes.join(", ")} px; up to ${APP_ICON.dibMax} px they are 32-bit bitmaps, larger ones PNG.</p>
    <div class="cols2">${["white", "ink-950", "stone-50", "taskbar-dark"].map((bg) => appReal(bg, appSmall)).join("")}</div>
    <div class="cols2" style="margin-top: var(--space-6)">${["white", "ink-950"].map((bg) => appReal(bg, APP_ICON.sizes.filter((px) => px > 64))).join("")}</div>
    <h3 style="margin-top: var(--space-8)">Frames up to 64 px, at 4 device pixels per pixel</h3>
    <div class="zoomrow">${appSmall.map((px) => `<figure>${zoom(`app-${px}`, px, 4, `shelfsync.ico ${px} px frame, enlarged`, "white")}<figcaption>${px} px, symbol ${APP_ICON.fittedSymbol[px]} px</figcaption></figure>`).join("")}</div>
    <h3 style="margin-top: var(--space-8)">The 16 px frame</h3>
    <p class="intro">At 16 px a plate around a 16 px symbol has no room, so this frame alone holds the symbol fitted at ${APP_ICON.rimFit} px inside a 1 px ink rim (the owner's exception to the 16 px minimum, for this ICO frame only). The rule gives the ${APP_ICON.rimFit} px fit: strokes 3 and 2, spur 2, openings 2. The rim keeps the icon's edge on white; on dark the S reads as before.</p>
    <div class="zoomrow">
      <figure>${zoom("app-16", 16, 8, "16 px frame on white, enlarged", "white")}<figcaption>On white</figcaption></figure>
      <figure>${zoom("app-16", 16, 8, "16 px frame on ink-950, enlarged", "ink-950")}<figcaption>On ink-950</figcaption></figure>
      <figure>${zoom("app-16", 16, 8, "16 px frame on the light taskbar mock, enlarged", "taskbar-light")}<figcaption>On the light taskbar mock</figcaption></figure>
    </div>
  </section>

  <section id="favicon" aria-labelledby="h-favicon">
    <h2 id="h-favicon">Favicon</h2>
    <p class="intro"><a class="mono" href="assets/favicon/favicon.svg">favicon.svg</a> is the symbol on a 16-unit pixel grid that switches to the dark colours when the browser is dark (the image follows the system setting, not this page's button, and so do the two live samples' backgrounds). <a class="mono" href="assets/favicon/favicon.ico">favicon.ico</a> holds the app-icon plate frames at ${FAVICON_ICO_SIZES.join(", ")} px, for places that don't take SVG.</p>
    <div class="zoomrow">
      <figure><span class="zoomcell bg-system"><img src="assets/favicon/favicon.svg" width="16" height="16" alt="favicon.svg at 16 CSS px"></span><figcaption><span class="mono">favicon.svg</span>, 16 px</figcaption></figure>
      <figure><span class="zoomcell bg-system"><img src="assets/favicon/favicon.svg" width="32" height="32" alt="favicon.svg at 32 CSS px"></span><figcaption>32 px</figcaption></figure>
      <figure>${zoom("favicon-light-16", 16, 6, "favicon.svg in a light browser, enlarged", "white")}<figcaption>Light browser, enlarged</figcaption></figure>
      <figure>${zoom("favicon-dark-16", 16, 6, "favicon.svg in a dark browser, enlarged", "ink-950")}<figcaption>Dark browser, enlarged</figcaption></figure>
      ${FAVICON_ICO_SIZES.map((px) => `<figure>${zoom(`app-${px}`, px, px === 16 ? 6 : px === 32 ? 3 : 2, `favicon.ico ${px} px frame, enlarged`, "stone-50")}<figcaption><span class="mono">favicon.ico</span>, ${px} px</figcaption></figure>`).join("")}
    </div>
  </section>

  <section id="installer" aria-labelledby="h-installer">
    <h2 id="h-installer">Installer art</h2>
    <p class="intro">The endorsed lockup needs ${Math.ceil(M.endorsed.width)} px for a 12 px "by TecHaust", and NSIS gives 164 px. With the endorsed lockup's own proportions the caption would be ${f1(M.endorsedInPanelCaptionPx)} px there. So two smaller endorsed lockups keep the caption at 12 px: the shapes are unchanged, the endorsement is aligned with the wordmark's left edge as before, and only its size relative to the wordmark grows. Both sit on whole pixels where it matters: the symbol is pixel-fitted at ${M.stacked.symbolPx} px in the panel and ${M.compact.symbolPx} px in the header.</p>
    <dl class="facts">
      <div><dt>Stacked: width</dt><dd>${M.stacked.width} px</dd></div>
      <div><dt>Stacked: caption</dt><dd>${M.stacked.captionPx} px</dd></div>
      <div><dt>Stacked: endorsement / cap</dt><dd>${f2(M.stacked.ratio)}</dd></div>
      <div><dt>Stacked: symbol</dt><dd>${M.stacked.symbolPx} px</dd></div>
      <div><dt>Compact: width</dt><dd>${f1(M.compact.width)} px</dd></div>
      <div><dt>Compact: caption</dt><dd>${M.compact.captionPx} px</dd></div>
      <div><dt>Compact: endorsement / cap</dt><dd>${f2(M.compact.ratio)}</dd></div>
      <div><dt>Compact: symbol</dt><dd>${M.compact.symbolPx} px</dd></div>
    </dl>
    <div class="nsis-row">${nsisWelcome}${nsisInner}</div>
    <p class="note" style="margin-top: var(--space-4)">Mock windows, one image pixel per CSS pixel. The window text is NSIS's default wording, shown as sample text only. NSIS takes the 24-bit <a class="mono" href="assets/installer/installer-panel.bmp">installer-panel.bmp</a> and <a class="mono" href="assets/installer/installer-header.bmp">installer-header.bmp</a>; the PNGs are previews of the same pixels. How NSIS scales them at 150 % and 200 % is checked at M1; the art is flat colour with a large mark so it survives stretching.</p>
  </section>

  <section id="github" aria-labelledby="h-github">
    <h2 id="h-github">GitHub</h2>
    <p class="intro">The repository's social preview (1280 × 640, shown here at half size) and the README header in both GitHub themes (1280 × 320, drawn at 2× for a 640 px display). The README picks one with <span class="mono">&lt;picture&gt;</span> and <span class="mono">prefers-color-scheme</span>. The surfaces below stand in for GitHub's own colours with the white and ink-950 tokens.</p>
    <figure class="social"><img src="assets/github/social-preview.png" width="1280" height="640" alt="Social preview: the endorsed lockup on ink, the symbol tone on tone bleeding off the right"><figcaption><a class="mono" href="assets/github/social-preview.png">social-preview.png</a>. No strapline: ShelfSync has no approved one yet.</figcaption></figure>
    <div class="cols2" style="margin-top: var(--space-8)">
      <figure class="gh gh-light"><img src="assets/github/readme-header-light.png" width="1280" height="320" alt="README header for GitHub's light theme"><figcaption><a class="mono" href="assets/github/readme-header-light.png">readme-header-light.png</a></figcaption></figure>
      <figure class="gh gh-dark"><img src="assets/github/readme-header-dark.png" width="1280" height="320" alt="README header for GitHub's dark theme"><figcaption><a class="mono" href="assets/github/readme-header-dark.png">readme-header-dark.png</a></figcaption></figure>
    </div>
  </section>

  <section id="tokens" aria-labelledby="h-tokens">
    <h2 id="h-tokens">Tokens</h2>
    <p class="intro"><span class="mono">brand/tokens.json</span> is TecHaust's Patina file, copied unchanged (source and date recorded inside it). The build writes <a class="mono" href="assets/tokens.css">tokens.css</a> from it: palette, semantic colours for light and dark, type, space, radius, motion. This page uses nothing else.</p>
    <ul class="swatches" aria-label="Palette">${palette}</ul>
    <ul class="swatches" aria-label="Status colours, for this page's theme">${status}</ul>
  </section>

  <section id="checks" aria-labelledby="h-checks">
    <h2 id="h-checks">Checks and files</h2>
    <p class="intro">Every number here comes from the build (<span class="mono">brand/generated/measurements.json</span>) and is guarded by the tests. Verdigris is ${f1(facts.share.vector)} % of the mark (${f1(facts.share.px16)} % at 16 px); every spine row at 16 px keeps ${facts.channelClear16.min} clear channel pixels.</p>
    <div class="tables">
      <div class="scroll"><table class="data">
        <caption>Pixel fit at every fitted size</caption>
        <thead><tr><th scope="col">Size</th><th scope="col">Vertical</th><th scope="col">Horizontal</th><th scope="col">Spur</th><th scope="col">Channel run</th><th scope="col">Channel / stroke</th><th scope="col">Openings</th><th scope="col">Whole pixels, cuts 45° "/"</th></tr></thead>
        <tbody>${fitRows}</tbody>
      </table></div>
      <div class="scroll"><table class="data">
        <caption>Contrast: every pair in 05 and 14, and the pairs this task adds</caption>
        <thead><tr><th scope="col">Source</th><th scope="col">Pair</th><th scope="col">Foreground</th><th scope="col">Background</th><th scope="col">Measured</th><th scope="col">Doc says</th><th scope="col">Needs</th><th scope="col">Result</th></tr></thead>
        <tbody>${contrastRows}</tbody>
      </table></div>
      <div class="scroll"><table class="data">
        <caption>Generated files (brand/), read back from their bytes</caption>
        <thead><tr><th scope="col">File</th><th scope="col">What it holds</th><th scope="col">Size</th><th scope="col">Limit</th></tr></thead>
        <tbody>${fileRows}</tbody>
      </table></div>
    </div>
  </section>
  </main>

  <footer class="board-foot">
    <p>Generated by <span class="mono">brand/scripts/build.mjs</span>; do not edit. Colours: <span class="mono">assets/tokens.css</span>, generated from <span class="mono">brand/tokens.json</span>. The taskbar greys are mixed from the white and black tokens to stand in for Windows 11.</p>
    <p>Sample content: the taskbar clock and neighbouring tray icons, the NSIS window text, and the GitHub surfaces are placeholders.</p>
    <p>Fonts: Archivo and IBM Plex Mono from the pinned Fontsource packages, SIL Open Font License 1.1 (<a href="fonts/LICENSE-archivo.txt">Archivo</a>, <a href="fonts/LICENSE-ibm-plex-mono.txt">IBM Plex Mono</a>).</p>
  </footer>
</div>
<script>
(() => {
  const root = document.documentElement;
  const btn = document.getElementById("theme");
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : sysDark.matches);
  const sync = () => { btn.setAttribute("aria-pressed", String(isDark())); btn.querySelector("span").textContent = isDark() ? "Light page" : "Dark page"; };
  btn.addEventListener("click", () => { root.dataset.theme = isDark() ? "light" : "dark"; sync(); });
  sysDark.addEventListener("change", sync);
  sync();
  // Draw rasters at whole device pixels: a frame of n px is n device pixels, an enlarged one k device px per pixel.
  const fitPixels = () => {
    const dpr = window.devicePixelRatio || 1;
    for (const img of document.querySelectorAll("img.dp")) { const n = +img.dataset.size; img.style.width = img.style.height = n / dpr + "px"; }
    for (const img of document.querySelectorAll("img.zoom[data-k]")) { const n = +img.dataset.size, k = +img.dataset.k; img.style.width = img.style.height = (n * k) / dpr + "px"; }
    const sizes = ${JSON.stringify(TRAY.sizes)};
    const want = Math.round(16 * dpr);
    const px = sizes.find((s) => s >= want) ?? sizes[sizes.length - 1];
    for (const img of document.querySelectorAll("img.tray-live")) { img.src = "frames/tray-" + img.dataset.state + "-" + img.dataset.taskbar + "-" + px + ".png"; img.style.width = img.style.height = px / dpr + "px"; }
    document.getElementById("trayfit").textContent = "This screen's scale is " + Math.round(dpr * 100) + " %, so the taskbars show the " + px + " px frames, drawn at device pixels.";
  };
  // A media query matches one scale only, so after each change it is rebuilt for the new scale.
  const watch = () => matchMedia("(resolution: " + (window.devicePixelRatio || 1) + "dppx)").addEventListener("change", () => { fitPixels(); watch(); }, { once: true });
  fitPixels();
  watch();
})();
</script>
</body>
</html>
`;
}
