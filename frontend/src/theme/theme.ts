// Theme (UI-SHELL): follows Windows (prefers-color-scheme) by default, with a manual override: system, light, dark.
// Until M1b's Settings API exists the override is kept in localStorage, as a convenience only: every access is
// wrapped, and the page works the same without storage (it then follows Windows). M1b moves it to the `theme`
// setting. The stylesheet does the work: tokens.css (and every dark rule in app.css) follows the media query while
// <html> has no data-theme, and a set data-theme overrides it. So "system" sets no attribute at all: every screen,
// the signed-out one included, follows a Windows switch live, with no script listening for it.

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "shelfsync.theme";
export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];
export const DARK_QUERY = "(prefers-color-scheme: dark)";

/** The few browser objects this module needs, so tests can pass fakes (the unit tests run without a DOM). */
export interface ThemeHost {
  storage: () => Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  prefersDark: () => boolean;
  root: () => { dataset: DOMStringMap } | null;
}

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEME_PREFERENCES as readonly string[]).includes(value);
}

export function readPreference(host: ThemeHost): ThemePreference {
  try {
    const value = host.storage()?.getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : "system";
  } catch {
    return "system"; // storage blocked or broken: follow Windows
  }
}

export function savePreference(host: ThemeHost, preference: ThemePreference): void {
  try {
    const storage = host.storage();
    if (!storage) return;
    if (preference === "system") storage.removeItem(THEME_STORAGE_KEY);
    else storage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Not saved; the choice still applies to this tab.
  }
}

export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (preference === "system") return prefersDark ? "dark" : "light";
  return preference;
}

/** Sets data-theme on <html> for an override, removes it for "system", and returns the theme that results. */
export function applyTheme(host: ThemeHost, preference: ThemePreference): ResolvedTheme {
  let dark = false;
  try {
    dark = host.prefersDark();
  } catch {
    dark = false;
  }
  const root = host.root();
  if (root) {
    if (preference === "system") delete root.dataset.theme;
    else root.dataset.theme = preference;
  }
  return resolveTheme(preference, dark);
}

/** The real browser, each piece guarded so a missing API never stops the page. */
export const browserThemeHost: ThemeHost = {
  storage: () => {
    try {
      return typeof window === "undefined" ? null : window.localStorage;
    } catch {
      return null;
    }
  },
  prefersDark: () => typeof window !== "undefined" && window.matchMedia?.(DARK_QUERY).matches === true,
  root: () => (typeof document === "undefined" ? null : document.documentElement),
};
