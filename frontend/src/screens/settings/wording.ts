// The owner-facing strings of the Settings shell and Settings › App (UI-SET), with where they come from:
// - "13 §6" and "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js);
// - "proposed (m1b.4)": new in m1b.4, listed in docs/runs/m1b.4-settings-screens.md section 4 for the lead.
// The wording of Settings › Updates and the GitHub token is in lib/updatesWording.ts (moved there in T4, so the
// switch in lib/ can use it).

// ---------- the shell (mockup) ----------
export const SETTINGS_TITLE = "Settings";

/** The page that comes later (proposed (m1b.4)): what it will hold, in the empty-state pattern of 13 §2. Storage and
 *  Backup became real pages in m2.5b. */
export const LATER: Record<"rules", { text: string; sub: string }> = {
  rules: {
    text: "Rules come in a later version of ShelfSync.",
    sub: "This is where you'll set auto-apply, its brakes and the words used for matching.",
  },
};

// ---------- Settings › App (mockup; 13 §6 for the reset) ----------
export const A = {
  cardTitle: "App",
  theme: "Theme",
  themeOptions: { system: "Same as Windows", light: "Light", dark: "Dark" },
  startWithWindows: "Start with Windows",
  startHint: "ShelfSync starts in the tray when you sign in to Windows.",
  // proposed (m1b.4): a development copy (installed: false, or start_with_windows_result "not_installed")
  startDevelopment: "This copy of ShelfSync runs from source, so it can't start with Windows.",
  notifications: "Notifications",
  notificationsHint: "A Windows notification when Review needs you or an update goes partial.",
  port: "Port",
  portHint: "If it's taken at start, ShelfSync uses the next free port up to 47624.",
  logs: "Keep logs for",
  days: "days",
  save: "Save app",
  // proposed (m1b.4): the form's limits, checked before saving (the API's limits)
  portLimit: (min: number, max: number) => `Use a port from ${min} to ${max}.`,
  logsLimit: (min: number, max: number) => `Use a number of days from ${min} to ${max}.`,
  // proposed (m1b.4): the save's answer
  saved: "Settings saved.",
  portNext: "The new port is used after the next start.",
  savedNotApplied:
    "Settings saved, but Windows wasn't changed: Start with Windows couldn't be set. Save again to try once more.",
  // lead wording (review item 16): no answer is never stated as an outcome
  saveFailed: "ShelfSync didn't answer, so the settings may not have been saved. Reload this page to check.",
  saveRefused: (status: number) => `ShelfSync refused the settings (HTTP ${status}), so nothing was saved.`,
  themeFailed: "The theme applies to this tab, but it may not have been saved. Reload this page to check.",
  // proposed (review item 9): a refresh failed while the page still shows what it had
  staleNotice: "ShelfSync didn't answer just now, so this may be out of date.",
  loadFailed: "ShelfSync didn't answer, so the app settings can't be shown.",
  loadRefused: (status: number) => `ShelfSync refused to show the app settings (HTTP ${status}).`,
  // mockup and 13 §6
  resetTitle: "Reset access token",
  resetText: "Makes a new token for signing in to this page.",
  resetLine: "Every open ShelfSync tab is signed out. Open ShelfSync again from the tray icon or the Start menu.",
  resetDialogTitle: "Reset the access token?",
  resetDialogLead: "ShelfSync makes a new access token and the old one stops working.",
  resetConfirm: "Reset access token",
  // proposed (m1b.4)
  resetFailed: "ShelfSync didn't answer, so the reset may not have happened. Reload this page to check.", // lead
  resetRefused: (status: number) => `ShelfSync refused the reset (HTTP ${status}), so the access token is unchanged.`,
};
