// UI-SET: the Settings actions as plain functions with fake answers (review item 10): Check now, the token's save and
// remove, Reset access token, Save app, the restart poll's questions; SecretField's Save (emptied after a save, kept
// after a failure); the theme's server sync while a choice is still saving (review item 4); the roll back words.
import { describe, expect, it, vi } from "vitest";
import { type ApiClient, createApiClient } from "../../api/client";
import { createSessionStore } from "../../api/session";
import type { AppSettingsSaved } from "../../api/settings";
import type { SettingsWriter } from "../../api/settingsWriter";
import { submitSecret } from "../../components/SecretField";
import { createThemeSync } from "../../theme/useSavedTheme";
import { checkNow, pollAnswers, removeToken, resetAccess, saveApp, saveToken } from "./actions";
import { rollBackWords } from "./UpdatesView";
import type { UpdatesModel } from "./updatesModel";
import { A, T } from "./wording";

/** An API client over a fake fetch: a status and body, or "no answer". */
function client(answer: number | "none", body: unknown = null): ApiClient {
  return createApiClient({
    fetch: (async () => {
      if (answer === "none") throw new TypeError("Failed to fetch");
      const text = body === null ? null : JSON.stringify(body);
      return new Response(answer === 204 ? null : text, {
        status: answer,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch,
  });
}

describe("Check now", () => {
  it("202 is no line; a 429 too_soon its 13 line; busy is information; no answer says it may not have happened", async () => {
    expect(await checkNow(client(202, { accepted: true }))).toBeNull();
    expect(await checkNow(client(429, { error: "too_soon" }))).toEqual({
      tone: "danger",
      text: "A check ran a moment ago. Try again in a minute.",
    });
    expect(await checkNow(client(409, { error: "busy" }))).toEqual({
      tone: "info",
      text: "An update is already under way.",
    });
    expect(await checkNow(client("none"))).toEqual({
      tone: "danger",
      text: "ShelfSync didn't answer, so that may not have happened. Reload this page to check.",
    });
  });
});

describe("the GitHub token", () => {
  it("save: 204 resolves; 422 is the shape refusal; no answer says it may not have been saved", async () => {
    await expect(saveToken(client(204), "github_pat_x")).resolves.toBeUndefined();
    await expect(saveToken(client(422, { error: "invalid_request" }), "x")).rejects.toThrow(T.refused);
    await expect(saveToken(client("none"), "x")).rejects.toThrow(T.saveFailed);
    expect(T.saveFailed).toBe(
      "ShelfSync didn't answer, so the token may not have been saved. Reload this page to check.",
    );
  });

  it("remove: no answer says it may not have been removed", async () => {
    await expect(removeToken(client(204))).resolves.toBeUndefined();
    await expect(removeToken(client("none"))).rejects.toThrow(T.removeFailed);
  });

  it("SecretField's Save empties the input only after the save is accepted, and keeps it after a failure", async () => {
    const field = { value: "github_pat_SAMPLEONLY_not_a_real_token_0000" };
    const fails = await submitSecret(
      field,
      () => null,
      () => Promise.reject(new Error(T.saveFailed)),
    );
    expect(fails).toEqual({ saved: false, error: T.saveFailed });
    expect(field.value).toBe("github_pat_SAMPLEONLY_not_a_real_token_0000");
    const refused = await submitSecret(field, () => T.refused, vi.fn());
    expect(refused.error).toBe(T.refused);
    expect(field.value).not.toBe("");
    const onSave = vi.fn(async () => undefined);
    const ok = await submitSecret(field, () => null, onSave);
    expect(ok).toEqual({ saved: true, error: null });
    expect(onSave).toHaveBeenCalledWith("github_pat_SAMPLEONLY_not_a_real_token_0000");
    expect(field.value).toBe("");
  });
});

describe("Reset access token", () => {
  it("204 signs this tab out through the session store", async () => {
    const session = createSessionStore({ kind: "signed_in" });
    expect(await resetAccess(client(204), session)).toBeNull();
    expect(session.get()).toEqual({ kind: "signed_out" });
  });

  it("no answer or a refusal keeps the tab signed in and says so", async () => {
    const session = createSessionStore({ kind: "signed_in" });
    expect(await resetAccess(client("none"), session)).toBe(
      "ShelfSync didn't answer, so the reset may not have happened. Reload this page to check.",
    );
    expect(await resetAccess(client(500, { error: "internal" }), session)).toBe(A.resetRefused(500));
    expect(session.get()).toEqual({ kind: "signed_in" });
  });
});

describe("Save app", () => {
  const values = {
    port: 47615,
    theme: "system" as const,
    start_with_windows: true,
    notifications: true,
    log_retention_days: 30,
  };
  const writer = (save: SettingsWriter["save"]): SettingsWriter => ({ save, saveTheme: vi.fn() });

  it("an answer: what was saved and its line", async () => {
    const saved: AppSettingsSaved = { ...values, restart_needed: false, start_with_windows_result: "failed" };
    expect(
      await saveApp(
        writer(async () => saved),
        values,
      ),
    ).toEqual({
      saved,
      result: { tone: "warning", text: A.savedNotApplied, note: null },
    });
  });

  it("no answer: may not have been saved; nothing goes back into the form", async () => {
    const result = await saveApp(
      writer(() => Promise.reject(new TypeError("no answer"))),
      values,
    );
    expect(result).toEqual({
      saved: null,
      result: {
        tone: "danger",
        text: "ShelfSync didn't answer, so the settings may not have been saved. Reload this page to check.",
        note: null,
      },
    });
  });
});

describe("the restart poll's questions", () => {
  it("stillSwitching reads busy from GET /api/updates; the session check reads 204 and 401", async () => {
    expect(await pollAnswers(client(200, { busy: true })).stillSwitching(new AbortController().signal)).toBe(true);
    expect(await pollAnswers(client(200, { busy: false })).stillSwitching(new AbortController().signal)).toBe(false);
    expect(await pollAnswers(client(204)).session(new AbortController().signal)).toBe("signed_in");
    expect(await pollAnswers(client(401, { error: "signed_out" })).session(new AbortController().signal)).toBe(
      "signed_out",
    );
    expect(await pollAnswers(client("none")).session(new AbortController().signal)).toBe("unknown");
  });

  it("a 401 from the session check never signs this tab out by itself", async () => {
    const onSignedOut = vi.fn();
    const api = createApiClient({
      fetch: (async () =>
        new Response(JSON.stringify({ error: "signed_out" }), { status: 401 })) as unknown as typeof fetch,
      onSignedOut,
    });
    expect(await pollAnswers(api).session(new AbortController().signal)).toBe("signed_out");
    expect(onSignedOut).not.toHaveBeenCalled();
  });
});

describe("the saved theme while a choice is still being saved (useThemeFromServer)", () => {
  it("an older save's answer never puts an older theme back: light, system, light, system", () => {
    const set = vi.fn();
    const sync = createThemeSync({ set });
    const ends = ["light", "system", "light", "system"].map(() => sync.begin());
    // the saves answer in order; each answer goes into the cache, so the server theme arrives each time
    for (const [i, theme] of ["light", "system", "light"].entries()) {
      ends[i]?.();
      expect(sync.fromServer(theme as "light" | "system")).toBe(false);
    }
    ends[3]?.();
    expect(sync.fromServer("system")).toBe(true);
    expect(set.mock.calls).toEqual([["system"]]);
  });

  it("with nothing pending the saved theme applies (a page load, another tab's choice)", () => {
    const set = vi.fn();
    const sync = createThemeSync({ set });
    expect(sync.fromServer("dark")).toBe(true);
    expect(set).toHaveBeenCalledWith("dark");
    const end = sync.begin();
    end();
    end(); // ending twice counts once
    expect(sync.pending()).toBe(0);
  });
});

describe("the roll back words (13 §6, the owner's decision)", () => {
  const rollBack = (over: Partial<UpdatesModel["rollBack"]>): UpdatesModel["rollBack"] => ({
    shown: true,
    enabled: true,
    reason: null,
    previous: "0.1.4",
    from: "0.2.0",
    databaseChanged: false,
    backupDate: null,
    ...over,
  });

  it("database unchanged", () => {
    expect(rollBackWords(rollBack({}))).toEqual({
      database: false,
      text: "0.2.0 didn't change the database, so your data stays as it is. You can install 0.2.0 again from Settings › Updates.",
      copyKept: null,
    });
  });

  it("database changed, with the backup's date", () => {
    expect(
      rollBackWords(rollBack({ databaseChanged: true, backupDate: "26 October 2026 at 03:13 India Standard Time" })),
    ).toEqual({
      database: true,
      text: "0.2.0 changed the database. ShelfSync restores the backup taken just before the update, on 26 October 2026 at 03:13 India Standard Time. Changes made since then are lost and can't be brought back. You can install 0.2.0 again from Settings › Updates.",
      copyKept: "A copy of the current data is kept in the backups folder.",
    });
  });

  it("database changed, no date known: the line without it, and never 'your data stays as it is'", () => {
    const words = rollBackWords(rollBack({ databaseChanged: true, backupDate: null }));
    expect(words.text).toBe(
      "0.2.0 changed the database. ShelfSync restores the backup taken just before the update. Changes made since then are lost and can't be brought back. You can install 0.2.0 again from Settings › Updates.",
    );
    expect(words.text).not.toContain("stays as it is");
  });
});
