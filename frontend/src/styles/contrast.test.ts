// WCAG 2.2 AA for every text/background pair the shell uses, in light and dark (05 section 2.2, 07 section 4), and
// 3:1 for non-text marks: focus rings, control borders, the ramp meter, and the store identifier dots on every
// surface they can sit on (05 section 2.3). Values come straight from brand/tokens.json, the source of truth.
import { describe, expect, it } from "vitest";
import tokens from "../../../brand/tokens.json";

type Theme = "light" | "dark";
type Semantic = keyof typeof tokens.semantic;

const palette = tokens.palette as Record<string, string>;
const hex = (value: string): string => (value.startsWith("#") ? value : (palette[value] ?? "")).toLowerCase();
const semantic = (name: Semantic, theme: Theme): string => hex(tokens.semantic[name][theme]);
const color = (name: string): string => {
  const value = palette[name];
  if (!value) throw new Error(`no palette token ${name}`);
  return value.toLowerCase();
};

function luminance(value: string): number {
  const match = /^#([0-9a-f]{6})$/.exec(value);
  if (!match?.[1]) throw new Error(`not a #rrggbb colour: ${value}`);
  const n = Number.parseInt(match[1], 16);
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = 4.5; // WCAG 1.4.3, normal text (the shell's text is 12-16 px)
const NON_TEXT = 3; // WCAG 1.4.11, focus rings, control borders, icons that carry meaning, store dots

// The app bar is ink in both themes (05 section 2.2): ink-900 under the light theme, ink-750 under the dark one.
// Its contents use the dark semantic values (.tone-dark).
const APP_BAR = { light: color("ink-900"), dark: color("ink-750") };

describe.each<Theme>(["light", "dark"])("%s theme", (theme) => {
  const s = (name: Semantic) => semantic(name, theme);
  const page = [
    ["page", s("bg")],
    ["nav and cards", s("surface")],
    ["status strip", s("surface-alt")],
    ["tooltip and menu", s("surface-raised")],
  ] as const;

  const textPairs: [string, string, string][] = [
    ...page.flatMap(([where, bg]) => [
      [`text on ${where}`, s("text"), bg] as [string, string, string],
      [`muted text on ${where}`, s("text-muted"), bg] as [string, string, string],
    ]),
    ["active nav label on the selection fill", s("text"), s("selection")],
    ["nav count on its fill", s("text"), s("fill-subtle")],
    ["button label on a surface", s("btn-secondary-fg"), s("surface")],
    ["button label on its hover fill", s("btn-secondary-fg"), s("surface-alt")],
    ["primary button label", s("btn-primary-fg"), s("btn-primary-bg")],
    ["primary button label on hover", s("btn-primary-fg"), s("btn-primary-hover")],
    ["link on a surface", s("link"), s("surface")],
    ["menu item on its highlight", s("text"), s("surface-alt")],
    ["skip link", s("text"), s("surface")],
    ["accent text on a surface", s("text-accent"), s("surface")],
    ...(["success", "warning", "danger", "info"] as const).map(
      (tone) => [`${tone} text on a surface`, s(tone), s("surface")] as [string, string, string],
    ),
  ];

  it.each(textPairs)("%s meets 4.5:1", (_name, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(TEXT);
  });

  const nonTextPairs: [string, string, string][] = [
    ...page.map(([where, bg]) => [`focus ring on ${where}`, s("focus"), bg] as [string, string, string]),
    ["focus ring on the selection fill", s("focus"), s("selection")],
    ["control border on a surface", s("border-control"), s("surface")],
    ["control border on the page", s("border-control"), s("bg")],
    ["active nav marker and icon on the selection fill", s("text-accent"), s("selection")],
    ["ramp meter fill on the status strip", s("text-accent"), s("surface-alt")],
  ];

  it.each(nonTextPairs)("%s meets 3:1", (_name, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(NON_TEXT);
  });

  describe("the app bar (ink in both themes, .tone-dark contents)", () => {
    const bar = APP_BAR[theme];
    const d = (name: Semantic) => semantic(name, "dark");
    it.each<[string, string, string, number]>([
      ["app-bar text", color("mist"), bar, TEXT],
      ["app-bar muted text", color("ink-300"), bar, TEXT],
      ["chip text (.tone-dark text)", d("text"), bar, TEXT],
      ["button text on its hover fill", d("text"), d("surface-raised"), TEXT],
      ["focus ring", d("focus"), bar, NON_TEXT],
      ["button border", d("border-control"), bar, NON_TEXT],
      ["connected icon", d("success"), bar, NON_TEXT],
      ["refused or unreachable icon and text", d("danger"), bar, TEXT],
    ])("%s", (_name, fg, bg, min) => {
      expect(contrast(fg, bg)).toBeGreaterThanOrEqual(min);
    });
  });
});

// 05 section 2.3: the store identifier dots, with the surfaces each can sit on. Store colours are store data (the
// backend's store table from M2), not tokens; these are the two stores' approved values.
const STORES = [
  { code: "GF", light: "#4d4d99", dark: "#a3a3e6" },
  { code: "PW", light: "#007b80", dark: "#3cc8cb" },
];
const LIGHT_SURFACES = ["white", "stone-50", "stone-100", "stone-200", "verdigris-100"];
// The dark surfaces, plus the app bar's two inks (the health chips sit on it in both themes).
const DARK_SURFACES = ["ink-950", "ink-900", "ink-800", "ink-750", "ink-700", "verdigris-900"];

describe("store identifier dots (05 section 2.3)", () => {
  it.each(STORES.flatMap((store) => LIGHT_SURFACES.map((surface) => [store.code, store.light, surface] as const)))(
    "%s light dot %s on %s meets 3:1",
    (_code, dot, surface) => {
      expect(contrast(dot, color(surface))).toBeGreaterThanOrEqual(NON_TEXT);
    },
  );

  it.each(STORES.flatMap((store) => DARK_SURFACES.map((surface) => [store.code, store.dark, surface] as const)))(
    "%s dark dot %s on %s meets 3:1",
    (_code, dot, surface) => {
      expect(contrast(dot, color(surface))).toBeGreaterThanOrEqual(NON_TEXT);
    },
  );
});

describe("the contrast function", () => {
  it("matches WCAG's reference values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(contrast("#ffffff", "#ffffff")).toBe(1);
  });
});
