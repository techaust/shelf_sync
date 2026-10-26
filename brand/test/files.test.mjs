// Every 05 1.4 asset exists; each ICO has the right frames, each PNG and BMP the right size and a valid structure;
// every file is under its size limit; generated files match a fresh build (catches hand edits).
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { APP_ICON, FAVICON_ICO_SIZES, GITHUB, INSTALLER, LOCKUPS, STROKE, TRAY, VERSIONS } from "../geometry.mjs";
import { decodeBmp, decodeIco, decodePng } from "../lib/formats.mjs";
import { minimums } from "../lib/lockups.mjs";
import { plan } from "../lib/plan.mjs";
import { REVIEW_DIR, limitFor, review } from "../lib/review.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const read = (f) => readFileSync(join(root, f));
const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]));

const EXPECTED = [
  ...LOCKUPS.flatMap((l) => Object.keys(VERSIONS).map((v) => `assets/logo/logo-${l}-${v}.svg`)),
  "assets/favicon/favicon.svg", "assets/favicon/favicon.ico", "assets/app/shelfsync.ico",
  ...TRAY.states.flatMap((s) => Object.keys(TRAY.taskbars).map((t) => `assets/tray/tray-${s}-${t}.ico`)),
  "assets/installer/installer-panel.bmp", "assets/installer/installer-header.bmp",
  "assets/installer/installer-panel.png", "assets/installer/installer-header.png",
  "assets/github/social-preview.png", "assets/github/readme-header-light.png", "assets/github/readme-header-dark.png",
  "generated/tokens.css", "generated/measurements.json",
];

describe("every 05 1.4 asset exists", () => {
  it("has the 4 lockups x 5 versions, plus the two installer lockups", () => {
    for (const l of ["primary", "symbol", "wordmark", "endorsed"]) for (const v of ["color", "dark", "ink", "white", "black"]) expect(EXPECTED).toContain(`assets/logo/logo-${l}-${v}.svg`);
  });
  it.each(EXPECTED)("%s", (f) => {
    expect(read(f).length).toBeGreaterThan(0);
  });
});

describe("file structure", () => {
  it("ICO frames: tray 16/20/24/32 as 32-bit bitmaps; app 16-256; favicon 16/32/48", () => {
    for (const s of TRAY.states) for (const t of Object.keys(TRAY.taskbars)) {
      const f = decodeIco(read(`assets/tray/tray-${s}-${t}.ico`));
      expect(f.map((x) => x.size)).toEqual(TRAY.sizes);
      for (const x of f) expect([x.kind, x.bpp]).toEqual(["dib", 32]);
    }
    const app = decodeIco(read("assets/app/shelfsync.ico"));
    expect(app.map((x) => x.size)).toEqual(APP_ICON.sizes);
    expect(app.map((x) => x.kind)).toEqual(APP_ICON.sizes.map((px) => (px <= APP_ICON.dibMax ? "dib" : "png")));
    expect(app[0].size).toBe(16);
    expect(app.at(-1).size).toBe(256);
    expect(decodeIco(read("assets/favicon/favicon.ico")).map((x) => x.size)).toEqual(FAVICON_ICO_SIZES);
  });
  it("PNGs are valid (signature, CRCs, IHDR first, IEND last, sRGB) and have the right sizes", () => {
    const sizes = {
      "assets/installer/installer-panel.png": [INSTALLER.panel.width, INSTALLER.panel.height],
      "assets/installer/installer-header.png": [INSTALLER.header.width, INSTALLER.header.height],
      "assets/github/social-preview.png": [1280, 640],
      "assets/github/readme-header-light.png": [GITHUB.readme.width, GITHUB.readme.height],
      "assets/github/readme-header-dark.png": [GITHUB.readme.width, GITHUB.readme.height],
    };
    for (const [f, [w, h]] of Object.entries(sizes)) {
      const p = decodePng(read(f));
      expect([p.width, p.height], f).toEqual([w, h]);
      expect(p.chunks).toContain("sRGB");
    }
    expect(decodePng(read("assets/github/readme-header-light.png")).colourType).toBe(6); // transparent
  });
  it("NSIS bitmaps are 24-bit BMPs of 164 x 314 and 150 x 57", () => {
    expect(decodeBmp(read("assets/installer/installer-panel.bmp"))).toMatchObject({ width: 164, height: 314, bpp: 24 });
    expect(decodeBmp(read("assets/installer/installer-header.bmp"))).toMatchObject({ width: 150, height: 57, bpp: 24 });
  });
  it("SVGs are outlined artwork with a title, a viewBox and no live text", () => {
    for (const f of EXPECTED.filter((x) => x.endsWith(".svg"))) {
      const s = read(f).toString();
      expect(s.startsWith("<svg xmlns=\"http://www.w3.org/2000/svg\"")).toBe(true);
      expect(s).toMatch(/viewBox="[\d. -]+"/);
      expect(s).toContain("<title>");
      expect(s).not.toMatch(/<text|font-family|<image|gradient|filter/);
    }
  });
  it("favicon.svg is drawn on the 16 px grid and switches colours in dark mode", () => {
    const s = read("assets/favicon/favicon.svg").toString();
    expect(s).toContain('viewBox="0 0 16 16"');
    expect(s).toContain("@media (prefers-color-scheme:dark)");
    for (const d of s.match(/ d="([^"]+)"/g)) for (const n of d.match(/-?\d*\.?\d+/g)) expect(Number.isInteger(Number(n))).toBe(true);
  });
  it.each(EXPECTED.filter((f) => limitFor(f)))("%s is under its size limit", (f) => {
    expect(read(f).length).toBeLessThanOrEqual(limitFor(f));
  });
});

