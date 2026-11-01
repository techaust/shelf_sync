// UI-SHELL, SET-06, NFR-2 (T5): the component rules written once with the tokens in component-tokens.css give the
// colours the paired dark rules gave before, in every theme context, without a browser. The rules are read from the
// stylesheets as text and resolved by a small var() resolver; the expected colours come from an independent table of
// the old behaviour (docs/runs/t5-dark-tokens.md section 1), turned into hex from brand/tokens.json.
import { describe, expect, it } from "vitest";
import tokens from "../../../brand/tokens.json";
import storeBadge from "../components/StoreBadge.tsx?raw";
import componentTokensCss from "./component-tokens.css?raw";
import shelfsyncTokensCss from "./generated/shelfsync-tokens.css?raw";
import tokensCss from "./generated/tokens.css?raw";
import { STORE_PALETTE } from "./storePalette";

// ---------- a small CSS reader: style rules with their @media conditions (@layer is transparent here) ----------

interface Rule {
  selectors: string[];
  media: string[];
  decls: [string, string][];
}

function closing(text: string, open: number, pair: "{}" | "()"): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === pair[0]) depth++;
    else if (text[i] === pair[1] && --depth === 0) return i;
  }
  throw new Error(`unbalanced ${pair} from ${open}`);
}

/** Splits on commas outside parentheses (selector lists, var() fallbacks). */
function splitTop(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "(") depth++;
    else if (text[i] === ")") depth--;
    else if (text[i] === "," && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  return parts;
}

function walk(text: string, media: string[], out: Rule[]): void {
  let i = 0;
  for (;;) {
    const open = text.indexOf("{", i);
    const semi = text.indexOf(";", i);
    if (open < 0) {
      if (
        text
          .slice(i)
          .replace(/[^;]*;/g, "")
          .trim()
      )
        throw new Error(`stray text: ${text.slice(i, i + 40)}`);
      return;
    }
    if (semi >= 0 && semi < open) {
      i = semi + 1; // a statement: @import, @layer a, b;
      continue;
    }
    const prelude = text.slice(i, open).trim().replace(/\s+/g, " ");
    const close = closing(text, open, "{}");
    const body = text.slice(open + 1, close);
    if (prelude.startsWith("@media ")) walk(body, [...media, prelude.slice(7)], out);
    else if (prelude.startsWith("@layer ") || prelude.startsWith("@supports ")) walk(body, media, out);
    else if (!prelude.startsWith("@")) {
      if (body.includes("{")) throw new Error(`nested rule in ${prelude}: the reader doesn't model nesting`);
      const decls = body
        .split(";")
        .filter((d) => d.trim())
        .map((d): [string, string] => {
          const colon = d.indexOf(":");
          if (colon < 0) throw new Error(`not a declaration: ${d.trim()}`);
          // A declared value is trimmed (css-syntax), so "--x: ;" (a single space) is the empty value.
          return [d.slice(0, colon).trim(), d.slice(colon + 1).trim()];
        });
      out.push({ selectors: splitTop(prelude).map((s) => s.trim()), media, decls });
    } // other at-rules (@keyframes, @font-face) hold no theme rules
    i = close + 1;
  }
}

