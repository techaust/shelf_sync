// UI-SET Updates (SYS-06, SYS-07, SET-04): what Settings › Updates shows for every state GET /api/updates can
// report, with the wording of 13 section 3 (m1b.2's proposed rows), and every API error code's line.
import { describe, expect, it } from "vitest";
import { ERROR_CODES } from "../../api/client";
import type { LastCheck, SwitchResult, Updates } from "../../api/settings";
import { type DateFormat, describeUpdates } from "./updatesModel";
import { checkProblem, lastSwitch, updatesActionError } from "./wording";

/** Dates are shown as "<iso>" so the tests don't depend on the PC's time zone. */
const date: DateFormat = (iso) => (iso ? `<${iso}>` : null);

const base: Updates = {
  development: false,
  key_available: true,
  installed: "0.2.0",
  previous: null,
  can_roll_back: false,
  database_changed: false,
  backup_at: null,
  backup_available: false,
  checking: false,
  busy: false,
  last_check: null,
  available: null,
  token: { set: false, expires_at: null, notice: false },
  last_result: null,
};
const at = "2026-10-28T09:30:00Z";
const ok: LastCheck = { at, outcome: "ok", detail: null };
/** The token's expiry is a day: shown as "[<iso>]"; "now" is fixed, so "in N days" is exact. */
const day: DateFormat = (iso) => (iso ? `[${iso}]` : null);
const NOW = new Date("2026-10-28T09:30:00Z");
const view = (over: Partial<Updates>, phase?: Parameters<typeof describeUpdates>[1]) =>
  describeUpdates({ ...base, ...over }, phase, date, day, NOW);

