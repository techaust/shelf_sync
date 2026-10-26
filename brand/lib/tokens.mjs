// Token model and the generated tokens.css (pure functions). brand/tokens.json is the single source; this mirrors
// TecHaust's packages/ui/src/tokens/model.ts and render.ts (renderTokensCss only; the Tailwind theme is M1).
import { readFileSync } from "node:fs";
import { TASKBAR_MIX } from "../geometry.mjs";

const raw = JSON.parse(readFileSync(new URL("../tokens.json", import.meta.url), "utf8"));
const { $description: _d, $source: _s, $copied: _c, ...data } = raw;
export const tokens = data;
export const tokenSource = { source: raw.$source, copied: raw.$copied };

const HEX = /^#[0-9A-Fa-f]{6}$/;

/** A semantic value is either a palette key or a literal hex colour. Returns upper-case hex. */
export function hex(value, t = tokens) {
  if (value.startsWith("taskbar-")) return TASKBAR[value.slice(8)];
  const h = HEX.test(value) ? value : t.palette[value];
  if (!h || !HEX.test(h)) throw new Error(`Unknown colour "${value}"`);
  return h.toUpperCase();
}
/** A semantic colour for a theme, e.g. status("warning", "dark"). */
export const semantic = (name, theme, t = tokens) => hex(t.semantic[name][theme], t);

const mix = (a, b, w) => {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return "#" + x.map((c, i) => Math.round(c * w + y[i] * (1 - w)).toString(16).padStart(2, "0")).join("").toUpperCase();
};
/** Mock Windows 11 taskbar greys (stand-ins for the contrast checks; the real taskbar is checked at M1). */
export const TASKBAR = {
  light: mix(tokens.palette.white, tokens.palette.black, TASKBAR_MIX.light),
  dark: mix(tokens.palette.black, tokens.palette.white, TASKBAR_MIX.dark),
};

/** WCAG 2.x relative luminance and contrast ratio. */
export function luminance(h) {
  const n = parseInt(hex(h).slice(1), 16);
  const f = (c) => (c / 255 <= 0.04045 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(n >> 16) + 0.7152 * f((n >> 8) & 255) + 0.0722 * f(n & 255);
}
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

/** [r, g, b] 0..255 of a token or hex. */
export const rgb = (v) => { const n = parseInt(hex(v).slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };

// ---------- tokens.css ----------
const round = (n, places = 4) => Number(n.toFixed(places)).toString();
const rem = (px) => (px === 0 ? "0" : `${round(px / 16)}rem`);
function fluidSize(min, max, t) {
  const { minViewport: v0, maxViewport: v1 } = t.fluid;
  const slope = (max - min) / (v1 - v0);
  const intercept = min - slope * v0;
  return `clamp(${rem(min)}, ${rem(intercept)} + ${round(slope * 100)}vw, ${rem(max)})`;
}
const textSize = (tok, t) => ("size" in tok ? rem(tok.size) : fluidSize(tok.min, tok.max, t));
const quoteFamily = (f) => (/^[a-z-]+$/.test(f) ? f : `"${f}"`);
const fontStack = (f) => [f.family, ...(f.metricFallback ? [f.metricFallback] : []), ...f.fallback].map(quoteFamily).join(", ");
const block = (selector, lines, indent = "") => `${indent}${selector} {\n${lines.map((l) => `${indent}  ${l}`).join("\n")}\n${indent}}\n`;
const decl = (name, value) => `--${name}: ${value};`;
const low = (v, t) => hex(v, t).toLowerCase();

function colorDecls(t, theme, withPalette) {
  const out = [];
  if (withPalette) for (const k of Object.keys(t.palette)) out.push(decl(`color-${k}`, low(k, t)));
  for (const [k, v] of Object.entries(t.semantic)) out.push(decl(`color-${k}`, low(v[theme], t)));
  return out;
}
const elevationDecls = (t, theme) => Object.entries(t.shadow).map(([k, v]) => decl(`elevation-${k}`, v[theme]));
const shadowRefs = (t) => Object.keys(t.shadow).map((k) => decl(`shadow-${k}`, `var(--elevation-${k})`));
function typeDecls(t) {
  const out = Object.entries(t.font).map(([k, f]) => decl(`font-${k}`, fontStack(f)));
  for (const [k, f] of Object.entries(t.font)) if (f.stretch) out.push(decl(`font-${k}--stretch`, f.stretch));
  for (const [k, tok] of Object.entries(t.text)) {
    out.push(decl(`text-${k}`, textSize(tok, t)));
    out.push(decl(`text-${k}--line-height`, tok.lineHeight));
    out.push(decl(`text-${k}--font-weight`, tok.weight));
    if (tok.letterSpacing) out.push(decl(`text-${k}--letter-spacing`, tok.letterSpacing));
  }
  return out;
}
const shapeDecls = (t) => [
  ...Object.entries(t.breakpoint).map(([k, v]) => decl(`breakpoint-${k}`, rem(v))),
  ...Object.entries(t.container).map(([k, v]) => decl(`container-${k}`, v)),
  ...Object.entries(t.radius).map(([k, v]) => decl(`radius-${k}`, v >= 999 ? "9999px" : rem(v))),
  ...Object.entries(t.ease).map(([k, v]) => decl(`ease-${k}`, v)),
];
const rootDecls = (t) => [
  ...Object.entries(t.space).map(([k, v]) => decl(`space-${k}`, rem(v))),
  ...Object.entries(t.rhythm).map(([k, v]) => decl(k, rem(v.base))),
  ...Object.entries(t.duration).map(([k, v]) => decl(`duration-${k}`, `${v}ms`)),
  ...Object.entries(t.app).map(([k, v]) => decl(`app-${k}`, rem(v))),
  decl("target-min", rem(t.target.min)),
];

/** Plain CSS custom properties, light on :root, dark by OS preference or data-theme="dark". */
export function renderTokensCss(t = tokens) {
  const md = rem(t.breakpoint.md ?? 768);
  const lg = rem(t.breakpoint.lg ?? 1024);
  const rhythm = (bp) => Object.entries(t.rhythm).map(([k, v]) => decl(k, rem(v[bp])));
  const dark = ["color-scheme: dark;", ...colorDecls(t, "dark", false), ...elevationDecls(t, "dark")];
  const reduced = Object.keys(t.duration).map((k) => decl(`duration-${k}`, "0ms"));
  const root = ["color-scheme: light;", ...colorDecls(t, "light", true), ...elevationDecls(t, "light"), ...shadowRefs(t), ...typeDecls(t), ...shapeDecls(t), ...rootDecls(t)];
  return [
    `/* Design tokens as CSS custom properties. Generated from brand/tokens.json by \`npm run build\` in brand/. Do not edit. */\n`,
    block(":root", root),
    `@media (min-width: ${md}) {\n${block(":root", rhythm("md"), "  ")}}\n`,
    `@media (min-width: ${lg}) {\n${block(":root", rhythm("lg"), "  ")}}\n`,
    "/* Dark theme: follows the OS unless the page sets data-theme. */\n",
    `@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', dark, "  ")}}\n`,
    block(':root[data-theme="dark"]', dark),
    `@media (prefers-reduced-motion: reduce) {\n${block(":root", reduced, "  ")}}\n`,
  ].join("\n");
}
