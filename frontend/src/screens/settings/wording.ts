// Every owner-facing string of Settings (UI-SET), in one place, with where it comes from:
// - "13 §3 Updates": docs/13-content.md section 3, the rows "Settings › Updates", "Update check results",
//   "Last switch" and "Updates API errors" (m1b.2, Lead (proposed));
// - "13 §6" and "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js);
// - "proposed (m1b.4)": new in this task, listed in docs/runs/m1b.4-settings-screens.md section 4 for the lead.

import type { ErrorCode } from "../../api/client";
import type { LastCheck, SwitchResult } from "../../api/settings";

// ---------- the shell (mockup) ----------
export const SETTINGS_TITLE = "Settings";

/** The four pages that come later (proposed (m1b.4)): what the page will hold, in the empty-state pattern of 13 §2. */
export const LATER: Record<"storage" | "rules" | "backup", { text: string; sub: string }> = {
  storage: {
    text: "Storage settings come in a later version of ShelfSync.",
    sub: "This is where you'll add the S3 bucket ShelfSync uploads to, and test its keys.",
  },
  rules: {
    text: "Rules come in a later version of ShelfSync.",
    sub: "This is where you'll set auto-apply, its brakes and the words used for matching.",
  },
  backup: {
    text: "Backup settings come in a later version of ShelfSync.",
    sub: "This is where you'll export and import your settings, and choose how long backups are kept.",
  },
};

// ---------- Settings › Updates (13 §3 Updates) ----------
export const U = {
  heading: (v: string) => `ShelfSync ${v}`,
  development: "This copy of ShelfSync runs from source, so updates are turned off.",
  noKey: "This build can't verify updates, so it won't install any.",
  empty:
    "ShelfSync checks for updates by itself. A GitHub token is optional: add one only if GitHub refuses the check or the project is private.",
  upToDate: (v: string) => `ShelfSync ${v} is up to date.`,
  downloading: (v: string) => `Version ${v} is being downloaded and checked.`,
  ready: (v: string) => `Version ${v} is ready to install.`,
  checkNow: "Check now",
  install: (v: string) => `Install ${v} and restart`,
  rollBack: "Roll back app",
  installText: "ShelfSync will close and open again. This takes about a minute.",
  rollBackTitle: (v: string) => `Roll back to ${v}?`,
  // The roll back dialog: 13 §6's rows, tied to the owner's decision of 2026-10-26 (11), which win over 13 §3's
  // proposed dialog lines (lead, m1b.4 review item 6). `v` is the version rolled back from (the installed one).
  rollBackRestart: "ShelfSync will close and open again.", // 13 §3
  rollBackFiles: (v: string) =>
    `${v} didn't change the database, so your data stays as it is. You can install ${v} again from Settings › Updates.`,
  /** `date` null: the backup's time isn't known, so the line goes without it (lead, review item 5). */
  rollBackDatabase: (v: string, date: string | null) =>
    `${v} changed the database. ShelfSync restores the backup taken just before the update${date ? `, on ${date}` : ""}. Changes made since then are lost and can't be brought back. You can install ${v} again from Settings › Updates.`,
  rollBackCopyKept: "A copy of the current data is kept in the backups folder.", // 13 §3
  rollBackConfirm: "Roll back",
  cancel: "Cancel",
  // proposed (m1b.4): the Install dialog's title, the "preparing" line, the restart panel's lines and its late line
  installTitle: (v: string) => `Install ShelfSync ${v}?`,
  preparing: (v: string) => `Checking the files of ${v} before it's installed.`,
  restartingTitle: "ShelfSync is restarting", // the brief's words (m1b.4 section 1)
  restartingText: "When ShelfSync is back, it opens in a new tab, or this one reloads.", // lead (re-review low 3)
  restartingLate: "ShelfSync hasn't answered yet. If it doesn't open by itself, open it from the Start menu.",
  // proposed (m1b.4 review item 1): a new copy answers, so this tab's sign-in is gone and the switcher opened a new one
  backTitle: "ShelfSync is back",
  backText: "It opened in a new tab, signed in. You can close this one.",
  // lead (re-review low 1): the new version answers and already knows this tab (the new tab signed in)
  backRunning: (v: string) => `ShelfSync ${v} is running. You can close this tab, or keep using it.`,
  // proposed (m1b.4): GET /api/updates got no answer, or a refusal
  loadFailed: "ShelfSync didn't answer, so the update status can't be shown.",
  loadRefused: (status: number) => `ShelfSync refused to show the update status (HTTP ${status}).`,
  tryAgain: "Try again",
  // proposed (m1b.4): the roll back button is off because the backup it needs is gone (the words of 13 §3's
  // Last switch `backup_missing`)
  rollBackNoBackup: "The backup needed to roll back isn't there.",
  // mockup: opens the Help panel's GitHub token guide (11, 2026-10-28: it waited for the Help panel, m2.5a)
  tokenGuide: "How to make the token",
};

