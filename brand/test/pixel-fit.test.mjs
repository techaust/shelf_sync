// Pixel fit at every raster size (05 1.4): every edge on a whole pixel, both cuts 45 degrees "/", the 16 px
// exception, and the same fit read back from the generated ICO and BMP files.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { APP_ICON, FIT_SIZES, INSTALLER, TRAY, VERSIONS, mark, params } from "../geometry.mjs";
import { artCanvases } from "../lib/art.mjs";
import { decodeBmp, decodeIco } from "../lib/formats.mjs";
import { badgeGeometry } from "../lib/icons.mjs";
import { channelClear, pixelFit } from "../lib/measure.mjs";
import { scanCoverage } from "../lib/render.mjs";
import { rgb } from "../lib/tokens.mjs";

const file = (f) => readFileSync(new URL(`../${f}`, import.meta.url));

describe("the fitted mark at 16, 20, 24, 32, 48 and 64 px", () => {
  const fits = pixelFit();
  it.each(fits.map((f) => [f.px, f]))("%i px: whole pixels, two 45 degree \"/\" cuts, openings and spurs of 2 px or more", (px, f) => {
    expect(f.whole).toBe(true);
    expect(f.coords).toBe(26); // every number in both paths (H and V carry one), all whole pixels
    expect(f.diagonals).toBe(2);
    expect(f.slash45).toBe(true);
    expect(f.upperOpening).toBeGreaterThanOrEqual(2);
    expect(f.lowerOpening).toBeGreaterThanOrEqual(2);
    expect(f.spur).toBeGreaterThanOrEqual(2);
    expect(f.channelVsStroke).toBeGreaterThan(90);
    expect(f.channelVsStroke).toBeLessThan(110);
  });
  it("follows TecHaust's pixelMark rule, with the owner's 16 px exception only", () => {
    for (const px of FIT_SIZES) {
      const p = params(px);
      expect(p.v).toBe(Math.max(2, Math.round(px * 0.19)));
      expect(p.ch).toBe(Math.round(p.v * Math.SQRT2));
      if (px === 16) expect([p.v, p.h]).toEqual([3, 2]);
      else if (px < 40) expect(p.h).toBe(p.v);
      else expect(p.h).toBeLessThan(p.v);
      expect(p.thinned).toBe(px === 16);
    }
  });
  it("keeps 3 clear channel pixels on every spine row at 16 px", () => {
    expect(channelClear(16).min).toBe(3);
  });
  it.each(FIT_SIZES)("%i px renders to coverage 0 or 1, and exactly 0.5 on the two cut edges only", (px) => {
    const m = mark(px);
    const cov = scanCoverage(m.base + m.accent, px, px);
    const half = [...cov].filter((c) => Math.abs(c - 0.5) < 1e-9).length;
    const other = [...cov].filter((c) => c !== 0 && c !== 1 && Math.abs(c - 0.5) >= 1e-9).length;
    expect(other).toBe(0);
    expect(half).toBe(2 * m.p.h); // each 45 degree edge crosses the spine's h rows, one half pixel per row
  });
});

/** Checks a decoded frame against the fitted mark drawn at (ox, oy): every pixel of the symbol box is exactly the
 * background, the base or the accent colour, except the 2h half pixels on the cut edges. */
function expectFitted(rgba, width, sym, ox, oy, colours, bg) {
  const m = mark(sym);
  const base = scanCoverage(m.base, sym, sym), acc = scanCoverage(m.accent, sym, sym);
  let half = 0;
  for (let y = 0; y < sym; y++) for (let x = 0; x < sym; x++) {
    const i = ((oy + y) * width + ox + x) * 4;
    const px = [rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3]];
    const b = base[y * sym + x], a = acc[y * sym + x];
    if (b === 1) expect(px.slice(0, 3)).toEqual(colours.base);
    else if (a === 1) expect(px.slice(0, 3)).toEqual(colours.accent);
    else if (b === 0 && a === 0) { if (bg) expect(px.slice(0, 3)).toEqual(bg); else expect(px[3]).toBe(0); }
    else half++;
  }
  expect(half).toBe(2 * m.p.h);
}

