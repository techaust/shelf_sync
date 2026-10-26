// Every number the tests, the measurements file and the review page report, computed from geometry.mjs and
// tokens.json (never typed in by hand).
import { FIT_SIZES, MARK, mark } from "../geometry.mjs";
import { area, coords, coverage, polygons } from "./raster.mjs";
import { contrast, semantic } from "./tokens.mjs";

const r1 = (n) => Math.round(n * 10) / 10;
const r2 = (n) => Math.round(n * 100) / 100;

/** Verdigris share of the inked area: exact for the vector, coverage-weighted at 16 px. */
export function share() {
  const m = mark();
  const ink = area(m.base), verd = area(m.accent);
  const m16 = mark(16);
  const cb = coverage(m16.base, 16, 8), ca = coverage(m16.accent, 16, 8);
  const b = cb.reduce((s, v) => s + v, 0), a = ca.reduce((s, v) => s + v, 0);
  return { vector: r1((100 * verd) / (ink + verd)), px16: r1((100 * a) / (a + b)) };
}

/** The pixel fit at every fitted size: whole-pixel edges, both cuts 45 degrees "/", openings, the channel. */
export function pixelFit(sizes = FIT_SIZES) {
  return sizes.map((px) => {
    const m = mark(px);
    const nums = [...coords(m.base), ...coords(m.accent)];
    const diag = [];
    for (const d of [m.base, m.accent]) for (const poly of polygons(d)) for (let k = 0; k < poly.length; k++) {
      const [x1, y1] = poly[k], [x2, y2] = poly[(k + 1) % poly.length];
      if (x1 !== x2 && y1 !== y2) diag.push({ run: x2 - x1, rise: y2 - y1 });
    }
    const { p, f } = m;
    const square = p.ch / Math.SQRT2;
    return {
      px, v: p.v, h: p.h, thinned: p.thinned, spur: f.sp, channelRun: p.ch, channelSquare: r2(square), channelVsStroke: r1((100 * square) / p.v),
      upperOpening: f.y0 - p.h - f.sp, lowerOpening: f.b0 - f.y1 - f.sp,
      whole: nums.every((n) => Number.isInteger(n)), coords: nums.length,
      diagonals: diag.length, slash45: diag.every((e) => Math.abs(e.run) === Math.abs(e.rise) && Math.sign(e.run) === -Math.sign(e.rise)),
    };
  });
}

/** On every spine row at 16 px, the clear (background) pixels between the blocks: the channel. */
export function channelClear(px = 16) {
  const m = mark(px);
  const cb = coverage(m.base, px, 16), ca = coverage(m.accent, px, 16);
  const rows = [];
  for (let y = m.f.y0; y < m.f.y1; y++) {
    let clear = 0;
    for (let x = 0; x < px; x++) if (cb[y * px + x] + ca[y * px + x] <= 0.02) clear++;
    rows.push(clear);
  }
  return { rows, min: Math.min(...rows) };
}

/** The vector construction numbers. */
export const ratios = () => ({
  stroke: MARK.v, horizontal: MARK.h, horizontalThinner: r1((100 * (MARK.v - MARK.h)) / MARK.v),
  channelSquare: r2((mark().p.ch / Math.SQRT2)), spineCentre: MARK.cy, spur: MARK.spur,
});

/**
 * Every contrast pair stated in 05 (2.2, 2.3) and 14 (2.6), with the value the doc states, and the new pairs this
 * task adds (tray badges on the taskbar mocks, installer art). `min` is the WCAG level the pair must meet.
 * `docMismatch`: the value 05 states (copied from TecHaust's table) is not what tokens.json gives; the pair still
 * passes its level. Reported for the lead to correct in 05 (the test fails if the doc value ever starts to match,
 * so the flag is removed with the fix).
 */
/** A status colour as its semantic token, e.g. st("info", "light"), shown by name on the review page. */
const st = (name, theme) => ({ fg: semantic(name, theme), fgName: `${name} (${theme})` });

