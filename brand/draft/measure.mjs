// Every number the board and the brand audit report, computed from geometry.mjs (never typed in by hand).
import { MARK, RECOMMENDED, SPACING, VARIANTS, WORDMARK, mark, params } from "./geometry.mjs";
import { FONTS, outlineText } from "./outline.mjs";
import { area, coords, coverage, extremes, polygons } from "./raster.mjs";
import { drawWordmark } from "./wordmark.mjs";

const r1 = (n) => Math.round(n * 10) / 10;
const r2 = (n) => Math.round(n * 100) / 100;

// ---------- colour (Patina, from techaust_platform packages/ui/tokens/tokens.json; read-only) ----------
export const PALETTE = {
  "ink-950": "#0D1613", "ink-900": "#14231F", "ink-800": "#15211D", "ink-750": "#111C18", "ink-700": "#1B2924",
  "ink-600": "#26352F", "ink-500": "#61796F", "ink-400": "#485752", "ink-300": "#9DB0A8",
  "verdigris-900": "#1F4A40", "verdigris-800": "#175548", "verdigris-700": "#1E6B5C", "verdigris-500": "#2E8B77",
  "verdigris-300": "#6CC4AE", "verdigris-200": "#8AD4C1", "verdigris-100": "#D7ECE5",
  "stone-50": "#F6F7F5", "stone-100": "#ECEFEB", "stone-200": "#E1E6E2", "stone-300": "#D3DBD6", "stone-500": "#75867F",
  mist: "#E4EBE7", white: "#FFFFFF", black: "#000000",
};
// Mock Windows 11 taskbar surfaces: mixed from white and black (no Patina token is a Windows grey). Same mixes as
// the board's CSS (color-mix 95 % white / 87.5 % black).
const mix = (a, b, t) => {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return "#" + x.map((c, i) => Math.round(c * t + y[i] * (1 - t)).toString(16).padStart(2, "0")).join("").toUpperCase();
};
export const TASKBAR = { light: mix(PALETTE.white, PALETTE.black, 0.95), dark: mix(PALETTE.black, PALETTE.white, 0.875) };
export const hex = (k) => PALETTE[k] ?? TASKBAR[k.replace("taskbar-", "")];

const lin = (c) => (c / 255 <= 0.04045 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4);
const lum = (h) => { const n = parseInt(h.slice(1), 16); return 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255); };
export const contrast = (a, b) => { const x = lum(hex(a)), y = lum(hex(b)); return r2((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)); };

// CIELAB and CIEDE2000, for the hue difference between the halves (contrast ratio only sees lightness).
function lab(h) {
  const n = parseInt(hex(h).slice(1), 16);
  const [R, G, B] = [n >> 16, (n >> 8) & 255, n & 255].map(lin);
  const X = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047, Y = 0.2126 * R + 0.7152 * G + 0.0722 * B, Z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116);
  return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
}
export function deltaE2000(a, b) {
  const [L1, a1, b1] = lab(a), [L2, a2, b2] = lab(b);
  const rad = Math.PI / 180, C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2), Cb = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)));
  const ap1 = (1 + G) * a1, ap2 = (1 + G) * a2, Cp1 = Math.hypot(ap1, b1), Cp2 = Math.hypot(ap2, b2);
  const hp = (x, y) => { const v = Math.atan2(y, x) / rad; return v < 0 ? v + 360 : v; };
  const h1 = hp(ap1, b1), h2 = hp(ap2, b2);
  const dL = L2 - L1, dC = Cp2 - Cp1;
  let dh = h2 - h1; if (Math.abs(dh) > 180) dh -= 360 * Math.sign(dh);
  const dH = 2 * Math.sqrt(Cp1 * Cp2) * Math.sin((dh / 2) * rad);
  const Lb = (L1 + L2) / 2, Cpb = (Cp1 + Cp2) / 2;
  let hb = (h1 + h2) / 2; if (Math.abs(h1 - h2) > 180) hb += 180;
  const T = 1 - 0.17 * Math.cos((hb - 30) * rad) + 0.24 * Math.cos(2 * hb * rad) + 0.32 * Math.cos((3 * hb + 6) * rad) - 0.2 * Math.cos((4 * hb - 63) * rad);
  const SL = 1 + (0.015 * (Lb - 50) ** 2) / Math.sqrt(20 + (Lb - 50) ** 2), SC = 1 + 0.045 * Cpb, SH = 1 + 0.015 * Cpb * T;
  const RT = -2 * Math.sqrt(Cpb ** 7 / (Cpb ** 7 + 25 ** 7)) * Math.sin(60 * Math.exp(-(((hb - 275) / 25) ** 2)) * rad);
  return r1(Math.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH)));
}
export const lightness = (h) => r1(lab(h)[0]);

