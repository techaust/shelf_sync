import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import {
  APP_SETTINGS_QUERY_KEY,
  type AppSettings,
  type AppSettingsSaved,
  getAppSettings,
  valuesOf,
} from "../api/settings";
import { settingsWriter } from "../api/settingsWriter";
import { useServices } from "../app/services";
import { isRestarting, useSwitchPhase } from "../screens/settings/switchStore";
import type { ThemePreference } from "./theme";
import { type ThemeStore, themeStore, useTheme } from "./useTheme";

/** After a save, the cached App settings hold what is stored now (the answer's five values). */
export function cacheSaved(previous: AppSettings | undefined, saved: AppSettingsSaved): AppSettings | undefined {
  return previous ? { ...previous, ...valuesOf(saved) } : previous;
}

/**
 * The saved theme and this tab's own choices (review item 4): while a choice is still being saved, an older save's
 * answer (or a refetch) must not put an older theme back. So a server theme applies only when no choice is pending.
 */
export function createThemeSync(store: Pick<ThemeStore, "set">) {
  let pending = 0;
  return {
    /** A choice starts saving; returns the function that ends it (call it before the answer goes into the cache). */
    begin(): () => void {
      pending += 1;
      let ended = false;
      return () => {
        if (ended) return;
        ended = true;
        pending -= 1;
      };
    },
    /** The App settings arrived or changed: their theme applies, unless a choice is still being saved. */
    fromServer(theme: ThemePreference): boolean {
      if (pending > 0) return false;
      store.set(theme);
      return true;
    },
    pending: (): number => pending,
  };
}

export const themeSync = createThemeSync(themeStore);

/**
 * The theme as Settings › App saves it (SET-06): a choice, from the app bar or from Settings › App, applies to this
 * tab at once (theme/ module) and is saved to the `theme` setting. Resolves false when the save failed: the choice
 * still applies to this tab, and localStorage keeps it for the next page load.
 */
export function useSavedTheme(): { preference: ThemePreference; choose: (next: ThemePreference) => Promise<boolean> } {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const { preference, setPreference } = useTheme();
  const choose = useCallback(
    async (next: ThemePreference) => {
      setPreference(next);
      // While ShelfSync restarts, nothing is sent: this tab's sign-in may be gone (re-review, medium)
      if (isRestarting()) return false;
      const end = themeSync.begin();
      try {
        const saved = await settingsWriter(api).saveTheme(next);
        end();
        queryClient.setQueryData<AppSettings>(APP_SETTINGS_QUERY_KEY, (old) => cacheSaved(old, saved));
        return true;
      } catch {
        end();
        return false;
      }
    },
    [api, queryClient, setPreference],
  );
  return { preference, choose };
}

/**
 * The saved theme wins once it is known: when the App settings arrive (or change), this tab takes their theme, so
 * every tab and every page load shows the saved one. Mounted once, in the AppShell.
 */
export function useThemeFromServer(): void {
  const { api } = useServices();
  const restarting = useSwitchPhase().kind === "restarting";
  const { data } = useQuery({
    queryKey: APP_SETTINGS_QUERY_KEY,
    queryFn: () => getAppSettings(api),
    enabled: !restarting, // paused while ShelfSync restarts (re-review, medium)
  });
  const saved = data?.theme;
  useEffect(() => {
    if (saved) themeSync.fromServer(saved);
  }, [saved]);
}
