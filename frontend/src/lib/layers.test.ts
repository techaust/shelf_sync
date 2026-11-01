// CLAUDE.md "Screen code layers": api/ → lib/ → components/ → app/ and screens/. Nothing in api/, lib/ or
// components/ (tests included) may import from screens/, directly or through another folder such as theme/ or app/,
// so a lower layer never pulls a screen into its code. The import graph is read from the sources as text (Vite's
// ?raw, as chunkBoundary.test.ts reads the components), so no parser package is needed.
import { describe, expect, it } from "vitest";

const raw = import.meta.glob("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

/** The glob names files from lib/ ("./time.ts", "../app/boot.ts"); the graph names them from src/ ("app/boot.ts"). */
const resolveFrom = (dir: string, specifier: string) =>
  new URL(specifier, `file:///src/${dir}`).pathname.slice("/src/".length);
const sources = new Map(Object.entries(raw).map(([key, text]) => [resolveFrom("lib/", key), text]));

const SPECIFIERS = [
  /^\s*(?:import|export)\b[^;]*?\bfrom\s*["']([^"']+)["']/gm, // import … from "…", export … from "…"
  /^\s*import\s*["']([^"']+)["']/gm, // import "…" (side effect)
  /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g, // import("…")
];
// ".d.ts": the API's types come from "./schema" (schema.d.ts).
const CODE_SUFFIXES = ["", ".ts", ".tsx", ".d.ts", "/index.ts", "/index.tsx"];

interface Imports {
  edges: string[];
  unresolved: string[];
}

function importsOf(file: string, text: string): Imports {
  const dir = file.slice(0, file.lastIndexOf("/") + 1);
  const found: Imports = { edges: [], unresolved: [] };
  for (const pattern of SPECIFIERS) {
    for (const [, specifier = ""] of text.matchAll(pattern)) {
      // Packages aren't layers; a "?raw" import reads a file as text, and a CSS, SVG or JSON file holds no imports.
      if (!specifier.startsWith(".") || specifier.includes("?") || /\.(?!tsx?$)\w+$/.test(specifier)) continue;
      const base = resolveFrom(dir, specifier);
      const target = CODE_SUFFIXES.map((suffix) => base + suffix).find((path) => sources.has(path));
      if (target) found.edges.push(target);
      else found.unresolved.push(`${file}: "${specifier}"`);
    }
  }
  return found;
}

const graph = new Map([...sources].map(([file, text]) => [file, importsOf(file, text)]));
const LOWER = /^(api|lib|components)\//;
const SCREENS = /^screens\//;

/** The first path from `start` into screens/, as "a → b → screens/…", or null when there is none. */
function pathToScreens(start: string): string | null {
  const cameFrom = new Map<string, string | null>([[start, null]]);
  const queue = [start];
  for (let file = queue.shift(); file !== undefined; file = queue.shift()) {
    if (SCREENS.test(file)) {
      const chain = [file];
      for (let step = cameFrom.get(file); step; step = cameFrom.get(step)) chain.unshift(step);
      return chain.join(" → ");
    }
    for (const next of graph.get(file)?.edges ?? []) {
      if (!cameFrom.has(next)) {
        cameFrom.set(next, file);
        queue.push(next);
      }
    }
  }
  return null;
}

describe("the import graph", () => {
  it("finds static, re-exported and dynamic imports, and every relative import resolves", () => {
    // If the extractor found nothing, the layer checks below would pass on any tree.
    expect(graph.get("main.tsx")?.edges).toContain("lib/switchStore.ts");
    expect(graph.get("screens/settings/Settings.tsx")?.edges).toContain("screens/settings/UpdatesPage.tsx");
    expect(graph.get("components/help/HelpPanel.tsx")?.edges).toContain("components/help/guides.tsx");
    expect(graph.get("api/settings.ts")?.edges).toContain("api/schema.d.ts");
    expect([...graph.values()].flatMap((imports) => imports.unresolved)).toEqual([]);
  });
});

describe("screen code layers (CLAUDE.md)", () => {
  const lower = [...graph.keys()].filter((file) => LOWER.test(file)).sort();

  it("reads every file of api/, lib/ and components/", () => {
    expect(lower).toContain("api/client.ts");
    expect(lower).toContain("lib/restartPoll.test.ts"); // tests too (the glob leaves out only this file)
    expect(lower).toContain("components/ThemeMenu.tsx");
  });

  it("no file in api/, lib/ or components/ imports from screens/", () => {
    const direct = lower.flatMap((file) =>
      (graph.get(file)?.edges ?? []).filter((target) => SCREENS.test(target)).map((target) => `${file} → ${target}`),
    );
    expect(direct).toEqual([]);
  });

  it("nor through another module", () => {
    const paths = lower.map(pathToScreens).filter((path) => path !== null);
    expect(paths).toEqual([]);
  });
});