// ---------- the GitHub token (13 §3 Updates; the field's hint is the mockup's) ----------
export const T = {
  label: "GitHub token (read-only)", // mockup
  saved: "Saved", // mockup (the wizard's saved secret)
  notSet: "Not set", // proposed (m1b.4)
  hint: "Kept in Windows Credential Manager. It's never shown again or sent to this page.", // mockup
  newLabel: "New GitHub token", // mockup pattern "New <label>" (screen-reader label of the input)
  placeholder: "Paste the new value", // mockup
  replace: "Replace", // mockup
  save: "Save", // mockup
  remove: "Remove", // mockup (Remove a store)
  cancel: "Cancel",
  savedDone: "Token saved.",
  removedDone: "Token removed.",
  refused: "That isn't a fine-grained GitHub token (it starts with github_pat_).",
  /** 13 §3, with the mockup's "in N days" (review item 20); the date only. Expired (days ≤ 0): lead wording
   *  (re-review low 4). */
  expires: (date: string, days: number | null) => {
    if (days === null) return `Your GitHub token expires on ${date}. Make a new one before then.`;
    if (days <= 0) return `Your GitHub token expired on ${date}. Make a new one, or remove it to check without one.`;
    return `Your GitHub token expires in ${days} ${days === 1 ? "day" : "days"}, on ${date}. Make a new one before then.`;
  },
  expiresOn: (date: string) => `Expires on ${date}.`, // proposed (m1b.4): the saved token's expiry, when GitHub said
  // proposed (m1b.4; lead wording, review item 16: no answer is never stated as an outcome)
  saveFailed: "ShelfSync didn't answer, so the token may not have been saved. Reload this page to check.",
  removeFailed: "ShelfSync didn't answer, so the token may not have been removed. Reload this page to check.",
};

/** 13 §3 "Update check results" (`last_check.outcome`); `v` is the version found, when known. */
export function checkProblem(
  check: LastCheck,
  v: string | null,
): { tone: "danger" | "warning"; title: string; body: string | null } | null {
  const found = v ? `Version ${v}` : "An update"; // proposed (m1b.4): no version known (after a restart)
  const line = (tone: "danger" | "warning", title: string, body: string | null = null) => ({ tone, title, body });
  switch (check.outcome) {
    case "ok":
    case "no_release":
      return null;
    case "token_refused":
      return line("danger", "GitHub refused the token. Check it, or remove it to check without one.");
    case "rate_limited":
      return line("warning", "GitHub says there were too many checks. Try again later.");
    case "not_public":
      return line("warning", "GitHub can't find the project. If it is private, add a read-only token.");
    case "unreachable":
      return line("warning", "Couldn't reach GitHub. Check your connection.");
    case "update_refused":
      return line(
        "danger",
        `${found} was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed.`,
      );
    case "update_failed":
      return line(
        "warning",
        `${found} couldn't be downloaded. It will be tried again at the next check.`,
        check.detail === "no_space" ? "There isn't enough free space on the drive ShelfSync is installed on." : null,
      );
  }
}

export const NO_RELEASE = "No release has been published yet.";
export const checkedAt = (date: string) => `Checked ${date}.`;