export function contrasts() {
  const rows = [
    ["Ink on white", "ink-900", "white"], ["Verdigris on white", "verdigris-700", "white"],
    ["Ink on stone-50 page", "ink-900", "stone-50"], ["Verdigris on stone-50 page", "verdigris-700", "stone-50"],
    ["Mist on ink-900 (dark app bar)", "mist", "ink-900"], ["Verdigris-300 on ink-900", "verdigris-300", "ink-900"],
    ["Mist on ink-950 (dark page)", "mist", "ink-950"], ["Verdigris-300 on ink-950", "verdigris-300", "ink-950"],
    ["Halves against each other, light (verdigris-700 / ink-900)", "verdigris-700", "ink-900"],
    ["Halves against each other, dark (verdigris-300 / mist)", "verdigris-300", "mist"],
    ["Ink on light taskbar mock", "ink-900", "taskbar-light"], ["Verdigris on light taskbar mock", "verdigris-700", "taskbar-light"],
    ["Mist on dark taskbar mock", "mist", "taskbar-dark"], ["Verdigris-300 on dark taskbar mock", "verdigris-300", "taskbar-dark"],
    ["One colour: ink on white", "ink-900", "white"], ["One colour: white on ink-900", "white", "ink-900"],
  ];
  return rows.map(([label, fg, bg]) => ({ label, fg, bg, ratio: contrast(fg, bg) }));
}

// ---------- colour split ----------
export function shares() {
  const list = [{ id: "p3.1", name: "P3.1 (before)", what: "the whole lower block" }, ...VARIANTS];
  return list.map((vt) => {
    const m = mark(vt.id, undefined, { spurs: vt.id !== "p3.1" });
    const ink = area(m.base), verd = area(m.accent);
    const px16 = rasterShare(vt.id, 16);
    return { id: vt.id, name: vt.name, what: vt.what, ink: r1(ink), verdigris: r1(verd), share: r1((100 * verd) / (ink + verd)), share16: px16 };
  });
}
function rasterShare(id, px) {
  const m = mark(id, px, { spurs: id !== "p3.1" });
  const cb = coverage(m.base, px, 8), ca = coverage(m.accent, px, 8);
  const b = cb.reduce((s, v) => s + v, 0), a = ca.reduce((s, v) => s + v, 0);
  return r1((100 * a) / (a + b));
}

// ---------- pixel fit ----------
export const SIZES = [16, 20, 24, 32, 48, 64]; // 20 and 24: the tray icon at 125 % and 150 % display scale
export function pixelFit(id) {
  return SIZES.map((px) => {
    const m = mark(id, px);
    const nums = [...coords(m.base), ...coords(m.accent)];
    const whole = nums.every((n) => Number.isInteger(n));
    // Every diagonal must be exactly 45 degrees: check each L segment's run equals its rise.
    const diag = [];
    for (const d of [m.base, m.accent]) for (const poly of polygons(d)) for (let k = 0; k < poly.length; k++) {
      const [x1, y1] = poly[k], [x2, y2] = poly[(k + 1) % poly.length];
      if (x1 !== x2 && y1 !== y2) diag.push(Math.abs(x2 - x1) === Math.abs(y2 - y1) && Math.sign(x2 - x1) === -Math.sign(y2 - y1));
    }
    const { p, f } = m;
    const square = p.ch / Math.SQRT2;
    return {
      px, v: p.v, h: p.h, thinned: p.thinned, spur: f.sp, channelRun: p.ch, channelSquare: r2(square), channelVsStroke: r1((100 * square) / p.v),
      spineTop: f.y0, cutInk: f.a, cutVerdigris: f.g, upperCounter: f.y0 - p.h, lowerCounter: f.b0 - f.y1,
      upperOpening: f.y0 - p.h - f.sp, lowerOpening: f.b0 - f.y1 - f.sp,
      whole, diagonals: diag.length, diagonals45slash: diag.every(Boolean), coords: nums.length,
    };
  });
}

