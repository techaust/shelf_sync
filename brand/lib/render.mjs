// The rasterizer behind every PNG, ICO and BMP (no sharp): an exact-area scanline renderer built on raster.mjs's
// path flattening. Each pixel row is sampled on `sub` horizontal lines; on each line the covered spans are added
// with their exact horizontal overlap per pixel. So vertical and horizontal edges on whole pixels give coverage of
// exactly 0 or 1, and a 45 degree edge from pixel corner to pixel corner gives exactly 0.5 (the pixel-fit tests rely
// on this). Colours that touch without overlapping (the mark's ink and verdigris) are drawn as one layer, so no
// seam shows where they meet.
import { polygons } from "./raster.mjs";
import { rgb } from "./tokens.mjs";

/** Coverage (0..1) of path `d` drawn with x' = s*x + dx, y' = s*y + dy on a w x h grid (nonzero rule). */
export function scanCoverage(d, w, h, { s = 1, dx = 0, dy = 0, sub = 16, seg = 24 } = {}) {
  const edges = [];
  for (const poly of polygons(d, seg)) {
    for (let k = 0; k < poly.length; k++) {
      const [x1, y1] = poly[k];
      const [x2, y2] = poly[(k + 1) % poly.length];
      const X1 = s * x1 + dx, Y1 = s * y1 + dy, X2 = s * x2 + dx, Y2 = s * y2 + dy;
      if (Y1 === Y2) continue;
      const down = Y2 > Y1;
      const [ya, yb, xa] = down ? [Y1, Y2, X1] : [Y2, Y1, X2];
      edges.push({ ya, yb, xa, k: (X2 - X1) / (Y2 - Y1), dir: down ? 1 : -1 });
    }
  }
  edges.sort((a, b) => a.ya - b.ya);
  const out = new Float32Array(w * h);
  const row = new Float64Array(w + 1);
  const wgt = 1 / sub;
  const add = (x0, x1) => {
    if (x1 <= 0 || x0 >= w) return;
    x0 = Math.max(0, x0);
    x1 = Math.min(w, x1);
    const i0 = Math.floor(x0), i1 = Math.floor(x1);
    if (i0 === i1) { row[i0] += (x1 - x0) * wgt; return; }
    row[i0] += (i0 + 1 - x0) * wgt;
    for (let i = i0 + 1; i < i1; i++) row[i] += wgt;
    if (i1 < w) row[i1] += (x1 - i1) * wgt;
  };
  let next = 0;
  let active = [];
  const xs = [];
  for (let py = 0; py < h; py++) {
    while (next < edges.length && edges[next].ya < py + 1) active.push(edges[next++]);
    active = active.filter((e) => e.yb > py);
    if (!active.length) continue;
    row.fill(0);
    for (let si = 0; si < sub; si++) {
      const y = py + (si + 0.5) / sub;
      xs.length = 0;
      for (const e of active) if (e.ya <= y && y < e.yb) xs.push([e.xa + (y - e.ya) * e.k, e.dir]);
      if (!xs.length) continue;
      xs.sort((a, b) => a[0] - b[0]);
      let wind = 0, start = 0;
      for (const [x, dir] of xs) {
        const was = wind;
        wind += dir;
        if (was === 0 && wind !== 0) start = x;
        else if (was !== 0 && wind === 0) add(start, x);
      }
    }
    for (let px = 0; px < w; px++) out[py * w + px] = Math.min(1, row[px]);
  }
  return out;
}

const unit = (c) => (Array.isArray(c) ? c : rgb(c)).map((v) => v / 255);

