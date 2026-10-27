// What Settings › Updates shows for a GET /api/updates answer (SYS-06, SYS-07, SET-04): a pure function, so every
// state the API can report is tested without a browser (updatesModel.test.ts). Wording is in wording.ts.

import type { Updates } from "../../api/settings";
import { formatDateTime, parseUtc } from "../../lib/time";
import { checkedAt, checkProblem, lastSwitch, NO_RELEASE, T, U } from "./wording";

export type Tone = "info" | "success" | "warning" | "danger";

export interface Notice {
  key: string;
  tone: Tone;
  title: string;
  body: string | null;
  /** When it happened, for a result that stays until the next switch. */
  when?: string | null;
}

/** What the page is doing on its own, between a confirmed Install or Roll back and the reload. */
export type Phase =
  | { kind: "idle" }
  | { kind: "preparing"; version: string } // the install request runs: the server checks the files first
  | { kind: "rolling_back"; version: string }
  | { kind: "restarting"; version: string; late: boolean };

export type StatusKind = "ready" | "downloading" | "up_to_date" | "no_release" | "none";

export interface UpdatesModel {
  heading: string;
  checked: string | null;
  notices: Notice[];
  /** The last switch when it went well, and when (a problem is a notice instead). */
  lastChange: { text: string; at: string | null } | null;
  status: { kind: StatusKind; text: string | null; version: string | null };
  /** `why`: the notice that says why Check now is off (its key), if one does. */
  check: { enabled: boolean; running: boolean; why: string | null };
  install: { shown: boolean; enabled: boolean; version: string | null };
  rollBack: {
    shown: boolean;
    enabled: boolean;
    reason: string | null;
    previous: string | null;
    databaseChanged: boolean;
    backupDate: string | null;
  };
  token: { set: boolean; expires: string | null };
}

export type DateFormat = (iso: string | null | undefined) => string | null;

export const localDate: DateFormat = (iso) => {
  const at = parseUtc(iso);
  return at ? formatDateTime(at) : null;
};

export function describeUpdates(u: Updates, phase: Phase = { kind: "idle" }, date: DateFormat = localDate) {
  const idle = phase.kind === "idle";
  const notices: Notice[] = [];
  if (u.development) notices.push({ key: "development", tone: "info", title: U.development, body: null });
  else if (!u.key_available) notices.push({ key: "no-key", tone: "info", title: U.noKey, body: null });
  if (u.busy && idle) notices.push({ key: "busy", tone: "info", title: "An update is already under way.", body: null });

  let lastChange: UpdatesModel["lastChange"] = null;
  if (u.last_result) {
    const line = lastSwitch(u.last_result);
    if (line.tone === "success") lastChange = { text: line.title, at: date(u.last_result.at) };
    else
      notices.push({
        key: "last-result",
        tone: line.tone,
        title: line.title,
        body: line.body,
        when: date(u.last_result.at),
      });
  }

  const available = u.available;
  const problem = u.last_check ? checkProblem(u.last_check, available?.version ?? null) : null;
  if (problem) notices.push({ key: "last-check", ...problem });

  const expiry = date(u.token.expires_at);
  if (u.token.set && u.token.notice && expiry) {
    notices.push({ key: "token-expiry", tone: "warning", title: T.expires(expiry), body: null });
  }

  let status: UpdatesModel["status"] = { kind: "none", text: null, version: null };
  if (!u.development) {
    if (available?.ready) status = { kind: "ready", text: U.ready(available.version), version: available.version };
    else if (available && u.key_available && !problem)
      status = { kind: "downloading", text: U.downloading(available.version), version: available.version };
    else if (!available && u.last_check?.outcome === "ok")
      status = { kind: "up_to_date", text: U.upToDate(u.installed), version: u.installed };
    else if (!available && u.last_check?.outcome === "no_release")
      status = { kind: "no_release", text: NO_RELEASE, version: null };
  }

  const lockedOut = u.development || u.busy || !idle;
  const noBackup = u.database_changed && !u.backup_available;
  const checked = date(u.last_check?.at);
  return {
    heading: U.heading(u.installed),
    checked: checked ? checkedAt(checked) : null,
    notices,
    lastChange,
    status,
    check: {
      enabled: !lockedOut && !u.checking,
      running: u.checking,
      why: u.development ? "development" : u.busy && idle ? "busy" : null,
    },
    install: {
      shown: status.kind === "ready",
      enabled: status.kind === "ready" && u.key_available && !lockedOut,
      version: status.kind === "ready" ? status.version : null,
    },
    rollBack: {
      shown: u.previous !== null,
      enabled: u.previous !== null && u.can_roll_back && !lockedOut && !noBackup,
      reason: u.previous !== null && noBackup ? U.rollBackNoBackup : null,
      previous: u.previous,
      databaseChanged: u.database_changed,
      backupDate: date(u.backup_at),
    },
    // the expiry beside "Saved", unless the notice at the top already says it
    token: { set: u.token.set, expires: u.token.set && !u.token.notice ? expiry : null },
  } satisfies UpdatesModel;
}
