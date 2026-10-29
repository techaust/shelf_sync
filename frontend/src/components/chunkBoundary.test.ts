// m2.5b round 1: a lazily loaded part whose code can't be fetched (a tab left open across an update) shows one line
// with Reload, and the rest of the app stays. The unit tests run in Node with no DOM, and React's server renderer
// doesn't run error boundaries, so the boundary is driven the way React drives it: a failed import rejects, React
// asks getDerivedStateFromError for the new state, and render() then draws the panel. The whole path was also
// checked in the built-in browser pane against a dist copy with a chunk deleted (run file section 3, round 1).
import { createElement as h, lazy } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RouteError } from "../app/RouteError";
import { CHUNK_FAILED, ChunkBoundary, ChunkFailed } from "./ChunkBoundary";

const decode = (html: string) => html.replaceAll("&#x27;", "'");
/** What the browser does with an import() whose chunk is gone from the server. */
const failingImport = () =>
  Promise.reject(new TypeError("Failed to fetch dynamically imported module: http://127.0.0.1:47615/assets/X.js"));

describe("ChunkBoundary", () => {
  it("a lazy part whose import fails rejects with the browser's error", async () => {
    const load = vi.fn(failingImport);
    lazy(load); // React calls the loader only when it renders the part
    await expect(load()).rejects.toThrow("Failed to fetch dynamically imported module");
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
});
