// Theme (UI-SHELL): follows Windows (prefers-color-scheme) by default, with a manual override: system, light, dark.
// Until M1b's Settings API exists the override is kept in localStorage, as a convenience only: every access is
// wrapped, and the page works the same without storage (it then follows Windows). M1b moves it to the `theme`
// setting. The stylesheet does the work: tokens.css switches on :root[data-theme] (and on the media query when
// data-theme isn't set), so this module only decides the attribute.

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

/** Sets data-theme on <html> and returns what it set. */
export function applyTheme(host: ThemeHost, preference: ThemePreference): ResolvedTheme {
  let dark = false;
  try {
    dark = host.prefersDark();
  } catch {
    dark = false;
  }
  const resolved = resolveTheme(preference, dark);
  const root = host.root();
  if (root) root.dataset.theme = resolved;
  return resolved;
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
