import { useCallback, useState } from "react";
import { applyTheme, browserThemeHost, readPreference, savePreference, type ThemePreference } from "./theme";

/**
 * The theme preference for the theme menu. Nothing is written while React renders: early.ts applied the stored
 * preference before the first render, and a new choice is applied once, in the event that makes it. A Windows switch
 * while on "system" needs no listener here: "system" leaves <html> without data-theme, so the stylesheet's media
 * query follows Windows by itself.
 */
export function useTheme(): { preference: ThemePreference; setPreference: (next: ThemePreference) => void } {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => readPreference(browserThemeHost));

  const setPreference = useCallback((next: ThemePreference) => {
    savePreference(browserThemeHost, next);
    applyTheme(browserThemeHost, next);
    setPreferenceState(next);
  }, []);

  return { preference, setPreference };
}
