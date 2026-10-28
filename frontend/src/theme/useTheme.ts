import { useSyncExternalStore } from "react";
import {
  applyTheme,
  browserThemeHost,
  readPreference,
  savePreference,
  type ThemeHost,
  type ThemePreference,
} from "./theme";

/**
 * One theme preference for the whole tab, shared by the app bar's ThemeMenu and Settings › App (UI-SET), so the two
 * always show the same value. A choice is applied once, in the event that makes it (localStorage keeps it for the
 * next page load, before React renders: early.ts). A Windows switch while on "system" needs no listener: "system"
 * leaves <html> without data-theme, so the stylesheet's media query follows Windows by itself.
 */
export function createThemeStore(host: ThemeHost) {
  let preference: ThemePreference | null = null;
  const listeners = new Set<() => void>();
  const get = (): ThemePreference => {
    if (preference === null) preference = readPreference(host);
    return preference;
  };
  return {
    get,
    /** Applies and remembers `next`; listeners hear of it only when it changed. */
    set(next: ThemePreference): void {
      savePreference(host, next);
      applyTheme(host, next);
      if (next === get()) return;
      preference = next;
      for (const listener of listeners) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type ThemeStore = ReturnType<typeof createThemeStore>;

export const themeStore: ThemeStore = createThemeStore(browserThemeHost);

export function useTheme(store: ThemeStore = themeStore): {
  preference: ThemePreference;
  setPreference: (next: ThemePreference) => void;
} {
  const preference = useSyncExternalStore(store.subscribe, store.get, store.get);
  return { preference, setPreference: store.set };
}