/** Coverage grids used for the enlarged rasters (0..1 per pixel, base and accent). */
export function rasters(id, sizes = SIZES, opts = {}) {
  const out = {};
  for (const px of sizes) {
    const m = mark(id, px, opts);
    const n = px <= 32 ? 16 : 8;
    out[px] = { base: [...coverage(m.base, px, n)].map((v) => r2(v)), accent: [...coverage(m.accent, px, n)].map((v) => r2(v)) };
  }
  return out;
}

// ---------- dark split at 16 px ----------
/**
 * Along every spine row at 16 px, how many pixels of pure background (coverage <= 2 %) separate the top block
 * from the lower block, and the longest run of ink touching verdigris with no background between (butt joints).
 */
export function darkSplit(id, px = 16) {
  const m = mark(id, px);
  const cb = coverage(m.base, px, 16), ca = coverage(m.accent, px, 16);
  const { y0, y1 } = m.f;
  const rows = [];
  // On a spine row the mark is inked edge to edge except for the channel, so every clear pixel is channel.
  for (let y = y0; y < y1; y++) {
    let clear = 0;
    for (let x = 0; x < px; x++) if (cb[y * px + x] + ca[y * px + x] <= 0.02) clear++;
    rows.push({ row: y, clear });
  }
  // Butt joints: pairs of 4-neighbour pixels where one is (mostly) ink and the other (mostly) verdigris.
  let joints = 0;
  const isB = (x, y) => cb[y * px + x] >= 0.5, isA = (x, y) => ca[y * px + x] >= 0.5;
  for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
    if (x + 1 < px && ((isB(x, y) && isA(x + 1, y)) || (isA(x, y) && isB(x + 1, y)))) joints++;
    if (y + 1 < px && ((isB(x, y) && isA(x, y + 1)) || (isA(x, y) && isB(x, y + 1)))) joints++;
  }
  // The channel, square to the cut, in pixels.
  return { px, rows, minClear: Math.min(...rows.map((x) => x.clear)), channelSquare: r2(m.p.ch / Math.SQRT2), jointEdges: joints };
}

// ---------- not a 5 ----------
/**
 * A square 5 drawn with the same strokes is the S without its channel and without its spurs. Count the pixels
 * (coverage >= 50 %) where the S differs from the 5 drawn at the same fit: P3.1's S against P3.1's 5, P3.2's S
 * against a 5 with P3.2's strokes.
 */
export function fivePath(id, px) {
  const m = mark(id, px, { spurs: false });
  return m.base + m.accent + `M0 ${m.f.y0}H${px}V${m.f.y1}H0Z`;
}
export function notFive(px = 16) {
  const ink = (d) => [...coverage(d, px, 8)].map((v) => (v >= 0.5 ? 1 : 0));
  const diff = (a, b) => a.reduce((s, v, i) => s + (v !== b[i] ? 1 : 0), 0);
  const p31 = mark("p3.1", px), now = mark(undefined, px);
  return {
    px,
    before: diff(ink(p31.base + p31.accent), ink(fivePath("p3.1", px))),
    after: diff(ink(now.base + now.accent), ink(fivePath(RECOMMENDED, px))),
    spurPixels: 2 * now.p.v * now.f.sp,
  };
}

// ---------- wordmark spacing ----------
/** Mean white per scanline (capped) and the share of scanlines that hit the cap (open counters). */
export function whiteArea(gl, gr, xHeight, cap = WORDMARK.cap) {
  const pl = polygons(gl), pr = polygons(gr);
  let s = 0, n = 0, c = 0;
  for (let y = cap - xHeight + SPACING.step / 2; y < cap; y += SPACING.step) {
    const L = extremes(pl, y), R = extremes(pr, y);
    const w = L && R ? R.lo - L.hi : Infinity;
    if (w >= SPACING.depth) c++;
    s += Math.min(w, SPACING.depth);
    n++;
  }
  return { mean: s / n, capped: c / n };
}