describe("installer lockups", () => {
  it("keep the caption at 12 px and fit their panels with one stroke of clear space", async () => {
    const m = await minimums();
    expect(m.stacked.captionPx).toBeGreaterThanOrEqual(12);
    expect(m.compact.captionPx).toBeGreaterThanOrEqual(12);
    const strokePx = (u) => STROKE * u; // one symbol stroke
    expect(INSTALLER.panel.x).toBeGreaterThanOrEqual(STROKE * (m.stacked.symbolPx / 100));
    expect(INSTALLER.panel.x + m.stacked.width + STROKE * (m.stacked.symbolPx / 100)).toBeLessThanOrEqual(INSTALLER.panel.width);
    expect(m.compact.width + 2 * strokePx(16 / 100)).toBeLessThanOrEqual(INSTALLER.header.width);
    expect(m.compact.height + 2 * strokePx(16 / 100)).toBeLessThanOrEqual(INSTALLER.header.height);
    expect(m.compact.width).toBeGreaterThanOrEqual(118.6); // the primary at its 119 px minimum (symbol 16 px)
  });
});

/**
 * Compares a file on disk with the build's output. PNG streams are zlib, whose bytes may differ between Node /
 * zlib versions while the image is the same, so a PNG (and a PNG frame inside an ICO) is compared by its decoded
 * pixels, size, colour type and chunk order. Everything without zlib is compared byte for byte: SVG, CSS, JSON,
 * HTML, BMP, fonts, each ICO directory entry's first 8 bytes (size, colours, planes, bpp), and each 32-bit DIB frame
 * whole (header, BGRA pixels and the AND mask).
 */
function same(disk, built, f) {
  const b = Buffer.from(built);
  if (f.endsWith(".png")) {
    const x = decodePng(disk), y = decodePng(b);
    return x.width === y.width && x.height === y.height && x.colourType === y.colourType && x.chunks.join() === y.chunks.join() && Buffer.from(x.rgba).equals(Buffer.from(y.rgba));
  }
  if (f.endsWith(".ico")) {
    const x = decodeIco(disk), y = decodeIco(b);
    if (!disk.subarray(0, 6).equals(b.subarray(0, 6)) || x.length !== y.length) return false;
    return x.every((fr, i) => fr.kind === y[i].kind && fr.entry.equals(y[i].entry) &&
      (fr.kind === "dib" ? fr.data.equals(y[i].data) : Buffer.from(fr.rgba).equals(Buffer.from(y[i].rgba))));
  }
  return disk.equals(b);
}

describe("generated files match a fresh build", () => {
  let p, r;
  beforeAll(async () => { p = await plan(); r = await review(p); });
  it("every file in brand/ matches the build's output (rasters by pixels, the rest byte for byte)", () => {
    for (const [f, body] of Object.entries(p.files)) expect(same(read(f), body, f), f).toBe(true);
  });
  it("brand/assets and brand/generated hold nothing the build doesn't make", () => {
    const onDisk = [...walk(join(root, "assets")), ...walk(join(root, "generated"))].map((f) => relative(root, f).split("\\").join("/")).sort();
    expect(onDisk).toEqual(Object.keys(p.files).sort());
  });
  it("the review page and its copies match the build's output", () => {
    for (const [f, body] of Object.entries(r)) expect(same(readFileSync(join(REVIEW_DIR, f)), body, f), f).toBe(true);
  });
});
