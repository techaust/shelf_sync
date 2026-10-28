// Writes of the App settings (SET-06), one at a time. The API takes all five values in each PUT, so a theme chosen in
// the app bar and a Save on Settings › App must never overlap: each waits for the one before it. A theme change
// sends the five values as they are stored now (a fresh GET), with only the theme changed, so it never saves a field
// the owner is still editing on Settings › App.

import type { ThemePreference } from "../theme/theme";
import type { ApiClient } from "./client";
import { type AppSettingsSaved, type AppSettingsValues, getAppSettings, saveAppSettings, valuesOf } from "./settings";

export interface SettingsWriter {
  saveTheme(theme: ThemePreference): Promise<AppSettingsSaved>;
  save(values: AppSettingsValues): Promise<AppSettingsSaved>;
}

export function createSettingsWriter(api: ApiClient): SettingsWriter {
  let last: Promise<unknown> = Promise.resolve();
  function queue<T>(work: () => Promise<T>): Promise<T> {
    const next = last.then(work, work);
    last = next.catch(() => undefined);
    return next;
  }
  return {
    saveTheme: (theme) =>
      queue(async () => {
        const stored = await getAppSettings(api);
        return saveAppSettings(api, { ...valuesOf(stored), theme });
      }),
    save: (values) => queue(() => saveAppSettings(api, valuesOf(values))),
  };
}

const writers = new WeakMap<ApiClient, SettingsWriter>();

/** The tab's one writer for this client. */
export function settingsWriter(api: ApiClient): SettingsWriter {
  let writer = writers.get(api);
  if (!writer) {
    writer = createSettingsWriter(api);
    writers.set(api, writer);
  }
  return writer;
}
