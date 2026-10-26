// The raster writers and the renderer on small known shapes.
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { decodeBmp, decodeIco, decodePng, encodeBmp, encodeIco, encodePng } from "../lib/formats.mjs";
import { Canvas, rectPath, scanCoverage } from "../lib/render.mjs";

describe("renderer", () => {
  it("gives exact coverage: 1 inside whole-pixel edges, 0.5 on a corner-to-corner 45 degree edge", () => {
    const cov = scanCoverage("M0 0H4L0 4Z", 4, 4); // right triangle, hypotenuse from (4,0) to (0,4)
    const row = (y) => [...cov.slice(y * 4, y * 4 + 4)];
    expect(row(0)).toEqual([1, 1, 1, 0.5]);
    expect(row(3)).toEqual([0.5, 0, 0, 0]);
    expect(cov.reduce((s, v) => s + v, 0)).toBeCloseTo(8, 9);
  });
  it("leaves no seam where two colours of one layer meet", () => {
    const c = new Canvas(4, 1).draw([{ d: rectPath(0, 0, 2.5, 1), color: [255, 0, 0] }, { d: rectPath(2.5, 0, 1.5, 1), color: [0, 0, 255] }]);
    const px = c.pixels();
    expect(px[2 * 4 + 3]).toBe(255); // the shared pixel is fully opaque
  });
});

describe("formats", () => {
  const c = new Canvas(5, 3).draw([{ d: rectPath(1, 1, 3, 1), color: [20, 35, 31] }]);
  it("PNG round-trips with alpha", () => {
    const p = decodePng(encodePng(5, 3, c.pixels()));
    expect([p.width, p.height, p.colourType]).toEqual([5, 3, 6]);
    expect([...p.rgba]).toEqual([...c.pixels()]);
  });
  it("PNG rejects a broken CRC", () => {
    const b = Buffer.from(encodePng(5, 3, c.pixels()));
    b[b.length - 20] ^= 0xff;
    expect(() => decodePng(b)).toThrow(/CRC|length|PNG/);
  });
  it("ICO round-trips DIB and PNG frames", () => {
    const f8 = new Canvas(8, 8).draw([{ d: rectPath(2, 2, 4, 4), color: [30, 107, 92] }]);
    const f64 = new Canvas(64, 64).draw([{ d: rectPath(0, 0, 32, 64), color: [30, 107, 92] }]);
    const ico = decodeIco(encodeIco([{ size: 8, rgba: f8.pixels() }, { size: 64, rgba: f64.pixels() }], { dibMax: 48 }));
    expect(ico.map((x) => [x.size, x.kind])).toEqual([[8, "dib"], [64, "png"]]);
    expect([...ico[0].rgba]).toEqual([...f8.pixels()]);
    expect([...ico[1].rgba]).toEqual([...f64.pixels()]);
  });
  it("BMP round-trips and refuses transparency", () => {
    const o = new Canvas(5, 3).fill([255, 255, 255]).draw([{ d: rectPath(1, 1, 3, 1), color: [20, 35, 31] }]);
    expect([...decodeBmp(encodeBmp(5, 3, o.pixels())).rgba]).toEqual([...o.pixels()]);
    expect(() => encodeBmp(5, 3, c.pixels())).toThrow(/opaque/);
  });
  it("is deterministic", () => {
    expect(encodePng(5, 3, c.pixels()).equals(encodePng(5, 3, c.pixels()))).toBe(true);
  });
});

// Known answers, independent of our own decoders: the bytes the formats' specifications require.
describe("known-answer bytes", () => {
  const hex = (b) => Buffer.from(b).toString("hex");
  it("PNG, 1 x 1 transparent pixel: signature, IHDR with its CRC, sRGB, IEND, and the raw scanline", () => {
    const b = encodePng(1, 1, new Uint8Array([1, 2, 3, 4]));
    expect(hex(b.subarray(0, 8))).toBe("89504e470d0a1a0a");
    // length 13, "IHDR", width 1, height 1, depth 8, colour type 6 (RGBA), compression 0, filter 0, interlace 0, CRC
    expect(hex(b.subarray(8, 33))).toBe("0000000d" + "49484452" + "00000001" + "00000001" + "0806000000" + "1f15c489");
    expect(hex(b.subarray(33, 46))).toBe("00000001" + "73524742" + "00" + "aece1ce9"); // sRGB, perceptual, with its CRC
    expect(hex(b.subarray(b.length - 12))).toBe("0000000049454e44ae426082");
    const len = b.readUInt32BE(46);
    expect(b.toString("latin1", 50, 54)).toBe("IDAT");
    // one scanline: filter byte, then R G B A (any filter type gives back these bytes for a single pixel)
    const raw = inflateSync(b.subarray(54, 54 + len));
    expect(raw.length).toBe(5);
    expect([...raw.subarray(1)]).toEqual([1, 2, 3, 4]);
    expect([0, 1, 2, 3, 4]).toContain(raw[0]);
  });
  it("BMP, 1 x 2: file header, info header, rows bottom-up, pixels as B G R, rows padded to 4 bytes", () => {
    const top = [255, 0, 0, 255], bottom = [0, 0, 255, 255]; // red above blue
    const b = encodeBmp(1, 2, new Uint8Array([...top, ...bottom]));
    expect(b.length).toBe(54 + 2 * 4);
    expect(hex(b.subarray(0, 14))).toBe("424d" + "3e000000" + "00000000" + "36000000");
    expect(hex(b.subarray(14, 30))).toBe("28000000" + "01000000" + "02000000" + "0100" + "1800");
    expect(hex(b.subarray(54, 58))).toBe("ff000000"); // first stored row is the bottom one: blue as B, G, R, then padding
    expect(hex(b.subarray(58, 62))).toBe("0000ff00"); // then the top row: red as B, G, R
  });
  it("ICO, one 2 x 2 frame: directory entry and DIB header, BGRA bottom-up, AND mask set where transparent", () => {
    const px = new Uint8Array([10, 20, 30, 255, 0, 0, 0, 0, /* row 2 */ 40, 50, 60, 255, 70, 80, 90, 128]);
    const b = encodeIco([{ size: 2, rgba: px }], { dibMax: 48 });
    expect(hex(b.subarray(0, 6))).toBe("000001000100"); // reserved, type 1 (icon), 1 image
    // width 2, height 2, 0 colours, reserved, 1 plane, 32 bpp, 64 bytes of data at offset 22
    expect(hex(b.subarray(6, 22))).toBe("0202" + "0000" + "0100" + "2000" + "40000000" + "16000000");
    const d = b.subarray(22);
    expect(hex(d.subarray(0, 24))).toBe("28000000" + "02000000" + "04000000" + "0100" + "2000" + "00000000" + "18000000");
    expect(hex(d.subarray(40, 56))).toBe("3c3228ff" + "5a504680" + "1e140aff" + "00000000"); // bottom row first, B G R A
    expect(hex(d.subarray(56, 64))).toBe("00000000" + "40000000"); // mask rows bottom-up: only the top row's 2nd pixel is transparent
  });
});
