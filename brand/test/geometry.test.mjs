// Construction rules of the approved S-cut (05 1.2-1.4, docs/11 2026-10-26): grid, stroke ratio, the channel is
// one stroke, both cuts and the f cut at 45 degrees "/", and the shapes are still exactly the approved P3.2 ones.
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { ENDORSE, FIT_SIZES, LOCKUP, MARK, MINIMUM, STROKE, VERSIONS, WORDMARK, mark } from "../geometry.mjs";
import { layouts } from "../lib/lockups.mjs";
import { coords, polygons } from "../lib/raster.mjs";
import { drawEndorsement, drawWordmark } from "../lib/wordmark.mjs";

const diagonals = (m) => {
  const out = [];
  for (const d of [m.base, m.accent]) for (const poly of polygons(d)) for (let k = 0; k < poly.length; k++) {
    const [x1, y1] = poly[k], [x2, y2] = poly[(k + 1) % poly.length];
    if (x1 !== x2 && y1 !== y2) out.push({ dx: x2 - x1, dy: y2 - y1, from: [x1, y1], to: [x2, y2] });
  }
  return out;
};
// "/" in SVG's y-down space: going down means going left (or up means right).
const isSlash = (e) => Math.sign(e.dx) === -Math.sign(e.dy);

describe("the vector mark", () => {
  const m = mark();
  it("sits on the 100-unit grid", () => {
    expect(MARK.size).toBe(100);
    for (const n of coords(m.base + m.accent)) {
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThanOrEqual(100);
    }
  });
  it("has verticals 19 and horizontals 17.5, about 8 % thinner", () => {
    expect([MARK.v, MARK.h, MARK.cy, MARK.spur]).toEqual([19, 17.5, 48.5, 9]);
    const thinner = (MARK.v - MARK.h) / MARK.v;
    expect(thinner).toBeGreaterThan(0.07);
    expect(thinner).toBeLessThan(0.09);
  });
  it("has one channel, exactly one stroke wide measured square to the cut", () => {
    expect(m.p.ch / Math.SQRT2).toBeCloseTo(MARK.v, 9);
    expect(m.f.g - m.f.a).toBeCloseTo(m.p.ch, 1); // the two cut edges are one channel apart along the spine
  });
  it("cuts both channel edges at 45 degrees, running \"/\"", () => {
    const d = diagonals(m);
    expect(d).toHaveLength(2);
    for (const e of d) {
      expect(Math.abs(Math.abs(e.dx) - Math.abs(e.dy))).toBeLessThan(0.011);
      expect(isSlash(e)).toBe(true);
    }
  });
  it("is still exactly the approved P3.2 shape", () => {
    // Fingerprints of the approved paths (the P3.2 output the owner approved on 2026-10-26). A deliberate design
    // change updates these in a reviewed commit.
    const h = (s) => createHash("sha256").update(s).digest("hex").slice(0, 16);
    const want = { 0: "a9abd60ef7e5c14f", 16: "16b45ffef5957133", 20: "414ab7c8e39f79fe", 24: "e875c0c168318eda", 32: "3feea0cf149048a7", 48: "4aef064a1d56598a", 64: "1c339bc7f619f909" };
    for (const [px, hash] of Object.entries(want)) {
      const mm = mark(Number(px) || undefined);
      expect(h(mm.base + "|" + mm.accent), `${px || "vector"}`).toBe(hash);
    }
  });
});

const word = await drawWordmark();
const { layouts: L } = await layouts();

describe("the wordmark and endorsement", () => {
  it("carries the f-crossbar cut: the full bar height, 45 degrees, \"/\"", () => {
    const c = word.cut;
    expect(c).toBeTruthy();
    expect(c.edge.dy).toBeCloseTo(c.height, 2);
    expect(Math.abs(c.edge.dx)).toBeCloseTo(c.edge.dy, 2);
    expect(c.edge.dx).toBeLessThan(0);
    expect(c.edge.dy).toBeGreaterThan(0);
    expect(word.glyphs[WORDMARK.text.indexOf("f")]).toContain(`L${c.maxX} ${c.barTop}L${c.cutX} ${c.barBottom}`);
  });
  it("keeps the approved settings and outlines", async () => {
    expect(WORDMARK.axes).toEqual({ wght: 620, wdth: 116 });
    expect(WORDMARK.tracking).toBe(-6);
    expect(WORDMARK.pairs).toEqual({ 1: 2, 4: 2, 5: 3, 6: 3, 7: 2 });
    const h = (s) => createHash("sha256").update(s).digest("hex").slice(0, 16);
    expect(h(word.glyphs.join("|"))).toBe("d3ba692a146dbe99");
    expect(h((await drawEndorsement()).d)).toBe("92bff4189815b53e");
    expect(ENDORSE.capRatio).toBe(0.3);
  });
});

describe("lockups and minimums", () => {
  it("places the symbol at 1.28 x the cap height with a two-stroke gap", () => {
    expect(LOCKUP).toEqual({ markScale: 1.28, markY: -14, gap: 48.64 });
    expect(L.primary.parts[1].x).toBeCloseTo(128 + 2 * STROKE * 1.28, 2);
  });
  it("keeps the symbol at 16 px or more at the 119 px primary minimum", () => {
    expect(MINIMUM.primaryWidth).toBe(119);
    expect((MINIMUM.primaryWidth / L.primary.vb[2]) * 128).toBeGreaterThanOrEqual(16);
  });
  it("uses verdigris-700 as the accent in the colour version, verdigris-300 on dark", () => {
    expect(VERSIONS.color).toMatchObject({ base: "ink-900", accent: "verdigris-700" });
    expect(VERSIONS.dark).toMatchObject({ base: "mist", accent: "verdigris-300" });
  });
  it("fits every pixel-fit size the rule needs", () => {
    expect(FIT_SIZES).toEqual([16, 20, 24, 32, 48, 64]);
  });
});
