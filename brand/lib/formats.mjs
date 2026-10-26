// PNG, ICO and BMP writers and readers, on Node's built-in zlib only (no sharp). Deterministic: the same pixels give
// the same bytes on the same Node / zlib, which the drift test relies on.
import { crc32, deflateSync, inflateSync } from "node:zlib";

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function chunk(type, data) {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, "latin1");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])) >>> 0, 0);
  return Buffer.concat([head, data, crc]);
}

const paeth = (a, b, c) => {
  const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
};

/**
 * Straight 8-bit RGBA -> PNG. Fully opaque images are written as RGB (colour type 2), others as RGBA (6); every
 * file is tagged sRGB. Each row takes the filter with the smallest sum of absolute values (the usual heuristic).
 */
export function encodePng(w, h, rgba) {
  let opaque = true;
  for (let i = 3; i < rgba.length; i += 4) if (rgba[i] !== 255) { opaque = false; break; }
  const bpp = opaque ? 3 : 4;
  const stride = w * bpp;
  const raw = Buffer.alloc(stride * h);
  for (let i = 0, o = 0; i < w * h; i++) {
    raw[o++] = rgba[i * 4];
    raw[o++] = rgba[i * 4 + 1];
    raw[o++] = rgba[i * 4 + 2];
    if (!opaque) raw[o++] = rgba[i * 4 + 3];
  }
  const out = Buffer.alloc((stride + 1) * h);
  const cand = Array.from({ length: 5 }, () => Buffer.alloc(stride));
  for (let y = 0; y < h; y++) {
    const cur = raw.subarray(y * stride, (y + 1) * stride);
    const prev = y ? raw.subarray((y - 1) * stride, y * stride) : Buffer.alloc(stride);
    let best = 0, bestSum = Infinity;
    for (let f = 0; f < 5; f++) {
      const c = cand[f];
      let sum = 0;
      for (let x = 0; x < stride; x++) {
        const a = x >= bpp ? cur[x - bpp] : 0, b = prev[x], cc = x >= bpp ? prev[x - bpp] : 0;
        const pred = f === 0 ? 0 : f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : paeth(a, b, cc);
        const v = (cur[x] - pred) & 255;
        c[x] = v;
        sum += v < 128 ? v : 256 - v;
      }
      if (sum < bestSum) { bestSum = sum; best = f; }
    }
    out[y * (stride + 1)] = best;
    cand[best].copy(out, y * (stride + 1) + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr.writeUInt8(8, 8);
  ihdr.writeUInt8(opaque ? 2 : 6, 9);
  return Buffer.concat([
    SIGNATURE, chunk("IHDR", ihdr), chunk("sRGB", Buffer.from([0])),
    chunk("IDAT", deflateSync(out, { level: 9, memLevel: 9 })), chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** PNG -> { width, height, colourType, chunks, rgba }, checking the signature and every CRC. 8-bit RGB/RGBA only. */
export function decodePng(buf) {
  if (!buf.subarray(0, 8).equals(SIGNATURE)) throw new Error("not a PNG (bad signature)");
  const chunks = [];
  const idat = [];
  let o = 8;
  while (o < buf.length) {
    const len = buf.readUInt32BE(o);
    const type = buf.toString("latin1", o + 4, o + 8);
    const data = buf.subarray(o + 8, o + 8 + len);
    const crc = buf.readUInt32BE(o + 8 + len);
    if ((crc32(buf.subarray(o + 4, o + 8 + len)) >>> 0) !== crc) throw new Error(`PNG chunk ${type}: bad CRC`);
    chunks.push(type);
    if (type === "IDAT") idat.push(data);
    o += 12 + len;
    if (type === "IEND") break;
  }
  if (chunks[0] !== "IHDR" || chunks.at(-1) !== "IEND") throw new Error("PNG: IHDR must come first and IEND last");
  const ihdr = buf.subarray(16, 29);
  const width = ihdr.readUInt32BE(0), height = ihdr.readUInt32BE(4), depth = ihdr[8], colourType = ihdr[9];
  if (depth !== 8 || (colourType !== 2 && colourType !== 6)) throw new Error("PNG: only 8-bit RGB / RGBA are read here");
  const bpp = colourType === 6 ? 4 : 3;
  const stride = width * bpp;
  const raw = inflateSync(Buffer.concat(idat));
  if (raw.length !== (stride + 1) * height) throw new Error("PNG: image data has the wrong length");
  const px = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const f = raw[y * (stride + 1)];
    for (let x = 0; x < stride; x++) {
      const v = raw[y * (stride + 1) + 1 + x];
      const a = x >= bpp ? px[y * stride + x - bpp] : 0, b = y ? px[(y - 1) * stride + x] : 0, c = x >= bpp && y ? px[(y - 1) * stride + x - bpp] : 0;
      const pred = f === 0 ? 0 : f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : f === 4 ? paeth(a, b, c) : NaN;
      if (Number.isNaN(pred)) throw new Error(`PNG: unknown filter ${f}`);
      px[y * stride + x] = (v + pred) & 255;
    }
  }
  const rgba = new Uint8Array(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    rgba.set(px.subarray(i * bpp, i * bpp + 3), i * 4);
    rgba[i * 4 + 3] = bpp === 4 ? px[i * bpp + 3] : 255;
  }
  return { width, height, colourType, chunks, rgba };
}

/** A 32-bit DIB icon frame: BITMAPINFOHEADER (height doubled), BGRA rows bottom-up, then the 1-bit AND mask. */
function dibFrame(size, rgba) {
  const maskStride = Math.ceil(size / 32) * 4;
  const head = Buffer.alloc(40);
  head.writeUInt32LE(40, 0);
  head.writeInt32LE(size, 4);
  head.writeInt32LE(size * 2, 8);
  head.writeUInt16LE(1, 12);
  head.writeUInt16LE(32, 14);
  head.writeUInt32LE(0, 16);
  head.writeUInt32LE(size * size * 4 + maskStride * size, 20);
  const xor = Buffer.alloc(size * size * 4);
  const and = Buffer.alloc(maskStride * size);
  for (let y = 0; y < size; y++) {
    const src = size - 1 - y;
    for (let x = 0; x < size; x++) {
      const i = (src * size + x) * 4, o = (y * size + x) * 4;
      xor[o] = rgba[i + 2]; xor[o + 1] = rgba[i + 1]; xor[o + 2] = rgba[i]; xor[o + 3] = rgba[i + 3];
      if (rgba[i + 3] === 0) and[y * maskStride + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  return Buffer.concat([head, xor, and]);
}

/** Frames [{ size, rgba }] -> ICO. Frames up to `dibMax` px are 32-bit DIBs, larger ones PNG (Vista and later). */
export function encodeIco(frames, { dibMax = 48 } = {}) {
  const images = frames.map((f) => ({ size: f.size, data: f.size <= dibMax ? dibFrame(f.size, f.rgba) : encodePng(f.size, f.size, f.rgba) }));
  const header = Buffer.alloc(6 + 16 * images.length);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = header.length;
  images.forEach((img, i) => {
    const e = 6 + 16 * i;
    header.writeUInt8(img.size >= 256 ? 0 : img.size, e);
    header.writeUInt8(img.size >= 256 ? 0 : img.size, e + 1);
    header.writeUInt16LE(1, e + 4);
    header.writeUInt16LE(32, e + 6);
    header.writeUInt32LE(img.data.length, e + 8);
    header.writeUInt32LE(offset, e + 12);
    offset += img.data.length;
  });
  return Buffer.concat([header, ...images.map((i) => i.data)]);
}

/** ICO -> [{ size, kind: "dib" | "png", bpp, bytes, entry (first 8 directory bytes), data (raw frame), rgba }], checking the directory against the data. */
export function decodeIco(buf) {
  if (buf.readUInt16LE(0) !== 0 || buf.readUInt16LE(2) !== 1) throw new Error("not an icon file");
  const n = buf.readUInt16LE(4);
  const out = [];
  for (let i = 0; i < n; i++) {
    const e = 6 + 16 * i;
    const size = buf[e] || 256;
    if ((buf[e + 1] || 256) !== size) throw new Error("ICO: frame is not square");
    const len = buf.readUInt32LE(e + 8), off = buf.readUInt32LE(e + 12);
    if (off + len > buf.length) throw new Error("ICO: frame runs past the end of the file");
    const data = buf.subarray(off, off + len);
    if (data.subarray(0, 8).equals(SIGNATURE)) {
      const png = decodePng(data);
      if (png.width !== size || png.height !== size) throw new Error(`ICO: PNG frame is ${png.width} x ${png.height}, directory says ${size}`);
      out.push({ size, kind: "png", bpp: buf.readUInt16LE(e + 6), bytes: len, entry: buf.subarray(e, e + 8), data, rgba: png.rgba });
      continue;
    }
    const w = data.readInt32LE(4), h = data.readInt32LE(8), bpp = data.readUInt16LE(14);
    if (data.readUInt32LE(0) !== 40 || w !== size || h !== size * 2 || bpp !== 32) throw new Error(`ICO: DIB frame header does not match ${size} px, 32-bit`);
    const maskStride = Math.ceil(size / 32) * 4;
    if (len !== 40 + size * size * 4 + maskStride * size) throw new Error("ICO: DIB frame has the wrong length");
    const rgba = new Uint8Array(size * size * 4);
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      const s = 40 + ((size - 1 - y) * size + x) * 4, o = (y * size + x) * 4;
      rgba[o] = data[s + 2]; rgba[o + 1] = data[s + 1]; rgba[o + 2] = data[s]; rgba[o + 3] = data[s + 3];
    }
    out.push({ size, kind: "dib", bpp, bytes: len, entry: buf.subarray(e, e + 8), data, rgba });
  }
  return out;
}

/** Opaque 8-bit RGBA -> 24-bit Windows BMP (BITMAPINFOHEADER, bottom-up), as NSIS Modern UI images take. */
export function encodeBmp(w, h, rgba) {
  const stride = Math.ceil((w * 3) / 4) * 4;
  const size = 54 + stride * h;
  const b = Buffer.alloc(size);
  b.write("BM", 0, "latin1");
  b.writeUInt32LE(size, 2);
  b.writeUInt32LE(54, 10);
  b.writeUInt32LE(40, 14);
  b.writeInt32LE(w, 18);
  b.writeInt32LE(h, 22);
  b.writeUInt16LE(1, 26);
  b.writeUInt16LE(24, 28);
  b.writeUInt32LE(stride * h, 34);
  b.writeInt32LE(2835, 38); // 72 dpi
  b.writeInt32LE(2835, 42);
  for (let y = 0; y < h; y++) {
    const src = h - 1 - y;
    for (let x = 0; x < w; x++) {
      const i = (src * w + x) * 4;
      if (rgba[i + 3] !== 255) throw new Error("BMP: the image must be opaque");
      const o = 54 + y * stride + x * 3;
      b[o] = rgba[i + 2]; b[o + 1] = rgba[i + 1]; b[o + 2] = rgba[i];
    }
  }
  return b;
}

/** 24-bit BMP -> { width, height, bpp, rgba }. */
export function decodeBmp(b) {
  if (b.toString("latin1", 0, 2) !== "BM" || b.readUInt32LE(2) !== b.length) throw new Error("not a BMP (or the size field is wrong)");
  const w = b.readInt32LE(18), h = b.readInt32LE(22), bpp = b.readUInt16LE(28), off = b.readUInt32LE(10);
  if (bpp !== 24 || b.readUInt32LE(30) !== 0) throw new Error("BMP: expected 24-bit, uncompressed");
  const stride = Math.ceil((w * 3) / 4) * 4;
  if (off + stride * h !== b.length) throw new Error("BMP: pixel data has the wrong length");
  const rgba = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const s = off + (h - 1 - y) * stride + x * 3, o = (y * w + x) * 4;
    rgba[o] = b[s + 2]; rgba[o + 1] = b[s + 1]; rgba[o + 2] = b[s]; rgba[o + 3] = 255;
  }
  return { width: w, height: h, bpp, rgba };
}