export const PAIRS = [
  // 05 2.2, light
  { doc: "05 2.2", label: "Text on page (light)", fg: "ink-900", bg: "stone-50", stated: 15.2, min: 7 },
  { doc: "05 2.2", label: "Muted text on page (light)", fg: "ink-400", bg: "stone-50", stated: 7.1, min: 7 },
  { doc: "05 2.2", label: "Muted text on alternate section (light)", fg: "ink-400", bg: "stone-100", stated: 6.6, min: 4.5 },
  { doc: "05 2.2", label: "Accent text on page (light)", fg: "verdigris-700", bg: "stone-50", stated: 5.9, min: 4.5 },
  { doc: "05 2.2", label: "Accent text on alternate section (light)", fg: "verdigris-700", bg: "stone-100", stated: 5.5, min: 4.5 },
  { doc: "05 2.2", label: "Button label on primary (light)", fg: "white", bg: "verdigris-700", stated: 6.3, min: 4.5 },
  { doc: "05 2.2", label: "Button label on primary hover (light)", fg: "white", bg: "verdigris-800", stated: 8.6, min: 4.5 },
  { doc: "05 2.2", label: "Control border on page (light)", fg: "stone-500", bg: "stone-50", stated: 3.3, min: 3, docMismatch: true },
  { doc: "05 2.2", label: "Control border on card (light)", fg: "stone-500", bg: "white", stated: 3.6, min: 3, docMismatch: true },
  { doc: "05 2.2", label: "Focus ring on page (light)", fg: "verdigris-700", bg: "stone-50", stated: 5.9, min: 3 },
  { doc: "05 2.2", label: "Decorative verdigris on page (light)", fg: "verdigris-500", bg: "stone-50", stated: 3.9, min: 3 },
  { doc: "05 2.2", label: "Success on page (light)", ...st("success", "light"), bg: "stone-50", stated: 5.2, min: 4.5, docMismatch: true },
  { doc: "05 2.2", label: "Warning on page (light)", ...st("warning", "light"), bg: "stone-50", stated: 5.3, min: 4.5 },
  { doc: "05 2.2", label: "Danger on page (light)", ...st("danger", "light"), bg: "stone-50", stated: 6.1, min: 4.5 },
  { doc: "05 2.2", label: "Info on page (light)", ...st("info", "light"), bg: "stone-50", stated: 6.7, min: 4.5 },
  // 05 2.2, dark
  { doc: "05 2.2", label: "Text on page (dark)", fg: "mist", bg: "ink-950", stated: 15.2, min: 7 },
  { doc: "05 2.2", label: "Muted text on page (dark)", fg: "ink-300", bg: "ink-950", stated: 8.1, min: 7 },
  { doc: "05 2.2", label: "Muted text on alternate section (dark)", fg: "ink-300", bg: "ink-750", stated: 7.7, min: 4.5 },
  { doc: "05 2.2", label: "Accent text on page (dark)", fg: "verdigris-300", bg: "ink-950", stated: 8.9, min: 4.5 },
  { doc: "05 2.2", label: "Accent text on alternate section (dark)", fg: "verdigris-300", bg: "ink-750", stated: 8.4, min: 4.5 },
  { doc: "05 2.2", label: "Button label on primary (dark)", fg: "ink-950", bg: "verdigris-300", stated: 8.9, min: 4.5 },
  { doc: "05 2.2", label: "Button label on primary hover (dark)", fg: "ink-950", bg: "verdigris-200", stated: 10.8, min: 4.5 },
  { doc: "05 2.2", label: "Control border on page (dark)", fg: "ink-500", bg: "ink-950", stated: 3.9, min: 3 },
  { doc: "05 2.2", label: "Control border on card (dark)", fg: "ink-500", bg: "ink-800", stated: 3.5, min: 3 },
  { doc: "05 2.2", label: "Control border on dialog (dark)", fg: "ink-500", bg: "ink-700", stated: 3.2, min: 3 },
  { doc: "05 2.2", label: "Focus ring on page (dark)", fg: "verdigris-300", bg: "ink-950", stated: 8.9, min: 3 },
  { doc: "05 2.2", label: "Decorative verdigris on page (dark)", fg: "verdigris-300", bg: "ink-950", stated: 8.9, min: 3 },
  { doc: "05 2.2", label: "Success on page (dark)", ...st("success", "dark"), bg: "ink-950", stated: 10.8, min: 4.5 },
  { doc: "05 2.2", label: "Warning on page (dark)", ...st("warning", "dark"), bg: "ink-950", stated: 9.7, min: 4.5 },
  { doc: "05 2.2", label: "Danger on page (dark)", ...st("danger", "dark"), bg: "ink-950", stated: 8.1, min: 4.5 },
  { doc: "05 2.2", label: "Info on page (dark)", ...st("info", "dark"), bg: "ink-950", stated: 8.9, min: 4.5 },
  // 05 2.2, app bar (ShelfSync additions)
  { doc: "05 2.2", label: "Mist on the light app bar (ink-900)", fg: "mist", bg: "ink-900", stated: 13.4, min: 7 },
  { doc: "05 2.2", label: "Mist on the dark app bar (ink-750)", fg: "mist", bg: "ink-750", stated: 14.4, min: 7 },
  { doc: "05 2.2", label: "Muted ink-300 on the light app bar", fg: "ink-300", bg: "ink-900", stated: 7.1, min: 7 },
  { doc: "05 2.2", label: "Muted ink-300 on the dark app bar", fg: "ink-300", bg: "ink-750", stated: 7.7, min: 7 },
  { doc: "05 2.2", label: "Focus ring on the light app bar", fg: "verdigris-300", bg: "ink-900", stated: 7.9, min: 3 },
  { doc: "05 2.2", label: "Focus ring on the dark app bar", fg: "verdigris-300", bg: "ink-750", stated: 8.4, min: 3 },
  // 05 2.3, store identifiers (literal hex: store colours are identifiers, not tokens)
  { doc: "05 2.3", label: "GPLFamily dot (light) on stone-200", fg: "#4D4D99", bg: "stone-200", stated: 5.9, min: 3 },
  { doc: "05 2.3", label: "GPLFamily dot (dark) on verdigris-900", fg: "#A3A3E6", bg: "verdigris-900", stated: 4.2, min: 3 },
  { doc: "05 2.3", label: "PluginWay dot (light) on stone-200", fg: "#007B80", bg: "stone-200", stated: 4.0, min: 3 },
  { doc: "05 2.3", label: "PluginWay dot (dark) on verdigris-900", fg: "#3CC8CB", bg: "verdigris-900", stated: 4.9, min: 3 },
  { doc: "05 2.3", label: "PluginWay's own teal on stone-200 (why it isn't used)", fg: "#009699", bg: "stone-200", stated: 2.85, max: 3, places: 2 },
  // 14 2.6, the mark
  { doc: "14 2.6", label: "Ink-900 on white", fg: "ink-900", bg: "white", stated: 16.28, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-700 on white", fg: "verdigris-700", bg: "white", stated: 6.34, min: 3, places: 2 },
  { doc: "14 2.6", label: "Ink-900 on stone-50", fg: "ink-900", bg: "stone-50", stated: 15.15, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-700 on stone-50", fg: "verdigris-700", bg: "stone-50", stated: 5.9, min: 3, places: 2 },
  { doc: "14 2.6", label: "Mist on ink-900", fg: "mist", bg: "ink-900", stated: 13.44, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-300 on ink-900", fg: "verdigris-300", bg: "ink-900", stated: 7.86, min: 3, places: 2 },
  { doc: "14 2.6", label: "Mist on ink-950", fg: "mist", bg: "ink-950", stated: 15.19, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-300 on ink-950", fg: "verdigris-300", bg: "ink-950", stated: 8.89, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-700 on the light taskbar mock", fg: "verdigris-700", bg: "taskbar-light", stated: 5.66, min: 3, places: 2 },
  { doc: "14 2.6", label: "Verdigris-300 on the dark taskbar mock", fg: "verdigris-300", bg: "taskbar-dark", stated: 7.87, min: 3, places: 2 },
  { doc: "14 2.6", label: "The halves against each other, light (no minimum: the channel separates them)", fg: "verdigris-700", bg: "ink-900", stated: 2.57, places: 2 },
  { doc: "14 2.6", label: "The halves against each other, dark (no minimum)", fg: "verdigris-300", bg: "mist", stated: 1.71, places: 2 },
  // New in P3.3: tray icons on the taskbar mocks, the installer art and the GitHub images
  { doc: "P3.3", label: "Ink-900 mark on the light taskbar mock", fg: "ink-900", bg: "taskbar-light", min: 3 },
  { doc: "P3.3", label: "Mist mark on the dark taskbar mock", fg: "mist", bg: "taskbar-dark", min: 3 },
  { doc: "P3.3", label: "Paused badge, info (light) on the light taskbar mock", ...st("info", "light"), bg: "taskbar-light", min: 3 },
  { doc: "P3.3", label: "Paused badge, info (dark) on the dark taskbar mock", ...st("info", "dark"), bg: "taskbar-dark", min: 3 },
  { doc: "P3.3", label: "Attention dot, warning (light) on the light taskbar mock", ...st("warning", "light"), bg: "taskbar-light", min: 3 },
  { doc: "P3.3", label: "Attention dot, warning (dark) on the dark taskbar mock", ...st("warning", "dark"), bg: "taskbar-dark", min: 3 },
  { doc: "P3.3", label: "Mist symbol on the app-icon plate (ink-900)", fg: "mist", bg: "ink-900", min: 3 },
  { doc: "P3.3", label: "App-icon plate (ink-900) on white (Explorer, light)", fg: "ink-900", bg: "white", min: 3 },
  { doc: "P3.3", label: "Mist caption on the installer panel (ink-900)", fg: "mist", bg: "ink-900", min: 4.5 },
  { doc: "P3.3", label: "Ink caption on the installer header (white)", fg: "ink-900", bg: "white", min: 4.5 },
  { doc: "P3.3", label: "Tone-on-tone watermark (ink-700 on ink-900; decoration, no minimum)", fg: "ink-700", bg: "ink-900" },
];

export function contrasts() {
  return PAIRS.map((p) => {
    const ratio = contrast(p.fg, p.bg);
    const places = p.places ?? 1;
    const shown = Number(ratio.toFixed(places));
    // A stated value matches if it is the ratio rounded to its places, allowing for rounding a 2-place value again.
    const tol = places === 1 ? 0.06 : 0.006;
    return { ...p, ratio: r2(ratio), shown, matches: p.stated === undefined || Math.abs(ratio - p.stated) <= tol, passes: (p.min === undefined || ratio >= p.min) && (p.max === undefined || ratio < p.max) };
  });
}