/** 13 §3 "Last switch": the reason codes with wording; a reason is a code, or codes joined by "+" (the first is the
 *  cause). A code without wording is never shown (nothing from a file is echoed). */
function switchReason(reason: string | null, v: string): string | null {
  const first = reason?.split("+")[0] ?? "";
  const words: Record<string, string> = {
    no_answer: "It didn't answer in time.",
    wrong_version: "It reported the wrong version.",
    untrusted_listener: "Something else was answering on ShelfSync's address.",
    exited: "It stopped while starting.",
    migration_failed: "Its database update failed and was undone.",
    old_copy_still_running: "ShelfSync didn't close in time.",
    old_process_mismatch: "The program that was running wasn't this version of ShelfSync.",
    lock_busy: "Another copy of ShelfSync was starting.",
    files_changed: `The files of ${v} no longer match what was signed.`,
    manifest_missing: `The signature of ${v} can't be checked.`,
    manifest_invalid: `The signature of ${v} can't be checked.`,
    backup_failed: "A copy of the current data couldn't be made, so the roll back was refused.",
    backup_missing: "The backup needed to roll back isn't there.",
    backup_mismatch: "The backup needed to roll back isn't there.",
    database_changed: "The database changed since you confirmed. Try again.",
  };
  return Object.hasOwn(words, first) ? (words[first] ?? null) : null;
}

export interface SwitchLine {
  tone: "success" | "warning" | "danger";
  title: string;
  body: string | null;
}

export function lastSwitch(result: SwitchResult): SwitchLine {
  const to = result.to_version;
  switch (result.outcome) {
    case "updated":
      return { tone: "success", title: `Updated to ${to}.`, body: null };
    case "rolled_back":
      return { tone: "success", title: `Rolled back to ${to}.`, body: null };
    case "kept_old":
      return {
        tone: "warning",
        title: `${to} didn't start, so ${result.from_version} is back.`,
        body: switchReason(result.reason, to),
      };
    case "not_switched":
      return { tone: "warning", title: "Nothing was changed.", body: switchReason(result.reason, to) };
    case "failed":
      return {
        tone: "danger",
        title: "Neither version started. Open ShelfSync from the Start menu; the log has the reason.",
        body: null,
      };
  }
}

/** 13 §3 "Updates API errors" (`{"error": "<code>"}`); other codes have the general line below. */
const API_ERRORS: Partial<Record<ErrorCode, string>> = {
  development_build: "Updates are turned off in this copy.",
  busy: "An update is already under way.",
  no_key: "This build can't verify updates.",
  nothing_to_install: "There's no downloaded update to install.",
  no_previous: "There's no earlier version to roll back to.",
  no_backup: "The backup needed to roll back isn't there, so the roll back was refused.",
  files_changed: "The files of that version changed on disk, so it was refused.",
  manifest_invalid: "That version's signature can't be checked, so it was refused.",
  manifest_missing: "That version's signature can't be checked, so it was refused.",
  cannot_restart: "ShelfSync couldn't close itself to restart, so nothing was changed.",
  too_soon: "A check ran a moment ago. Try again in a minute.",
};

/** 13 §3 `busy`: shown the same way from GET /api/updates and from a refused action (review item 15). */
export const BUSY_LINE = API_ERRORS.busy ?? "";

/** The line for a refused or unanswered Updates action. Proposed (m1b.4): the two general lines; an unanswered
 *  request never states its outcome (lead wording, review item 16). */
export function updatesActionError(code: ErrorCode | null, status: number | null): string {
  if (code && Object.hasOwn(API_ERRORS, code)) return API_ERRORS[code] ?? "";
  if (status === null) return "ShelfSync didn't answer, so that may not have happened. Reload this page to check.";
  return `ShelfSync refused that (HTTP ${status}), so nothing was changed.`;
}

/** The tone of an action's line: "An update is already under way." is information, like the GET state (item 19). */
export function updatesActionTone(code: ErrorCode | null): "info" | "danger" {
  return code === "busy" ? "info" : "danger";
}

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
