// The checks the Settings forms run before anything is sent, with the API's own limits (api/app_settings.py,
// api/secrets.py), so a value the API would refuse is caught in the form, next to its field.

import type { AppSettings, AppSettingsSaved, AppSettingsValues } from "../../api/settings";
import type { ThemePreference } from "../../theme/theme";
import { A, T } from "./wording";

/** ports.py DEFAULT_PORT and LAST_PORT; logs.py MAX_LOG_RETENTION_DAYS. */
export const PORT_MIN = 47615;
export const PORT_MAX = 47624;
export const LOG_DAYS_MIN = 1;
export const LOG_DAYS_MAX = 365;
/** The PUT body's limit (GithubTokenRequest.value). */
export const TOKEN_MAX_LENGTH = 300;
/** update/service.py _TOKEN_SHAPE: a fine-grained token. */
const TOKEN_SHAPE = /^github_pat_[A-Za-z0-9_]{20,255}$/;

export function checkGithubToken(value: string): string | null {
  return TOKEN_SHAPE.test(value) ? null : T.refused;
}

/** The App form as typed: the two numbers are text until they are checked. */
export interface AppForm {
  port: string;
  logDays: string;
  startWithWindows: boolean;
  notifications: boolean;
}

export type AppFormErrors = Partial<Record<"port" | "logDays", string>>;

export function formFrom(settings: AppSettings | AppSettingsSaved): AppForm {
  return {
    port: String(settings.port),
    logDays: String(settings.log_retention_days),
    startWithWindows: settings.start_with_windows,
    notifications: settings.notifications,
  };
}

/** A whole number written with digits only (no sign, no decimal point, no exponent), or null. */
function wholeNumber(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[0-9]{1,6}$/.test(trimmed)) return null;
  return Number(trimmed);
}

export function inRange(text: string, min: number, max: number): number | null {
  const value = wholeNumber(text);
  return value !== null && value >= min && value <= max ? value : null;
}

/**
 * The PUT body, or the errors to show. `theme` is the tab's current theme (applied and saved by itself, so this sends
 * the same). Start with Windows is sent as it is stored when the switch is locked (a development copy), so a save
 * there never changes it.
 */
export function checkAppForm(
  form: AppForm,
  theme: ThemePreference,
  stored: AppSettings,
): { values: AppSettingsValues; errors: null } | { values: null; errors: AppFormErrors } {
  const port = inRange(form.port, PORT_MIN, PORT_MAX);
  const days = inRange(form.logDays, LOG_DAYS_MIN, LOG_DAYS_MAX);
  const errors: AppFormErrors = {};
  if (port === null) errors.port = A.portLimit(PORT_MIN, PORT_MAX);
  if (days === null) errors.logDays = A.logsLimit(LOG_DAYS_MIN, LOG_DAYS_MAX);
  if (port === null || days === null) return { values: null, errors };
  return {
    values: {
      port,
      log_retention_days: days,
      theme,
      start_with_windows: stored.installed ? form.startWithWindows : stored.start_with_windows,
      notifications: form.notifications,
    },
    errors: null,
  };
}

/** The lines after a save (SET-06): what was saved, the port's restart, and what Start with Windows did. */
export function savedLine(saved: AppSettingsSaved): { tone: "success" | "warning"; text: string; note: string | null } {
  const port = saved.restart_needed ? A.portNext : null;
  if (saved.start_with_windows_result === "failed") return { tone: "warning", text: A.savedNotApplied, note: port };
  const note = saved.start_with_windows_result === "not_installed" ? A.startDevelopment : null;
  return { tone: "success", text: port ? `${A.saved} ${port}` : A.saved, note };
}