describe("fitted frames in the generated files", () => {
  const col = (v) => ({ base: rgb(VERSIONS[v].base), accent: rgb(VERSIONS[v].accent) });
  it("tray icons: every normal frame is the fitted symbol, full bleed, on transparent", () => {
    for (const taskbar of Object.keys(TRAY.taskbars)) {
      const frames = decodeIco(file(`assets/tray/tray-normal-${taskbar}.ico`));
      for (const f of frames) expectFitted(f.rgba, f.size, f.size, 0, 0, col(TRAY.taskbars[taskbar]), null);
    }
  });
  it("tray badges sit wholly below the spine, so the cut piece is never clipped", () => {
    for (const px of TRAY.sizes) for (const state of ["paused", "attention"]) {
      const b = badgeGeometry(px, state).box;
      expect(b.y - TRAY.badge[px].gap, `${px} px ${state}`).toBeGreaterThanOrEqual(mark(px).f.y1);
    }
  });
  it("app icon: up to 96 px the symbol is fitted at an approved size on whole pixels", () => {
    const frames = decodeIco(file("assets/app/shelfsync.ico"));
    const plate = rgb(APP_ICON.plate);
    for (const f of frames) {
      const sym = APP_ICON.fittedSymbol[f.size];
      if (!sym) continue;
      expect([...FIT_SIZES, APP_ICON.rimFit]).toContain(sym);
      if (sym === APP_ICON.rimFit) expect(f.size).toBe(16); // the 14 px fit lives only in the 16 px frame
      const off = (f.size - sym) / 2;
      expect(Number.isInteger(off)).toBe(true);
      expectFitted(f.rgba, f.size, sym, off, off, col(APP_ICON.version), plate);
    }
  });
  it("16 px ICO frame: the symbol fitted at 14 px inside a 1 px ink rim (owner, 2026-10-26)", () => {
    expect(APP_ICON.fittedSymbol[16]).toBe(14);
    const [fit] = pixelFit([APP_ICON.rimFit]);
    expect([fit.v, fit.h, fit.spur, fit.upperOpening, fit.lowerOpening]).toEqual([3, 2, 2, 2, 2]);
    expect(fit.whole && fit.slash45 && fit.diagonals === 2).toBe(true);
    const plate = rgb(APP_ICON.plate);
    for (const f of ["assets/app/shelfsync.ico", "assets/favicon/favicon.ico"]) {
      const frame = decodeIco(file(f)).find((x) => x.size === 16);
      for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
        if (x > 0 && x < 15 && y > 0 && y < 15) continue;
        const i = (y * 16 + x) * 4;
        expect([...frame.rgba.subarray(i, i + 4)], `${f} rim ${x},${y}`).toEqual([...plate, 255]);
      }
      expectFitted(frame.rgba, 16, 14, 1, 1, col(APP_ICON.version), plate);
    }
  });
  it("installer art: the symbol is fitted at 32 px in the panel and 16 px in the header", async () => {
    const art = await artCanvases();
    expect(art.panel.placed).toMatchObject({ size: 32, fitted: true, x: INSTALLER.panel.x, y: INSTALLER.panel.y });
    expect(art.header.placed).toMatchObject({ size: 16, fitted: true });
    const panel = decodeBmp(file("assets/installer/installer-panel.bmp"));
    expectFitted(panel.rgba, panel.width, 32, art.panel.placed.x, art.panel.placed.y, col(INSTALLER.panel.version), rgb(INSTALLER.panel.bg));
    const header = decodeBmp(file("assets/installer/installer-header.bmp"));
    expectFitted(header.rgba, header.width, 16, art.header.placed.x, art.header.placed.y, col(INSTALLER.header.version), rgb(INSTALLER.header.bg));
  });
});
