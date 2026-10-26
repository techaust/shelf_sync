import { useCallback, useEffect, useState } from "react";
import {
  applyTheme,
  browserThemeHost,
  DARK_QUERY,
  type ResolvedTheme,
  readPreference,
  savePreference,
  type ThemePreference,
} from "./theme";

/** The theme preference and the theme it resolves to; re-applies when Windows switches while on "system". */
export function useTheme(): {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
} {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => readPreference(browserThemeHost));
  const [resolved, setResolved] = useState<ResolvedTheme>(() => applyTheme(browserThemeHost, preference));

  useEffect(() => {
    setResolved(applyTheme(browserThemeHost, preference));
    if (preference !== "system" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DARK_QUERY);
    const onChange = () => setResolved(applyTheme(browserThemeHost, "system"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    savePreference(browserThemeHost, next);
    setPreferenceState(next);
  }, []);

  return { preference, resolved, setPreference };
}