function parse(css: string): Rule[] {
  const out: Rule[] = [];
  walk(css.replace(/\/\*[\s\S]*?\*\//g, ""), [], out);
  return out;
}

// ---------- the resolver ----------

/** The guaranteed-invalid value: `initial` on a custom property, an undeclared one, or a failed substitution. */
const INVALID = Symbol("guaranteed-invalid");
type Value = string | typeof INVALID;
type Env = ReadonlyMap<string, Value>;

/** Substitutes every var() in a value, with nested fallbacks; INVALID if any var() resolves to nothing usable. */
function substitute(value: string, lookup: (name: string) => Value): Value {
  let out = "";
  let i = 0;
  for (;;) {
    const at = value.indexOf("var(", i);
    if (at < 0) return out + value.slice(i);
    out += value.slice(i, at);
    const close = closing(value, at + 3, "()");
    const [name = "", ...rest] = splitTop(value.slice(at + 4, close));
    const own = lookup(name.trim());
    const sub = own !== INVALID ? own : rest.length ? substitute(rest.join(",").trim(), lookup) : INVALID;
    if (sub === INVALID) return INVALID;
    out += sub;
    i = close + 1;
  }
}

/** An element's custom properties: inherited from its parent, and its own declarations substituted where declared
 *  (against this element's values, so a token declared on :root keeps :root's colours in every descendant). */
function element(parent: Env, declared: ReadonlyMap<string, string>): Env {
  const done = new Map<string, Value>();
  const busy = new Set<string>();
  const get = (name: string): Value => {
    const raw = declared.get(name);
    if (raw === undefined) return parent.get(name) ?? INVALID;
    const known = done.get(name);
    if (known !== undefined) return known;
    if (busy.has(name)) return INVALID; // a cycle
    if (/^(inherit|unset|revert|revert-layer)$/i.test(raw)) throw new Error(`${name}: ${raw} isn't modelled`);
    busy.add(name);
    const value = /^initial$/i.test(raw) ? INVALID : substitute(raw, get);
    busy.delete(name);
    done.set(name, value);
    return value;
  };
  const env = new Map(parent);
  for (const name of declared.keys()) env.set(name, get(name));
  return env;
}

/** A normal property's value on an element: INVALID when it is invalid at computed-value time. */
function computed(env: Env, value: string): Value {
  const out = substitute(value, (name) => env.get(name) ?? INVALID);
  return out === INVALID ? INVALID : out.trim();
}

describe("the resolver itself (a hand-worked case)", () => {
  const root = element(
    new Map(),
    new Map([
      ["--a", "#111111"],
      ["--b", "var(--a)"],
      ["--on", ""],
      ["--off", "initial"],
      ["--loop", "var(--loop)"],
    ]),
  );
  const child = element(root, new Map([["--a", "#222222"]]));

  it("substitutes a custom property where it is declared, and a fallback at the element", () => {
    expect(computed(child, "var(--b)")).toBe("#111111");
    expect(computed(child, "var(--a)")).toBe("#222222");
    expect(computed(child, "var(--missing, var(--also-missing, var(--a)))")).toBe("#222222");
  });

  it("models the switches: initial falls back, the empty value substitutes nothing", () => {
    expect(computed(child, "var(--off, var(--a)) var(--on, var(--b))")).toBe("#222222");
    expect(computed(child, "var(--on, x) var(--on, y)")).toBe("");
  });

  it("makes a declaration invalid when a var() has no usable value or fallback", () => {
    expect(computed(child, "var(--off)")).toBe(INVALID);
    expect(computed(child, "1px solid var(--missing, var(--off))")).toBe(INVALID);
    expect(computed(child, "var(--loop, red)")).toBe("red");
    expect(computed(child, "var(--loop)")).toBe(INVALID);
  });
});

// ---------- the theme scopes of the token files, in import order (app.css) ----------

type Theme = "light" | "dark";
type DataTheme = Theme | null;
interface Context {
  dataTheme: DataTheme;
  system: Theme;
}

// The only theme scopes the token files may use, with their specificity (classes, attributes, pseudo-classes).
const SCOPES: Record<string, { where: "root" | "tone"; specificity: number; matches: (c: Context) => boolean }> = {
  ":root": { where: "root", specificity: 1, matches: () => true },
  ':root:not([data-theme="light"])': { where: "root", specificity: 2, matches: (c) => c.dataTheme !== "light" },
  ':root[data-theme="dark"]': { where: "root", specificity: 2, matches: (c) => c.dataTheme === "dark" },
  ".tone-dark": { where: "tone", specificity: 1, matches: () => true },
};
const SYSTEM_DARK = "(prefers-color-scheme: dark)";

const tokenRules = [tokensCss, shelfsyncTokensCss, componentTokensCss].flatMap(parse);

function declared(where: "root" | "tone", context: Context): Map<string, string> {
  const matched: { specificity: number; order: number; decls: [string, string][] }[] = [];
  tokenRules.forEach((rule, order) => {
    const colourMedia = rule.media.filter((m) => m.includes("prefers-color-scheme"));
    if (rule.media.length > colourMedia.length) {
      // viewport and motion queries: they set sizes and durations only
      expect(rule.decls.filter(([name]) => /^--(color|theme)-|-dark$/.test(name))).toEqual([]);
      return;
    }
    for (const m of colourMedia) if (m !== SYSTEM_DARK) throw new Error(`unexpected theme query ${m}`);
    if (colourMedia.length && context.system !== "dark") return;
    for (const selector of rule.selectors) {
      const scope = SCOPES[selector];
      if (!scope) throw new Error(`unexpected theme scope ${selector} in a token file`);
      if (scope.where === where && scope.matches(context))
        matched.push({ specificity: scope.specificity, order, decls: rule.decls });
    }
  });
  matched.sort((a, b) => a.specificity - b.specificity || a.order - b.order);
  return new Map(matched.flatMap((m) => m.decls));
}

function scopes(context: Context): { page: Env; tone: Env } {
  const page = element(new Map(), declared("root", context));
  return { page, tone: element(page, declared("tone", context)) };
}

// ---------- the component rules, read from the stylesheets ----------

// Every stylesheet in this folder except the token file (the generated ones sit in a subfolder).
const SHEETS = import.meta.glob(["./*.css", "!./component-tokens.css"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
const SHEET_NAMES = ["./app.css", "./fonts.css", "./settings.css", "./storage-backup.css", "./stores.css"];
type Component = "card" | "sk" | "secret-pair__mask" | "store-dot";
const RULES: Record<Component, { property: "border" | "background"; family: RegExp }> = {
  card: { property: "border", family: /^border(-color)?$/ },
  sk: { property: "background", family: /^background(-color)?$/ },
  "secret-pair__mask": { property: "background", family: /^background(-color)?$/ },
  "store-dot": { property: "background", family: /^background(-color)?$/ },
};
const allRules = Object.values(SHEETS).flatMap(parse);

/** The one declaration that colours the component. The dark value now sits in the base rule (specificity 0,1,0, not
 *  the old dark rules' 0,3,0), so any other rule that colours the element would win over it: no rule in any
 *  stylesheet or media query (forced-colors included: it sets none of these today) whose selector's last compound
 *  carries the class (.card.is-x, .card:hover, .foo .card; not .card-alert) may set the property or its colour
 *  longhand. Only the base rule, the bare class, does. */
function declaration(component: Component): string {
  const { property, family } = RULES[component];
  const carries = new RegExp(`\\.${component}(?![\\w-])`);
  const found = allRules
    .filter((r) => r.selectors.some((s) => carries.test(s.split(/[\s>+~]+/).pop() ?? "")))
    .flatMap((r) => r.decls.filter(([name]) => family.test(name)).map(([name, value]) => ({ r, name, value })));
  expect(found.map(({ r, name }) => `${r.selectors.join(", ")} { ${name} }`)).toEqual([
    `.${component} { ${property} }`,
  ]);
  return found[0]?.value ?? "";
}

/** The colour the rule gives on an element under the given scope. */
function colour(component: Component, parent: Env, dot?: { light: string; dark: string }): Value {
  const own = new Map<string, string>(
    dot
      ? [
          ["--dot-light", dot.light],
          ["--dot-dark", dot.dark],
        ]
      : [],
  );
  const value = computed(element(parent, own), declaration(component));
  if (value === INVALID || component !== "card") return value;
  const parts = value.split(/\s+/);
  return parts.length === 3 ? (parts[2] ?? INVALID) : INVALID; // width, style, colour
}

// ---------- today's behaviour, as an independent table (the brief's) ----------

type Semantic = keyof typeof tokens.semantic;
const palette = tokens.palette as Record<string, string>;
function semantic(name: Semantic, theme: Theme): string {
  const value = tokens.semantic[name][theme];
  return (value.startsWith("#") ? value : (palette[value] ?? `no palette ${value}`)).toLowerCase();
}

function expected(component: Component, context: Context, inTone: boolean, dot?: { light: string; dark: string }) {
  // The old rules: :root[data-theme="dark"] X, and @media (prefers-color-scheme: dark) :root:not([data-theme="light"]) X
  const pageDark = context.dataTheme === "dark" || (context.dataTheme !== "light" && context.system === "dark");
  // var() in the old rules resolved at the element: .tone-dark's semantic values inside the app bar
  const scope: Theme = pageDark || inTone ? "dark" : "light";
  switch (component) {
    case "card":
      return pageDark ? "transparent" : semantic("border", scope);
    case "sk":
      return semantic(pageDark ? "border" : "fill-subtle", scope);
    case "secret-pair__mask":
      return semantic(pageDark ? "surface-alt" : "fill-subtle", scope);
    case "store-dot": // also dark under .tone-dark (the old `.tone-dark .store-dot`)
      return pageDark || inTone ? dot?.dark : dot?.light;
  }
}

const CONTEXTS: Context[] = (["light", "dark", null] as const).flatMap((dataTheme) =>
  (["light", "dark"] as const).map((system) => ({ dataTheme, system })),
);
/** Hex is case-insensitive: both sides are compared in lower case. */
const lower = (value: Value | undefined): Value | undefined =>
  typeof value === "string" ? value.toLowerCase() : value;

const PLACES = [
  ["on the page", false],
  ["inside .tone-dark", true],
] as const;

describe.each(CONTEXTS)("data-theme $dataTheme, Windows $system", (context) => {
  describe.each(PLACES)("%s", (_where, inTone) => {
    // resolved inside each test, so nothing asserts while Vitest collects the tests
    const parent = (): Env => {
      const { page, tone } = scopes(context);
      return inTone ? tone : page;
    };
    it.each<Component>(["card", "sk", "secret-pair__mask"])("%s keeps its colour", (component) => {
      const want = lower(expected(component, context, inTone));
      expect(want).toMatch(/^(#[0-9a-f]{6}|transparent)$/);
      expect(lower(colour(component, parent()))).toBe(want);
    });
    it.each(Object.entries(STORE_PALETTE))("store-dot keeps the %s pair's colour", (_key, dot) => {
      const want = lower(expected("store-dot", context, inTone, dot));
      expect(want).toMatch(/^#[0-9a-f]{6}$/);
      expect(lower(colour("store-dot", parent(), dot))).toBe(want);
    });
  });
});

// ---------- the structure the mechanisms rely on ----------

describe("the theme scopes", () => {
  it("the stylesheets were found (so the checks can't pass on nothing)", () => {
    expect(Object.keys(SHEETS)).toEqual(expect.arrayContaining(SHEET_NAMES));
    for (const text of Object.values(SHEETS)) expect(text.length).toBeGreaterThan(500);
  });

  it.each(Object.entries(SHEETS))("%s has no theme scope of its own (only the token files do)", (_path, text) => {
    expect(text).not.toMatch(/\[data-theme="dark"\]|prefers-color-scheme/);
  });

  function block(css: string, selector: string, media: string[]): [string, string][] {
    const found = parse(css).filter((r) => r.selectors.includes(selector) && r.media.join() === media.join());
    expect(found).toHaveLength(1);
    return found[0]?.decls ?? [];
  }

  it("the two dark forms in component-tokens.css declare the same tokens with the same values", () => {
    const attribute = block(componentTokensCss, ':root[data-theme="dark"]', []);
    expect(attribute.length).toBeGreaterThanOrEqual(5);
    expect(block(componentTokensCss, ':root:not([data-theme="light"])', [SYSTEM_DARK])).toEqual(attribute);
  });

  // Needed beside the colour checks: the mask's light fallback and its dark token are the same colour in dark (both
  // ink-750 today), so a misspelt token there would still resolve to the right colour.
  it("the rules read exactly the tokens component-tokens.css declares", () => {
    const read = new Set(
      (Object.keys(RULES) as Component[])
        .flatMap((c) => [...declaration(c).matchAll(/var\((--[a-z0-9-]+)/g)])
        .map((m) => m[1])
        // the store's own colours are set on the element (StoreBadge), not tokens
        .filter((name) => name !== "--dot-dark" && (name?.startsWith("--theme-") || name?.endsWith("-dark"))),
    );
    const declaredHere = new Set(block(componentTokensCss, ':root[data-theme="dark"]', []).map(([name]) => name));
    expect([...read].sort()).toEqual([...declaredHere].sort());
  });

  it(".tone-dark's semantic values are the dark ones (so dark tokens from :root are right inside it too)", () => {
    const colours = (decls: [string, string][]) =>
      Object.fromEntries(decls.filter(([n]) => n.startsWith("--color-")).map(([n, v]) => [n, v.toLowerCase()]));
    const dark = colours(block(tokensCss, ':root[data-theme="dark"]', []));
    expect(Object.keys(dark).length).toBeGreaterThan(20);
    expect(colours(block(tokensCss, ':root:not([data-theme="light"])', [SYSTEM_DARK]))).toEqual(dark);
    expect(colours(block(shelfsyncTokensCss, ".tone-dark", []))).toEqual(dark);
  });

  it("StoreBadge sets the --dot-light and --dot-dark the store-dot rule reads", () => {
    expect(storeBadge).toContain('{ "--dot-light": dot.light, "--dot-dark": dot.dark }');
  });
});
