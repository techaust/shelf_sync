// The typed calls of Settings › Updates and Settings › App (UI-SET; SYS-06, SYS-07, SET-04, SET-06, LOG-01). Every
// body and answer is a type from the generated OpenAPI schema (schema.d.ts), and every call goes through the one API
// client, which adds what the guard needs to each write (X-ShelfSync: 1; the browser adds Origin). The GitHub token
// goes out in one PUT body and is never read back: the API answers only whether one is saved and its expiry.

import type { ApiClient } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Updates = Schemas["UpdatesResponse"];
export type LastCheck = Schemas["LastCheckModel"];
export type SwitchResult = Schemas["ResultModel"];
export type AppSettings = Schemas["AppSettingsResponse"];
export type AppSettingsValues = Schemas["AppSettingsValues"];
export type AppSettingsSaved = Schemas["AppSettingsSaved"];
export type Health = Schemas["HealthResponse"];
type Accepted = Schemas["AcceptedResponse"];
type RollbackRequest = Schemas["RollbackRequest"];
type GithubTokenRequest = Schemas["GithubTokenRequest"];

export const UPDATES_PATH = "/api/updates";
export const GITHUB_TOKEN_PATH = "/api/secrets/github-token";
export const APP_SETTINGS_PATH = "/api/settings/app";
export const RESET_TOKEN_PATH = "/api/session/reset-token";
export const HEALTH_PATH = "/api/health";

export const UPDATES_QUERY_KEY = ["settings", "updates"] as const;
export const APP_SETTINGS_QUERY_KEY = ["settings", "app"] as const;

export const getUpdates = (api: ApiClient) => api.get<Updates>(UPDATES_PATH);
export const checkForUpdates = (api: ApiClient) => api.send<Accepted>("POST", `${UPDATES_PATH}/check`);
/** Slow on purpose: the server hashes the whole version folder before it answers 202 (m1b.2 section 6). */
export const installUpdate = (api: ApiClient) => api.send<Accepted>("POST", `${UPDATES_PATH}/install`);
export function rollBack(api: ApiClient, confirmDataLoss: boolean) {
  const body: RollbackRequest = { confirm_data_loss: confirmDataLoss };
  return api.send<Accepted>("POST", `${UPDATES_PATH}/rollback`, body);
}

export function saveGithubToken(api: ApiClient, value: string) {
  const body: GithubTokenRequest = { value };
  return api.send("PUT", GITHUB_TOKEN_PATH, body);
}
export const removeGithubToken = (api: ApiClient) => api.send("DELETE", GITHUB_TOKEN_PATH);

export const getAppSettings = (api: ApiClient) => api.get<AppSettings>(APP_SETTINGS_PATH);
export const saveAppSettings = (api: ApiClient, values: AppSettingsValues) =>
  api.send<AppSettingsSaved>("PUT", APP_SETTINGS_PATH, values);
export const resetAccessToken = (api: ApiClient) => api.send("POST", RESET_TOKEN_PATH);

export const getHealth = (api: ApiClient) => api.get<Health>(HEALTH_PATH);

/** The five saved values of a GET or PUT answer, as a PUT body (unknown fields are refused by the API). */
export function valuesOf(settings: AppSettingsValues): AppSettingsValues {
  return {
    port: settings.port,
    theme: settings.theme,
    start_with_windows: settings.start_with_windows,
    notifications: settings.notifications,
    log_retention_days: settings.log_retention_days,
  };
}
