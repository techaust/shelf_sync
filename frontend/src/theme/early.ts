// Imported first by main.tsx: sets the theme before anything else runs or renders, without an inline script (the
// CSP forbids one). Until this runs, the stylesheet already follows Windows through prefers-color-scheme, and the
// page is empty (React hasn't rendered), so only a manual override that differs from Windows needs this module.
import { applyTheme, browserThemeHost, readPreference } from "./theme";

applyTheme(browserThemeHost, readPreference(browserThemeHost));