describe("describeUpdates: the states", () => {
  it("empty: never checked, no token; Check now works, nothing else is said", () => {
    const m = view({});
    expect(m.heading).toBe("ShelfSync 0.2.0");
    expect(m.checked).toBeNull();
    expect(m.notices).toEqual([]);
    expect(m.status.kind).toBe("none");
    expect(m.check).toEqual({ enabled: true, running: false, why: null });
    expect(m.install.shown).toBe(false);
    expect(m.rollBack.shown).toBe(false);
    expect(m.token).toEqual({ set: false, expires: null });
  });

  it("up to date: the check's time and the 13 line", () => {
    const m = view({ last_check: ok });
    expect(m.checked).toBe(`Checked <${at}>.`);
    expect(m.status).toEqual({ kind: "up_to_date", text: "ShelfSync 0.2.0 is up to date.", version: "0.2.0" });
  });

  it("no release yet", () => {
    const m = view({ last_check: { at, outcome: "no_release", detail: null } });
    expect(m.status.text).toBe("No release has been published yet.");
    expect(m.notices).toEqual([]);
  });

  it("found, not ready: being downloaded and checked; no Install yet", () => {
    const m = view({ last_check: ok, available: { version: "0.3.0", ready: false } });
    expect(m.status.text).toBe("Version 0.3.0 is being downloaded and checked.");
    expect(m.install.shown).toBe(false);
  });

  it("ready: Install 0.3.0 and restart", () => {
    const m = view({ last_check: ok, available: { version: "0.3.0", ready: true } });
    expect(m.status.text).toBe("Version 0.3.0 is ready to install.");
    expect(m.install).toEqual({ shown: true, enabled: true, version: "0.3.0", why: null });
  });

  it("checking: Check now shows it runs and is off", () => {
    const m = view({ checking: true });
    expect(m.check).toEqual({ enabled: false, running: true, why: null });
  });

  it("development copy: says why, and turns the buttons off", () => {
    const m = view({ development: true, available: { version: "0.3.0", ready: true } });
    expect(m.notices).toEqual([
      {
        key: "development",
        tone: "info",
        title: "This copy of ShelfSync runs from source, so updates are turned off.",
        body: null,
      },
    ]);
    expect(m.check).toEqual({ enabled: false, running: false, why: "development" });
    expect(m.status.kind).toBe("none");
    expect(m.install.enabled).toBe(false);
  });

  it("no key in the build: says why; nothing can be installed", () => {
    const m = view({ key_available: false, last_check: ok, available: { version: "0.3.0", ready: false } });
    expect(m.notices[0]?.title).toBe("This build can't verify updates, so it won't install any.");
    expect(m.status.kind).toBe("none"); // nothing is downloaded without a key, so "being downloaded" would be false
    expect(m.install.shown).toBe(false);
    expect(m.check.enabled).toBe(true);
  });

  it("a ready update in a build without a key can't be installed", () => {
    const m = view({ key_available: false, available: { version: "0.3.0", ready: true } });
    expect(m.install).toEqual({ shown: true, enabled: false, version: "0.3.0", why: "no-key" });
  });

  it("a switch under way: said once, and everything waits", () => {
    const m = view({
      busy: true,
      previous: "0.1.4",
      can_roll_back: true,
      available: { version: "0.3.0", ready: true },
    });
    expect(m.notices.map((n) => n.title)).toEqual(["An update is already under way."]);
    expect(m.check).toEqual({ enabled: false, running: false, why: "busy" });
    expect(m.install.enabled).toBe(false);
    expect(m.rollBack.enabled).toBe(false);
  });

  it("while the page prepares an install, Check now and Roll back wait", () => {
    const ready = {
      last_check: ok,
      available: { version: "0.3.0", ready: true },
      previous: "0.1.4",
      can_roll_back: true,
    };
    const m = view(ready, { kind: "preparing", version: "0.3.0" });
    expect(m.check.enabled).toBe(false);
    expect(m.install.enabled).toBe(false);
    expect(m.rollBack.enabled).toBe(false);
  });

  it("roll back, files only: shown with the previous version", () => {
    const m = view({ previous: "0.1.4", can_roll_back: true });
    expect(m.rollBack).toEqual({
      shown: true,
      enabled: true,
      reason: null,
      previous: "0.1.4",
      from: "0.2.0",
      databaseChanged: false,
      backupDate: null,
    });
  });

  it("the optional-token line: shown with no token, never in a development copy", () => {
    expect(view({}).showEmpty).toBe(true);
    expect(view({ token: { set: true, expires_at: null, notice: false } }).showEmpty).toBe(false);
    expect(view({ development: true }).showEmpty).toBe(false);
  });

  it("roll back with a database change: the backup's date for the dialog", () => {
    const m = view({
      previous: "0.1.4",
      can_roll_back: true,
      database_changed: true,
      backup_at: "2026-10-26T03:00:00Z",
      backup_available: true,
    });
    expect(m.rollBack.databaseChanged).toBe(true);
    expect(m.rollBack.backupDate).toBe("<2026-10-26T03:00:00Z>");
    expect(m.rollBack.enabled).toBe(true);
  });

  it("roll back with a database change but no backup: off, and why", () => {
    const m = view({ previous: "0.1.4", can_roll_back: true, database_changed: true, backup_available: false });
    expect(m.rollBack.enabled).toBe(false);
    expect(m.rollBack.reason).toBe("The backup needed to roll back isn't there.");
  });

  it("the token: saved with its expiry date; the notice from 14 days before replaces it, with 'in N days'", () => {
    const later = view({ token: { set: true, expires_at: "2026-12-29T00:00:00Z", notice: false } });
    expect(later.token).toEqual({ set: true, expires: "[2026-12-29T00:00:00Z]" });
    expect(later.notices).toEqual([]);
    const soon = view({ token: { set: true, expires_at: "2026-11-06T00:00:00Z", notice: true } });
    expect(soon.token.expires).toBeNull();
    expect(soon.notices).toEqual([
      {
        key: "token-expiry",
        tone: "warning",
        title: "Your GitHub token expires in 9 days, on [2026-11-06T00:00:00Z]. Make a new one before then.",
        body: null,
      },
    ]);
    const tomorrow = view({ token: { set: true, expires_at: "2026-10-29T00:00:00Z", notice: true } });
    expect(tomorrow.notices[0]?.title).toContain("expires in 1 day, on");
    const past = view({ token: { set: true, expires_at: "2026-10-27T00:00:00Z", notice: true } });
    expect(past.notices[0]?.title).toBe(
      // lead wording (re-review low 4)
      "Your GitHub token expired on [2026-10-27T00:00:00Z]. Make a new one, or remove it to check without one.",
    );
  });

  it("a good last switch is a quiet line with its time; a bad one is a notice with its time", () => {
    const result: SwitchResult = {
      mode: "install",
      from_version: "0.1.4",
      to_version: "0.2.0",
      outcome: "updated",
      reason: null,
      at,
    };
    expect(view({ last_result: result }).lastChange).toEqual({ text: "Updated to 0.2.0.", at: `<${at}>` });
    const kept = view({
      last_result: { ...result, from_version: "0.2.0", to_version: "0.3.0", outcome: "kept_old", reason: "no_answer" },
    });
    expect(kept.lastChange).toBeNull();
    expect(kept.notices).toEqual([
      {
        key: "last-result",
        tone: "warning",
        title: "0.3.0 didn't start, so 0.2.0 is back.",
        body: "It didn't answer in time.",
        when: `<${at}>`,
      },
    ]);
  });

  it("a refused download says which version, from `available`", () => {
    const m = view({
      last_check: { at, outcome: "update_refused", detail: "signature_invalid" },
      available: { version: "0.3.0", ready: false },
    });
    expect(m.status.kind).toBe("none"); // not "being downloaded": it was refused
    expect(m.notices[0]?.title).toBe(
      "Version 0.3.0 was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed.",
    );
  });
});

