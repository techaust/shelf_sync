// m2.5b round 1: a lazily loaded part whose code can't be fetched (a tab left open across an update) shows one line
// with Reload, and the rest of the app stays. The unit tests run in Node with no DOM, and React's server renderer
// doesn't run error boundaries, so the boundary is driven the way React drives it: a failed import rejects, React
// asks getDerivedStateFromError for the new state, and render() then draws the panel. The whole path was also
// checked in the built-in browser pane against a dist copy with a chunk deleted (run file section 3, round 1).
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RouteError } from "../app/RouteError";
import { CHUNK_FAILED, ChunkBoundary, ChunkFailed } from "./ChunkBoundary";

const decode = (html: string) => html.replaceAll("&#x27;", "'");
/** Every component file's source, to check where Suspense is used (Vite's ?raw, as tokens.test.ts reads the CSS). */
const sources = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

describe("ChunkBoundary", () => {
  it("every Suspense in the app sits directly inside a ChunkBoundary (Settings' pages, the Help guides)", () => {
    const withSuspense = Object.entries(sources).filter(([, text]) => text.includes("<Suspense"));
    // the two lazy parts of m2.5b; a new one must be added here, and wrapped
    expect(withSuspense.map(([file]) => file).sort()).toEqual([
      "../screens/settings/Settings.tsx",
      "./help/HelpPanel.tsx",
    ]);
    for (const [file, text] of withSuspense) {
      const suspense = text.match(/<Suspense\b/g)?.length ?? 0;
      const wrapped = text.match(/<ChunkBoundary\b[^>]*>\s*<Suspense\b/g)?.length ?? 0;
      expect(wrapped, file).toBe(suspense);
      expect(text, file).toMatch(/<\/Suspense>\s*<\/ChunkBoundary>/);
    }
  });

  it("an error in the part turns the boundary to its failed state", () => {
    expect(ChunkBoundary.getDerivedStateFromError()).toEqual({ failed: true });
  });

  it("before a failure it draws its children; after it, one line and Reload, never the error's text", () => {
    const boundary = new ChunkBoundary({ children: h("p", null, "sample page body"), reload: vi.fn() });
    expect(renderToStaticMarkup(h("div", null, boundary.render()))).toBe("<div><p>sample page body</p></div>");
    boundary.state = ChunkBoundary.getDerivedStateFromError();
    const html = decode(renderToStaticMarkup(h("div", null, boundary.render())));
    expect(html).toContain(CHUNK_FAILED.title);
    expect(html).toContain(CHUNK_FAILED.text);
    expect(html).toContain(">Reload page</button>");
    expect(html).not.toContain("Failed to fetch");
    expect(html).not.toContain("sample page body");
  });

  it("Reload reloads the page", () => {
    const reload = vi.fn();
    const element = ChunkFailed({ onReload: reload });
    // the action button's onClick, found in the element tree
    const find = (node: unknown): ((...args: unknown[]) => void) | null => {
      if (!node || typeof node !== "object") return null;
      const props = (node as { props?: Record<string, unknown> }).props ?? {};
      if (typeof props.onClick === "function") return props.onClick as () => void;
      for (const value of Object.values(props)) {
        for (const child of Array.isArray(value) ? value : [value]) {
          const found = find(child);
          if (found) return found;
        }
      }
      return null;
    };
    find(element)?.();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("13 wording (proposed)", () => {
    expect(CHUNK_FAILED).toEqual({
      title: "This part of ShelfSync couldn't be loaded.",
      text: "ShelfSync may have been updated since this tab was opened. Reload the page to get the current version.",
      reload: "Reload page",
      screenTitle: "This screen couldn't be shown",
    });
  });
});

describe("the routes' last guard", () => {
  it("inside the shell: the screen shows the line; bare: the same line in the sign-in panel's place", () => {
    for (const bare of [false, true]) {
      const html = decode(renderToStaticMarkup(h(RouteError, { bare })));
      expect(html).toContain(CHUNK_FAILED.title);
      expect(html).toContain(bare ? 'class="gate"' : 'class="page"');
    }
  });

  it("inside the shell it has a focusable h1, so the shell's move-focus-to-the-title lands on it", () => {
    const html = decode(renderToStaticMarkup(h(RouteError)));
    expect(html).toContain(`<h1 class="page-title" tabindex="-1" data-nav-focus="">${CHUNK_FAILED.screenTitle}</h1>`);
  });
});
