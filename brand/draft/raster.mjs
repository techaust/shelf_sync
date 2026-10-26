// Geometry helpers with no dependencies: path -> polygons, exact areas, supersampled pixel coverage, and the
// left/right ink extremes of a glyph on a scanline (for the wordmark's white-area measurement).

/** Absolute path (M L H V Q C Z) -> list of closed polygons [[x, y], ...]; curves flattened to `seg` lines. */
export function polygons(d, seg = 16) {
  const t = d.match(/[MLHVQCZ]|-?\d*\.?\d+(?:e-?\d+)?/gi) ?? [];
  const polys = [];
  let cur = null;
  let x = 0;
  let y = 0;
  let i = 0;
  const num = () => Number(t[i++]);
  while (i < t.length) {
    const c = t[i++].toUpperCase();
    if (c === "M") { x = num(); y = num(); cur = [[x, y]]; polys.push(cur); }
    else if (c === "L") { x = num(); y = num(); cur.push([x, y]); }
    else if (c === "H") { x = num(); cur.push([x, y]); }
    else if (c === "V") { y = num(); cur.push([x, y]); }
    else if (c === "Q") {
      const [cx, cy, ex, ey] = [num(), num(), num(), num()];
      for (let k = 1; k <= seg; k++) {
        const s = k / seg, u = 1 - s;
        cur.push([u * u * x + 2 * u * s * cx + s * s * ex, u * u * y + 2 * u * s * cy + s * s * ey]);
      }
      x = ex; y = ey;
    } else if (c === "C") {
      const [c1x, c1y, c2x, c2y, ex, ey] = [num(), num(), num(), num(), num(), num()];
      for (let k = 1; k <= seg; k++) {
        const s = k / seg, u = 1 - s;
        cur.push([u ** 3 * x + 3 * u * u * s * c1x + 3 * u * s * s * c2x + s ** 3 * ex, u ** 3 * y + 3 * u * u * s * c1y + 3 * u * s * s * c2y + s ** 3 * ey]);
      }
      x = ex; y = ey;
    } else if (c === "Z") { if (cur) { x = cur[0][0]; y = cur[0][1]; } }
  }
  return polys.filter((p) => p.length > 2);
}

/** Signed shoelace area summed over subpaths; exact for straight-edged, non-overlapping paths (the mark). */
export function area(d) {
  let a = 0;
  for (const p of polygons(d)) {
    for (let k = 0; k < p.length; k++) {
      const [x1, y1] = p[k];
      const [x2, y2] = p[(k + 1) % p.length];
      a += x1 * y2 - x2 * y1;
    }
  }
  return Math.abs(a / 2);
}

function winding(polys, px, py) {
  let w = 0;
  for (const p of polys) {
    for (let k = 0; k < p.length; k++) {
      const [x1, y1] = p[k];
      const [x2, y2] = p[(k + 1) % p.length];
      if (y1 <= py) { if (y2 > py && (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1) > 0) w++; }
      else if (y2 <= py && (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1) < 0) w--;
    }
  }
  return w;
}

/** Per-pixel coverage (0..1) of path `d` on a size x size grid, n x n samples per pixel (nonzero rule). */
export function coverage(d, size, n = 16) {
  const polys = polygons(d);
  const out = new Float64Array(size * size);
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      let hit = 0;
      for (let sy = 0; sy < n; sy++) for (let sx = 0; sx < n; sx++) {
        if (winding(polys, px + (sx + 0.5) / n, py + (sy + 0.5) / n) !== 0) hit++;
      }
      out[py * size + px] = hit / (n * n);
    }
  }
  return out;
}

/** Leftmost and rightmost ink of a glyph on the horizontal line y (null where the line misses the glyph). */
export function extremes(polys, y) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const p of polys) {
    for (let k = 0; k < p.length; k++) {
      const [x1, y1] = p[k];
      const [x2, y2] = p[(k + 1) % p.length];
      if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
        const x = x1 + ((y - y1) / (y2 - y1)) * (x2 - x1);
        if (x < lo) lo = x;
        if (x > hi) hi = x;
      }
    }
  }
  return lo === Infinity ? null : { lo, hi };
}

/** Every number in a path, for the whole-pixel check. */
export const coords = (d) => (d.match(/-?\d*\.?\d+(?:e-?\d+)?/g) ?? []).map(Number);
