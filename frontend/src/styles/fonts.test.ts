// NFR-1 and 05 section 3: the bundled faces cover Latin and Latin Extended for every face the UI uses, so a product
// or file name with an accented letter (ě, ł, ő) never falls back to another font in a slug or a heading.
import { describe, expect, it } from "vitest";
import fonts from "./fonts.css?raw";

const faces = [...fonts.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((match) => match[1] ?? "");
const field = (face: string, name: string) => new RegExp(`${name}:\\s*([^;]+);`).exec(face)?.[1]?.trim() ?? "";

describe("bundled fonts", () => {
  it.each([
    ['"Archivo"', "100 900"],
    ['"IBM Plex Mono"', "400"],
    ['"IBM Plex Mono"', "500"],
  ])("%s %s ships both the Latin and the Latin Extended subset", (family, weight) => {
    const urls = faces
      .filter((face) => field(face, "font-family") === family && field(face, "font-weight") === weight)
      .map((face) => field(face, "src"));
    expect(urls.some((url) => /-latin-(?!ext)/.test(url))).toBe(true);
    expect(urls.some((url) => /-latin-ext-/.test(url))).toBe(true);
  });

  it("every face is a bundled woff2 file from a pinned @fontsource package, with a unicode range", () => {
    expect(faces.length).toBe(6);
    for (const face of faces) {
      expect(field(face, "src")).toMatch(/^url\("@fontsource(-variable)?\/[a-z-]+\/files\/[a-z0-9-]+\.woff2"\)/);
      expect(field(face, "unicode-range")).not.toBe("");
    }
  });
});