/** Closest approach of two glyphs over their full height (a collision guard for the re-spacing). */
export function closest(gl, gr) {
  const pl = polygons(gl), pr = polygons(gr);
  let m = Infinity;
  for (let y = -10; y < 130; y += 0.25) {
    const L = extremes(pl, y), R = extremes(pr, y);
    if (L && R) m = Math.min(m, R.lo - L.hi);
  }
  return m;
}

async function reference(text = SPACING.reference, axes = WORDMARK.axes, tracking = WORDMARK.tracking) {
  const ref = await outlineText(FONTS.archivo, text, { axes, cap: WORDMARK.cap, tracking });
  return whiteArea(ref.glyphs[0], ref.glyphs[1], ref.xHeight).mean;
}

/** The method checked against TecHaust's published values (docs/11 2.3), with TecHaust's own wordmark settings. */
export async function calibration() {
  const t = await outlineText(FONTS.archivo, "TecHaust", { axes: { wght: 620, wdth: 116 }, cap: 100, tracking: -6 });
  const W = (i) => whiteArea(t.glyphs[i], t.glyphs[i + 1], t.xHeight).mean;
  const rows = [
    { pair: "no", published: 20.3, ours: await reference("no", { wght: 620, wdth: 116 }, -6) },
    { pair: "cH", published: 24.1, ours: W(2) }, { pair: "Ha", published: 23.2, ours: W(3) }, { pair: "st", published: 23.1, ours: W(6) },
  ].map((x) => ({ ...x, ours: r1(x.ours), diff: r1(x.ours - x.published) }));
  return { rows, maxDiff: Math.max(...rows.map((x) => Math.abs(x.diff))) };
}

export async function spacing() {
  const ref = await reference();
  const before = await drawWordmark({ edits: false });
  const after = await drawWordmark({ edits: true });
  const text = WORDMARK.text;
  const pairs = [];
  for (let i = 0; i < text.length - 1; i++) {
    const wb = whiteArea(before.glyphs[i], before.glyphs[i + 1], before.xHeight);
    const wa = whiteArea(after.glyphs[i], after.glyphs[i + 1], after.xHeight);
    const b = wb.mean, a = wa.mean;
    pairs.push({
      pair: text[i] + text[i + 1], before: r1(b), beforeOff: r1((100 * (b - ref)) / ref), after: r1(a), afterOff: r1((100 * (a - ref)) / ref),
      kern: WORDMARK.pairs[i + 1] ?? 0, openBefore: Math.round(100 * wb.capped), openAfter: Math.round(100 * wa.capped), outlier: Math.abs(b - ref) / ref > SPACING.tolerance,
      closestBefore: r1(closest(before.glyphs[i], before.glyphs[i + 1])), closestAfter: r1(closest(after.glyphs[i], after.glyphs[i + 1])),
    });
  }
  return { reference: r1(ref), tolerance: SPACING.tolerance, pairs, cut: after.cut, beforeWidth: before.bounds.x1, afterWidth: after.bounds.x1 };
}

// ---------- ratios ----------
export function ratios() {
  return {
    stroke: MARK.v, horizontal: MARK.h, horizontalThinner: r1((100 * (MARK.v - MARK.h)) / MARK.v),
    channelSquare: r2(MARK.v), channelRun: r2(MARK.v * Math.SQRT2), channelVsStroke: 100,
    spineCentre: MARK.cy, spur: MARK.spur, spurVsStroke: r1((100 * MARK.spur) / MARK.v),
  };
}

export async function all() {
  return {
    shares: shares(), contrasts: contrasts(),
    deltaE: { light: deltaE2000("verdigris-700", "ink-900"), dark: deltaE2000("verdigris-300", "mist"), lightness: { mist: lightness("mist"), "verdigris-300": lightness("verdigris-300"), "ink-900": lightness("ink-900"), "verdigris-700": lightness("verdigris-700") } },
    pixelFit: pixelFit(), darkSplit: Object.fromEntries(["p3.1", ...VARIANTS.map((v) => v.id)].map((id) => [id, darkSplit(id)])),
    notFive: notFive(16), notFive32: notFive(32), ratios: ratios(), calibration: await calibration(), spacing: await spacing(),
    taskbar: TASKBAR, params16: params(16),
  };
}
