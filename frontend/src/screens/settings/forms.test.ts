// SET-06, LOG-01: the App form's limits are the API's (port 47615-47624, logs 1-365 days), checked before anything is
// sent; SET-04: the GitHub token's shape; the line after a save for each start_with_windows_result.
import { describe, expect, it } from "vitest";
import type { AppSettings, AppSettingsSaved } from "../../api/settings";
import {
  checkAppForm,
  checkGithubToken,
  formFrom,
  inRange,
  LOG_DAYS_MAX,
  LOG_DAYS_MIN,
  PORT_MAX,
  PORT_MIN,
  savedLine,
} from "./forms";
import { A, T } from "./wording";

const stored: AppSettings = {
  port: 47615,
  theme: "system",
  start_with_windows: true,
  notifications: true,
  log_retention_days: 30,
  installed: true,
};

describe("the App form's limits", () => {
  it("are the API's", () => {
    expect([PORT_MIN, PORT_MAX, LOG_DAYS_MIN, LOG_DAYS_MAX]).toEqual([47615, 47624, 1, 365]);
  });

  it.each([
    ["47615", 47615],
    ["47624", 47624],
    [" 47620 ", 47620],
  ])("accepts the port %j", (text, value) => {
    expect(inRange(text, PORT_MIN, PORT_MAX)).toBe(value);
  });

  it.each(["47614", "47625", "", "abc", "47615.5", "4.7615e4", "-47615", "+47615", "0x0BA0F", "4761５"])(
    "refuses the port %j",
    (text) => {
      expect(inRange(text, PORT_MIN, PORT_MAX)).toBeNull();
    },
  );

  it.each([
    ["1", 1],
    ["365", 365],
  ])("accepts %j days", (text, value) => {
    expect(inRange(text, LOG_DAYS_MIN, LOG_DAYS_MAX)).toBe(value);
  });

  it.each(["0", "366", "30 days", "1e2", ""])("refuses %j days", (text) => {
    expect(inRange(text, LOG_DAYS_MIN, LOG_DAYS_MAX)).toBeNull();
  });
});

describe("checkAppForm", () => {
  it("makes the PUT body with the tab's theme", () => {
    const form = { ...formFrom(stored), port: "47616", logDays: "90", notifications: false };
    const result = checkAppForm(form, "dark", stored);
    expect(result.errors).toBeNull();
    expect(result.values).toEqual({
      port: 47616,
      theme: "dark",
      start_with_windows: true,
      notifications: false,
      log_retention_days: 90,
    });
  });

  it("names each field that is out of range, with its limit, and sends nothing", () => {
    const result = checkAppForm({ ...formFrom(stored), port: "8080", logDays: "0" }, "system", stored);
    expect(result.values).toBeNull();
    expect(result.errors).toEqual({
      port: "Use a port from 47615 to 47624.",
      logDays: "Use a number of days from 1 to 365.",
    });
  });

  it("a development copy never changes Start with Windows: the stored value is sent", () => {
    const development = { ...stored, installed: false, start_with_windows: true };
    const form = { ...formFrom(development), startWithWindows: false };
    expect(checkAppForm(form, "system", development).values?.start_with_windows).toBe(true);
  });
});

describe("savedLine", () => {
  const saved = (over: Partial<AppSettingsSaved>): AppSettingsSaved => ({
    port: 47615,
    theme: "system",
    start_with_windows: true,
    notifications: true,
    log_retention_days: 30,
    restart_needed: false,
    start_with_windows_result: "applied",
    ...over,
  });

  it("applied", () => {
    expect(savedLine(saved({}))).toEqual({ tone: "success", text: "Settings saved.", note: null });
  });

  it("applied, with a new port: used after the next start", () => {
    expect(savedLine(saved({ restart_needed: true, port: 47616 }))).toEqual({
      tone: "success",
      text: "Settings saved. The new port is used after the next start.",
      note: null,
    });
  });

  it("failed: saved, but Windows wasn't changed", () => {
    expect(savedLine(saved({ start_with_windows_result: "failed" }))).toEqual({
      tone: "warning",
      text: A.savedNotApplied,
      note: null,
    });
    expect(A.savedNotApplied).toMatch(/^Settings saved, but Windows wasn't changed/);
    expect(savedLine(saved({ start_with_windows_result: "failed", restart_needed: true })).note).toBe(A.portNext);
  });

  it("not_installed: the development-copy reason", () => {
    expect(savedLine(saved({ start_with_windows_result: "not_installed" })).note).toBe(
      "This copy of ShelfSync runs from source, so it can't start with Windows.",
    );
  });
});

describe("checkGithubToken (update/service.py's shape)", () => {
  const body = "A".repeat(20);
  it.each([`github_pat_${body}`, `github_pat_${"a_1".repeat(85)}`])("accepts a fine-grained token", (value) => {
    expect(checkGithubToken(value)).toBeNull();
  });

  it.each([
    "",
    `ghp_${body}`,
    `github_pat_${"A".repeat(19)}`,
    `github_pat_${"A".repeat(256)}`,
    ` github_pat_${body}`,
    `github_pat_${body}-x`,
    `github_pat_${body}\n`,
  ])("refuses %j with the 13 wording", (value) => {
    expect(checkGithubToken(value)).toBe(T.refused);
  });
});