/** An RGBA canvas, premultiplied, in floats; `pixels()` gives straight 8-bit RGBA. */
export class Canvas {
  constructor(w, h) {
    this.w = w;
    this.h = h;
    this.p = new Float64Array(w * h * 4);
  }
  /** Opaque fill of the whole canvas. */
  fill(color) {
    const [r, g, b] = unit(color);
    for (let i = 0; i < this.w * this.h; i++) this.p.set([r, g, b, 1], i * 4);
    return this;
  }
  /**
   * Draws `layers` ([{ d, color }], non-overlapping shapes, e.g. a mark's ink and verdigris) as one layer: the
   * alpha is the summed coverage and the colour the coverage-weighted mix, so shared edges leave no seam.
   */
  draw(layers, t = {}) {
    const cov = layers.map((l) => scanCoverage(l.d, this.w, this.h, t));
    const cols = layers.map((l) => unit(l.color));
    for (let i = 0; i < this.w * this.h; i++) {
      let s = 0, r = 0, g = 0, b = 0;
      for (let k = 0; k < cov.length; k++) {
        const c = cov[k][i];
        if (!c) continue;
        s += c; r += c * cols[k][0]; g += c * cols[k][1]; b += c * cols[k][2];
      }
      if (!s) continue;
      const a = Math.min(1, s);
      const o = i * 4, inv = 1 - a;
      this.p[o] = (r / s) * a + this.p[o] * inv;
      this.p[o + 1] = (g / s) * a + this.p[o + 1] * inv;
      this.p[o + 2] = (b / s) * a + this.p[o + 2] * inv;
      this.p[o + 3] = a + this.p[o + 3] * inv;
    }
    return this;
  }
  /**
   * Clears what `d` covers (to transparent), e.g. the gap around a tray badge. With `snap`, any pixel the shape
   * touches at all is cleared completely, so a knockout never leaves a half-transparent pixel of ink behind.
   */
  erase(d, t = {}, { snap = false } = {}) {
    const cov = scanCoverage(d, this.w, this.h, t);
    for (let i = 0; i < this.w * this.h; i++) {
      if (!cov[i]) continue;
      const k = snap ? 0 : 1 - cov[i];
      for (let c = 0; c < 4; c++) this.p[i * 4 + c] *= k;
    }
    return this;
  }
  /** Straight (not premultiplied) 8-bit RGBA. */
  pixels() {
    const out = new Uint8Array(this.w * this.h * 4);
    for (let i = 0; i < this.w * this.h; i++) {
      const a = this.p[i * 4 + 3];
      if (a <= 0) continue;
      for (let c = 0; c < 3; c++) out[i * 4 + c] = Math.max(0, Math.min(255, Math.round((255 * this.p[i * 4 + c]) / a)));
      out[i * 4 + 3] = Math.round(255 * Math.min(1, a));
    }
    return out;
  }
}

/** Path helpers in absolute coordinates. */
export const rectPath = (x, y, w, h) => `M${x} ${y}H${x + w}V${y + h}H${x}Z`;
export function circlePath(cx, cy, rad) {
  const k = 0.5522847498 * rad;
  const f = (n) => Math.round(n * 10000) / 10000;
  return `M${f(cx + rad)} ${f(cy)}C${f(cx + rad)} ${f(cy + k)} ${f(cx + k)} ${f(cy + rad)} ${f(cx)} ${f(cy + rad)}` +
    `C${f(cx - k)} ${f(cy + rad)} ${f(cx - rad)} ${f(cy + k)} ${f(cx - rad)} ${f(cy)}` +
    `C${f(cx - rad)} ${f(cy - k)} ${f(cx - k)} ${f(cy - rad)} ${f(cx)} ${f(cy - rad)}` +
    `C${f(cx + k)} ${f(cy - rad)} ${f(cx + rad)} ${f(cy - k)} ${f(cx + rad)} ${f(cy)}Z`;
}
/** A rounded rectangle (radius 0 gives a plain rectangle). */
export function roundRectPath(x, y, w, h, rad) {
  if (!rad) return rectPath(x, y, w, h);
  const k = (1 - 0.5522847498) * rad;
  return `M${x + rad} ${y}H${x + w - rad}C${x + w - k} ${y} ${x + w} ${y + k} ${x + w} ${y + rad}V${y + h - rad}` +
    `C${x + w} ${y + h - k} ${x + w - k} ${y + h} ${x + w - rad} ${y + h}H${x + rad}C${x + k} ${y + h} ${x} ${y + h - k} ${x} ${y + h - rad}` +
    `V${y + rad}C${x} ${y + k} ${x + k} ${y} ${x + rad} ${y}Z`;
}
