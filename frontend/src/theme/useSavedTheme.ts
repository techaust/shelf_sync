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
import type { ThemePreference } from "./theme";
import { themeStore, useTheme } from "./useTheme";

/** After a save, the cached App settings hold what is stored now (the answer's five values). */
export function cacheSaved(previous: AppSettings | undefined, saved: AppSettingsSaved): AppSettings | undefined {
  return previous ? { ...previous, ...valuesOf(saved) } : previous;
}

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
      try {
        const saved = await settingsWriter(api).saveTheme(next);
        queryClient.setQueryData<AppSettings>(APP_SETTINGS_QUERY_KEY, (old) => cacheSaved(old, saved));
        return true;
      } catch {
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
  const { data } = useQuery({ queryKey: APP_SETTINGS_QUERY_KEY, queryFn: () => getAppSettings(api) });
  const saved = data?.theme;
  useEffect(() => {
    if (saved) themeStore.set(saved);
  }, [saved]);
}
