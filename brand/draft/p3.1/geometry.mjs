// P3.1 concept geometry, on the TecHaust construction (packages/ui/src/brand/geometry.ts, read-only reference):
// vertical stroke 19, horizontal 17.5 (8 % thinner), crossbar centre 48.5 (1.5 above centre), channel = one
// vertical stroke measured square to the 45° cut, so its horizontal run is v·√2. All cuts run "/" like TecHaust's.
// pixel(px) snaps every edge to whole pixels; below 40 px horizontals equal verticals (as TecHaust's pixelMark).

const r = (n) => Math.round(n * 100) / 100;

export function params(size, pixel = false) {
  if (!pixel) {
    const v = 19, h = 17.5;
    return { S: 100, v, h, cy: 48.5, ch: v * Math.SQRT2, q: r };
  }
  const v = Math.max(2, Math.round(size * 0.19));
  const h = size < 40 ? v : Math.round(size * 0.175);
  return { S: size, v, h, cy: size * 0.485, ch: Math.round(v * Math.SQRT2), q: Math.round };
}

const mid = (p) => {
  const y0 = p.q(p.cy - p.h / 2);
  return { y0, y1: y0 + p.h };
};

/** 1 Shelves: an ink upright with two shelves; the verdigris bar slides in on the middle shelf. */
export function shelves(p) {
  const { S, v, h, ch, q } = p;
  const { y0, y1 } = mid(p);
  const R = S - v; // the ink shelves stop one stroke short; the verdigris bar runs to the edge (still sliding in)
  const a = q(v + 1.5 * h); // top of the ink stub's cut
  const g = r(a + ch); // top of the verdigris bar's cut
  return {
    base: `M0 0H${R}V${h}H${v}V${y0}H${a}L${r(a - h)} ${y1}H${v}V${r(S - h)}H${R}V${S}H0Z`,
    accent: `M${g} ${y0}H${S}V${y1}H${r(g - h)}Z`,
    channel: { a, y0, y1, h },
  };
}

/** 2 S-cut: an S from two offset blocks; the channel splits the spine, centred on the mark. */
export function sCut(p) {
  const { S, v, h, ch, cy, q } = p;
  const { y0, y1 } = mid(p);
  const c1 = S / 2 + cy - ch / 2; // the ink cut's line, x + y = c1
  const a = q(c1 - y0);
  const g = r(a + ch);
  return {
    base: `M0 0H${S}V${h}H${v}V${y0}H${a}L${r(a - h)} ${y1}H0Z`,
    accent: `M${g} ${y0}H${S}V${S}H0V${r(S - h)}H${r(S - v)}V${y1}H${r(g - h)}Z`,
    channel: { a, y0, y1, h },
  };
}

/** 3 One to many: one ink block (bar + stem); the channel's far edge cuts the tops of two verdigris stems. */
export function oneToMany(p) {
  const { S, v, h, ch, q } = p;
  const c1 = r(S - ch); // the ink bar's cut (top); the far edge of the channel is x + y = S
  const m = q((S - v) / 2); // middle stem
  return {
    base: `M0 0H${c1}L${r(c1 - h)} ${h}H${v}V${S}H0Z`,
    accent: `M${r(S - v)} ${v}L${S} 0V${S}H${r(S - v)}ZM${m} ${r(S - m)}L${r(m + v)} ${r(S - m - v)}V${S}H${m}Z`,
    channel: { a: c1, y0: 0, y1: h, h },
  };
}

export const CONCEPTS = [
  { id: "1-shelves", name: "Shelves", fn: shelves },
  { id: "2-s-cut", name: "S-cut", fn: sCut },
  { id: "3-one-to-many", name: "One to many", fn: oneToMany },
];
