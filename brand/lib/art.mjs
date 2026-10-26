// Installer art (NSIS Modern UI) and the GitHub images, drawn on the canvas from the lockup layouts.
import { FIT_SIZES, GITHUB, INSTALLER, MARK, VERSIONS, mark } from "../geometry.mjs";
import { layouts } from "./lockups.mjs";
import { Canvas } from "./render.mjs";

const near = (n) => Math.abs(n - Math.round(n)) < 1e-6;

/**
 * Draws lockup `L` with its top-left corner at pixel (X, Y), `u` px per unit. A mark that lands on a fitted size
 * at whole pixels is drawn pixel-fitted; otherwise the vector is scaled. Returns the mark's placement.
 */
export function drawLockup(c, L, word, version, X, Y, u) {
  const v = VERSIONS[version];
  const ox = X - L.vb[0] * u, oy = Y - L.vb[1] * u;
  let placed = null;
  for (const p of L.parts) {
    const x = ox + p.x * u, y = oy + p.y * u;
    if (p.kind === "mark") {
      const size = p.size * u;
      const fit = near(size) && near(x) && near(y) && FIT_SIZES.includes(Math.round(size));
      const m = fit ? mark(Math.round(size)) : mark();
      const t = fit ? { dx: Math.round(x), dy: Math.round(y) } : { s: size / MARK.size, dx: x, dy: y };
      c.draw([{ d: m.base, color: v.base }, { d: m.accent, color: v.accent }], t);
      placed = { x, y, size, fitted: fit };
    } else if (p.kind === "word") {
      c.draw([{ d: word.glyphs.filter(Boolean).join(""), color: v.text }], { s: u, dx: x, dy: y });
    } else {
      c.draw([{ d: p.d, color: v.text }], { s: u, dx: x, dy: y });
    }
  }
  return placed;
}

/** The symbol tone-on-tone, cropped by the canvas edge (the one bold gesture, as TecHaust's banners). */
const watermark = (c, w) => {
  const m = mark();
  c.draw([{ d: m.base + m.accent, color: w.tone }], { s: w.size / MARK.size, dx: w.x, dy: w.y });
};

/** Every art canvas, with the facts the tests and the review page check. */
export async function artCanvases() {
  const { word, layouts: L } = await layouts();
  const out = {};

  { // NSIS welcome / finish side panel
    const P = INSTALLER.panel;
    const c = new Canvas(P.width, P.height).fill(P.bg);
    watermark(c, P.watermark);
    const placed = drawLockup(c, L.stacked, word, P.version, P.x, P.y, L.stacked.unitPx);
    out.panel = { canvas: c, placed, box: { x: P.x, y: P.y, w: L.stacked.vb[2] * L.stacked.unitPx, h: L.stacked.vb[3] * L.stacked.unitPx }, unitPx: L.stacked.unitPx };
  }
  { // NSIS header, compact endorsed lockup, right-aligned, centred vertically
    const H = INSTALLER.header;
    const u = L.compact.unitPx;
    const w = L.compact.vb[2] * u, h = L.compact.vb[3] * u;
    const X = Math.floor(H.width - H.right - w), Y = Math.round((H.height - h) / 2);
    const c = new Canvas(H.width, H.height).fill(H.bg);
    const placed = drawLockup(c, L.compact, word, H.version, X, Y, u);
    out.header = { canvas: c, placed, box: { x: X, y: Y, w, h }, unitPx: u };
  }
  { // GitHub social preview
    const S = GITHUB.social;
    const u = S.lockupWidth / L.endorsed.vb[2];
    const h = L.endorsed.vb[3] * u;
    const c = new Canvas(S.width, S.height).fill(S.bg);
    watermark(c, S.watermark);
    const Y = Math.round((S.height - h) / 2);
    drawLockup(c, L.endorsed, word, S.version, S.x, Y, u);
    out.social = { canvas: c, box: { x: S.x, y: Y, w: S.lockupWidth, h }, unitPx: u };
  }
  for (const theme of ["light", "dark"]) { // README header, transparent
    const R = GITHUB.readme;
    const u = R.lockupWidth / L.endorsed.vb[2];
    const h = L.endorsed.vb[3] * u;
    const stroke = 19 * 1.28 * u;
    const X = Math.ceil(stroke), Y = Math.round((R.height - h) / 2);
    const c = new Canvas(R.width, R.height);
    drawLockup(c, L.endorsed, word, theme === "light" ? "color" : "dark", X, Y, u);
    out[`readme-${theme}`] = { canvas: c, box: { x: X, y: Y, w: R.lockupWidth, h }, unitPx: u };
  }
  return out;
}
