// The Settings pages' actions as plain functions (review item 10): each takes the API client (or the writer, or the
// session store) and returns the line to show, so every answer, refusal and silence is tested with fake answers
// (actions.test.ts). The pages only call them and show the result.

import { type ApiClient, ApiError } from "../../api/client";
import type { SessionStore } from "../../api/session";
import {
  type AppSettingsValues,
  checkForUpdates,
  getHealth,
  removeGithubToken,
  resetAccessToken,
  saveGithubToken,
  sessionCheck,
  UPDATES_PATH,
} from "../../api/settings";
import type { SettingsWriter } from "../../api/settingsWriter";
import type { AppResult } from "./AppView";
import { savedLine } from "./forms";
import type { PollAnswers, SwitchLine } from "./switchStore";
import { A, T, updatesActionError, updatesActionTone } from "./wording";

/** What the restart poll asks, through the one API client. */
export function pollAnswers(api: ApiClient): PollAnswers {
  return {
    health: (signal) => getHealth(api, signal),
    session: (signal) => sessionCheck(api, signal),
    stillSwitching: async (signal) => {
      const response = await api.request("GET", UPDATES_PATH, undefined, signal);
      if (!response.ok) throw new Error("no status");
      return ((await response.json()) as { busy?: unknown }).busy === true;
    },
  };
}

/** Check now: null when it started (202); otherwise its line, in its tone. */
export async function checkNow(api: ApiClient): Promise<SwitchLine | null> {
  try {
    await checkForUpdates(api);
    return null;
  } catch (failure) {
    const code = failure instanceof ApiError ? failure.code : null;
    const status = failure instanceof ApiError ? failure.status : null;
    return { tone: updatesActionTone(code), text: updatesActionError(code, status) };
  }
}

/** Saves the GitHub token; rejects with the line to show next to the field. */
export async function saveToken(api: ApiClient, value: string): Promise<void> {
  try {
    await saveGithubToken(api, value);
  } catch (failure) {
    if (failure instanceof ApiError && failure.code === "invalid_request") throw new Error(T.refused);
    if (failure instanceof ApiError) throw new Error(updatesActionError(failure.code, failure.status));
    throw new Error(T.saveFailed);
  }
}

export async function removeToken(api: ApiClient): Promise<void> {
  try {
    await removeGithubToken(api);
  } catch (failure) {
    throw new Error(failure instanceof ApiError ? updatesActionError(failure.code, failure.status) : T.removeFailed);
  }
}

/** Reset access token: on 204 this tab is signed out (the session store shows it); otherwise the line to show. */
export async function resetAccess(api: ApiClient, session: SessionStore): Promise<string | null> {
  try {
    await resetAccessToken(api);
  } catch (failure) {
    return failure instanceof ApiError ? A.resetRefused(failure.status) : A.resetFailed;
  }
  session.set({ kind: "signed_out" });
  return null;
}

/** Save app: what was saved (to put back into the form) and the line beside Save. */
export async function saveApp(
  writer: SettingsWriter,
  values: AppSettingsValues,
): Promise<{ saved: Awaited<ReturnType<SettingsWriter["save"]>> | null; result: AppResult }> {
  try {
    const saved = await writer.save(values);
    return { saved, result: savedLine(saved) };
  } catch (failure) {
    const text = failure instanceof ApiError ? A.saveRefused(failure.status) : A.saveFailed;
    return { saved: null, result: { tone: "danger", text, note: null } };
  }
}
