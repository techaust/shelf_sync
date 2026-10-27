// UI-SET: the Settings calls go through the one API client, so every write carries what the guard needs, and the
// bodies are the schema's. The GitHub token is sent once, in a PUT body, and never read back. The App settings
// writes are one at a time, and a theme change sends the stored values with only the theme changed (SET-06).
import { describe, expect, it, vi } from "vitest";
import { createThemeStore } from "../theme/useTheme";
import { CSRF_HEADER, createApiClient } from "./client";
import {
  type AppSettings,
  checkForUpdates,
  getUpdates,
  installUpdate,
  removeGithubToken,
  resetAccessToken,
  rollBack,
  saveAppSettings,
  saveGithubToken,
} from "./settings";
import { createSettingsWriter } from "./settingsWriter";

interface Sent {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}

function recordingClient(
  answer: (sent: Sent) => Response | Promise<Response> = () => new Response(null, { status: 204 }),
) {
  const sent: Sent[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const record: Sent = {
      method: init?.method ?? "GET",
      path: String(input),
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    };
    sent.push(record);
    return answer(record);
  });
  return { api: createApiClient({ fetch: fetch as unknown as typeof globalThis.fetch }), sent };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const stored: AppSettings = {
  port: 47616,
  theme: "system",
  start_with_windows: false,
  notifications: true,
  log_retention_days: 60,
  installed: true,
};

describe("the Settings calls", () => {
  it("each write carries X-ShelfSync: 1; the read doesn't", async () => {
    const { api, sent } = recordingClient((s) => (s.method === "GET" ? json({}) : json({ accepted: true }, 202)));
    await getUpdates(api);
    await checkForUpdates(api);
    await installUpdate(api);
    await rollBack(api, true);
    await saveGithubToken(api, "github_pat_SAMPLEONLY_not_a_real_token_0000");
    await removeGithubToken(api);
    await resetAccessToken(api);
    expect(sent.map((s) => `${s.method} ${s.path}`)).toEqual([
      "GET /api/updates",
      "POST /api/updates/check",
      "POST /api/updates/install",
      "POST /api/updates/rollback",
      "PUT /api/secrets/github-token",
      "DELETE /api/secrets/github-token",
      "POST /api/session/reset-token",
    ]);
    expect(sent[0]?.headers[CSRF_HEADER]).toBeUndefined();
    for (const write of sent.slice(1)) expect(write.headers[CSRF_HEADER]).toBe("1");
  });

  it("roll back sends what confirm_required asks for", async () => {
    const { api, sent } = recordingClient(() => json({ accepted: true }, 202));
    await rollBack(api, false);
    await rollBack(api, true);
    expect(sent.map((s) => s.body)).toEqual([{ confirm_data_loss: false }, { confirm_data_loss: true }]);
  });

  it("the token goes out only in the PUT body", async () => {
    const { api, sent } = recordingClient();
    const value = "github_pat_SAMPLEONLY_not_a_real_token_0000";
    await saveGithubToken(api, value);
    expect(sent[0]?.body).toEqual({ value });
    expect(sent[0]?.path).not.toContain("github_pat_");
  });

  it("an App save sends the five values only (unknown fields are refused by the API)", async () => {
    const { api, sent } = recordingClient(() => json({}));
    await saveAppSettings(api, { ...stored, installed: true } as never);
    expect(sent[0]?.body).toEqual(stored);
    const writer = createSettingsWriter(api);
    await writer.save({ ...stored, restart_needed: true } as never);
    expect(Object.keys(sent[1]?.body as object).sort()).toEqual([
      "log_retention_days",
      "notifications",
      "port",
      "start_with_windows",
      "theme",
    ]);
  });
});

describe("the settings writer", () => {
  it("a theme change saves the stored values with only the theme changed", async () => {
    const { api, sent } = recordingClient((s) =>
      s.method === "GET" ? json(stored) : json({ ...stored, theme: "dark" }),
    );
    await createSettingsWriter(api).saveTheme("dark");
    expect(sent.map((s) => s.method)).toEqual(["GET", "PUT"]);
    expect(sent[1]?.body).toEqual({
      port: 47616,
      theme: "dark",
      start_with_windows: false,
      notifications: true,
      log_retention_days: 60,
    });
  });

  it("writes never overlap, and a failed one doesn't stop the next", async () => {
    const order: string[] = [];
    let release: () => void = () => undefined;
    const { api } = recordingClient(async (s) => {
      order.push(`start ${s.method} ${JSON.stringify(s.body ?? null)}`);
      if (s.method === "PUT" && (s.body as { port: number }).port === 47615) {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        order.push("end first");
        return new Response(null, { status: 500 });
      }
      return json(s.method === "GET" ? stored : s.body);
    });
    const writer = createSettingsWriter(api);
    const first = writer.save({ ...stored, port: 47615 });
    const second = writer.saveTheme("light");
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(order).toHaveLength(1); // the theme waits for the save
    release();
    await expect(first).rejects.toThrow();
    await expect(second).resolves.toBeTruthy();
    expect(order[1]).toBe("end first");
    expect(order[2]).toMatch(/^start GET/);
    expect(order[3]).toMatch(/^start PUT .*"theme":"light"/);
  });
});

describe("the tab's one theme (shared by the app bar and Settings › App)", () => {
  function host() {
    const root = { dataset: {} as DOMStringMap };
    const data = new Map<string, string>();
    return {
      root,
      data,
      host: {
        storage: () => ({
          getItem: (k: string) => data.get(k) ?? null,
          setItem: (k: string, v: string) => void data.set(k, v),
          removeItem: (k: string) => void data.delete(k),
        }),
        prefersDark: () => false,
        root: () => root,
      },
    };
  }

  it("one store: a choice from either place is seen by every listener, applied and kept", () => {
    const h = host();
    const store = createThemeStore(h.host);
    const appBar = vi.fn();
    const appPage = vi.fn();
    store.subscribe(appBar);
    store.subscribe(appPage);
    expect(store.get()).toBe("system");
    store.set("dark");
    expect(store.get()).toBe("dark");
    expect(h.root.dataset.theme).toBe("dark");
    expect(h.data.get("shelfsync.theme")).toBe("dark");
    expect(appBar).toHaveBeenCalledTimes(1);
    expect(appPage).toHaveBeenCalledTimes(1);
    store.set("dark"); // the same again: applied, nobody told twice
    expect(appBar).toHaveBeenCalledTimes(1);
    store.set("system");
    expect(h.root.dataset.theme).toBeUndefined();
    expect(h.data.has("shelfsync.theme")).toBe(false);
  });
});
