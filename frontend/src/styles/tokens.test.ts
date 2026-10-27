// "Tokens only, never a hand-typed colour" (05; CLAUDE.md conventions) and "one source of truth": the UI's copy
// of the brand tokens is byte for byte brand/generated/tokens.css, and no source file outside the generated
// folder types a colour. NFR-1: nothing is loaded from another host.
import { describe, expect, it } from "vitest";
import brandTokens from "../../../brand/generated/tokens.css?raw";
import uiTokens from "./generated/tokens.css?raw";

// storePalette.ts is the one hand-typed-colour file: store identifier colours are store data keyed by the backend's
// palette (05 section 2.3), never styling, and contrast.test.ts checks every pair on every surface.
const sources = import.meta.glob(
  ["../**/*.{ts,tsx,css}", "!../**/*.test.ts", "!./generated/**", "!../api/schema.d.ts", "!./storePalette.ts"],
  {
    query: "?raw",
    import: "default",
    eager: true,
  },
) as Record<string, string>;
const html = import.meta.glob("../../index.html", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

describe("tokens", () => {
  it("src/styles/generated/tokens.css is brand/generated/tokens.css, unchanged", () => {
    // Not empty: Vitest empties CSS imports unless vitest.config.ts lets "?raw" ones through, which would make
    // this comparison (and the colour checks below) pass on nothing.
    expect(uiTokens.length).toBeGreaterThan(1000);
    expect(uiTokens).toContain("--color-bg:");
    expect(uiTokens).toBe(brandTokens);
  });

  it("the source files were found", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10);
  });

  const COLOUR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\bhwb\(/;
  it.each(Object.entries(sources))("%s types no colour", (_path, text) => {
    const lines = text.split("\n").filter((line) => COLOUR.test(line));
    expect(lines).toEqual([]);
  });
});

describe("NFR-1 and the CSP", () => {
  const all = { ...sources, ...html };
  it.each(Object.entries(all))("%s loads nothing from another host", (_path, text) => {
    expect(text).not.toMatch(/(?:src|href|url)\s*[=(]\s*["']?(?:https?:)?\/\//i);
    expect(text).not.toMatch(/@import\s+["']?(?:https?:)?\/\//i);
  });

  it("index.html has no inline script or style", () => {
    const page = Object.values(html)[0] ?? "";
    expect(page).toMatch(/<script type="module" src="\/src\/main.tsx"><\/script>/);
    expect(page.match(/<script\b/g)).toHaveLength(1);
    expect(page).not.toMatch(/<style\b/i);
    expect(page).not.toMatch(/\sstyle=/i);
    expect(page).not.toMatch(/\son[a-z]+=/i);
  });
});