describe("13 section 3: Update check results", () => {
  const check = (outcome: LastCheck["outcome"], detail: string | null = null): LastCheck => ({ at, outcome, detail });
  it.each([
    ["token_refused", "danger", "GitHub refused the token. Check it, or remove it to check without one."],
    ["rate_limited", "warning", "GitHub says there were too many checks. Try again later."],
    ["not_public", "warning", "GitHub can't find the project. If it is private, add a read-only token."],
    ["unreachable", "warning", "Couldn't reach GitHub. Check your connection."],
    [
      "update_refused",
      "danger",
      "Version 0.3.0 was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed.",
    ],
    ["update_failed", "warning", "Version 0.3.0 couldn't be downloaded. It will be tried again at the next check."],
  ] as const)("%s", (outcome, tone, title) => {
    expect(checkProblem(check(outcome), "0.3.0")).toEqual({ tone, title, body: null });
  });

  it("ok and no_release are not problems", () => {
    expect(checkProblem(check("ok"), null)).toBeNull();
    expect(checkProblem(check("no_release"), null)).toBeNull();
  });

  it("update_failed with no_space adds the drive line", () => {
    expect(checkProblem(check("update_failed", "no_space"), "0.3.0")?.body).toBe(
      "There isn't enough free space on the drive ShelfSync is installed on.",
    );
  });

  it("with no version known (after a restart) the line still reads", () => {
    expect(checkProblem(check("update_failed"), null)?.title).toBe(
      "An update couldn't be downloaded. It will be tried again at the next check.",
    );
  });
});

describe("13 section 3: Last switch", () => {
  const result = (outcome: SwitchResult["outcome"], reason: string | null = null): SwitchResult => ({
    mode: "install",
    from_version: "0.2.0",
    to_version: "0.3.0",
    outcome,
    reason,
    at,
  });
  it("updated, rolled back, failed", () => {
    expect(lastSwitch(result("updated"))).toEqual({ tone: "success", title: "Updated to 0.3.0.", body: null });
    expect(lastSwitch({ ...result("rolled_back"), to_version: "0.1.4" }).title).toBe("Rolled back to 0.1.4.");
    expect(lastSwitch(result("failed")).title).toBe(
      "Neither version started. Open ShelfSync from the Start menu; the log has the reason.",
    );
  });

  it.each([
    ["no_answer", "It didn't answer in time."],
    ["wrong_version", "It reported the wrong version."],
    ["untrusted_listener", "Something else was answering on ShelfSync's address."],
    ["exited", "It stopped while starting."],
    ["migration_failed", "Its database update failed and was undone."],
  ])("kept_old + %s", (reason, body) => {
    expect(lastSwitch(result("kept_old", reason))).toEqual({
      tone: "warning",
      title: "0.3.0 didn't start, so 0.2.0 is back.",
      body,
    });
  });

  it.each([
    ["old_copy_still_running", "ShelfSync didn't close in time."],
    ["old_process_mismatch", "The program that was running wasn't this version of ShelfSync."],
    ["lock_busy", "Another copy of ShelfSync was starting."],
    ["files_changed", "The files of 0.3.0 no longer match what was signed."],
    ["manifest_missing", "The signature of 0.3.0 can't be checked."],
    ["manifest_invalid", "The signature of 0.3.0 can't be checked."],
    ["backup_failed", "A copy of the current data couldn't be made, so the roll back was refused."],
    ["backup_missing", "The backup needed to roll back isn't there."],
    ["backup_mismatch", "The backup needed to roll back isn't there."],
    ["database_changed", "The database changed since you confirmed. Try again."],
  ])("not_switched + %s", (reason, body) => {
    expect(lastSwitch(result("not_switched", reason))).toEqual({
      tone: "warning",
      title: "Nothing was changed.",
      body,
    });
  });

  it("a joined reason is read by its first code; a code without wording shows no reason (never echoed)", () => {
    expect(lastSwitch(result("kept_old", "no_answer+restore_failed")).body).toBe("It didn't answer in time.");
    expect(lastSwitch(result("not_switched", "old_copy_hung")).body).toBeNull();
    expect(lastSwitch(result("not_switched", "<script>")).body).toBeNull();
    expect(lastSwitch(result("not_switched", "constructor")).body).toBeNull();
  });
});

describe("13 section 3: Updates API errors", () => {
  it.each([
    ["development_build", "Updates are turned off in this copy."],
    ["busy", "An update is already under way."],
    ["no_key", "This build can't verify updates."],
    ["nothing_to_install", "There's no downloaded update to install."],
    ["no_previous", "There's no earlier version to roll back to."],
    ["no_backup", "The backup needed to roll back isn't there, so the roll back was refused."],
    ["files_changed", "The files of that version changed on disk, so it was refused."],
    ["manifest_invalid", "That version's signature can't be checked, so it was refused."],
    ["manifest_missing", "That version's signature can't be checked, so it was refused."],
    ["cannot_restart", "ShelfSync couldn't close itself to restart, so nothing was changed."],
    ["too_soon", "A check ran a moment ago. Try again in a minute."],
  ] as const)("%s", (code, text) => {
    expect(updatesActionError(code, 409)).toBe(text);
  });

  it("every other code, and no answer at all, has a general line with no detail from the request", () => {
    for (const code of ERROR_CODES) expect(updatesActionError(code, 500)).toMatch(/\S/);
    expect(updatesActionError("internal", 500)).toBe("ShelfSync refused that (HTTP 500), so nothing was changed.");
    // no answer is never stated as an outcome (lead wording, review item 16)
    expect(updatesActionError(null, null)).toBe(
      "ShelfSync didn't answer, so that may not have happened. Reload this page to check.",
    );
  });
});
