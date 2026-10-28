// A store's health and Test connection results as the screens say them (SET-01, ERR-01), shared by Settings ›
// Stores and the shell's HealthArea: which kind a store's chip is, and the one line a test answer, a saved health or
// a refused test reads as, in 13's words. Pure, tested in Node (storesModel.test.ts).

import { ApiError } from "../api/client";
import type { Store, StoreHealthModel, StoreTest } from "../api/stores";
import { REASONS_WITH_STATUS, reasonText, S } from "./storesWording";

/** A refused or unanswered Test connection. */
export function testError(failure: unknown): { text: string; tone: "danger" | "info" } {
  if (failure instanceof ApiError) {
    const code = failure.code;
    if (code === "busy") return { text: S.errors.busy, tone: "info" };
    if (code === "keys_missing" || code === "not_found") return { text: S.errors[code], tone: "danger" };
    return { text: S.testRefused(failure.status), tone: "danger" };
  }
  return { text: S.testNoAnswer, tone: "danger" };
}

// ---------- health and test results ----------

export type HealthKind = "connected" | "failed" | "unknown" | "paused";

/** What a store's chip shows: paused wins (a paused store is never shown as failed), then the saved health. */
export function healthKind(store: Pick<Store, "state" | "health">): HealthKind {
  if (store.state === "paused") return "paused";
  if (store.health.state === "connected") return "connected";
  if (store.health.state === "unknown") return "unknown";
  return "failed";
}

export interface ResultLine {
  tone: "success" | "warning" | "danger" | "neutral";
  text: string;
}

type Outcome = Pick<
  StoreTest,
  "state" | "reason" | "http_status" | "latency_ms" | "wc_version" | "downloadable_count"
> & { detail?: string | null; warning?: string | null };

/** The status written into a reason that doesn't name it already: "…blocked the request (HTTP 403)." */
function withStatus(sentence: string, reason: string, status: number | null): string {
  if (
    status === null ||
    status < 300 ||
    REASONS_WITH_STATUS.has(reason) ||
    reason === "redirected" ||
    sentence.includes("HTTP")
  ) {
    return sentence;
  }
  const end = sentence.indexOf(". ");
  const cut = end === -1 ? sentence.length - 1 : end;
  return `${sentence.slice(0, cut)} (HTTP ${status})${sentence.slice(cut)}`;
}

/** The reason of a failed test or health, in 13's words, or the general line. */
export function reasonLine(outcome: Outcome): string {
  const reason = outcome.reason ?? "";
  const words = reasonText(reason, {
    status: outcome.http_status,
    host: outcome.detail ?? null,
    version: outcome.wc_version,
  });
  return words ? withStatus(words, reason, outcome.http_status) : S.testFailedUnknown;
}

/** A test answer, or a saved health, as the one line the card and the popover show. */
export function outcomeLine(outcome: Outcome): ResultLine {
  if (outcome.state === "unknown") return { tone: "neutral", text: S.notTested };
  if (outcome.state !== "connected") return { tone: "danger", text: reasonLine(outcome) };
  const count = outcome.downloadable_count;
  if (outcome.warning === "no_downloadable_products" || count === 0) return { tone: "warning", text: S.noDownloadable };
  const ms = outcome.latency_ms ?? 0;
  if (count === null) return { tone: "success", text: S.connectedOnly(ms) };
  return {
    tone: "success",
    text: outcome.wc_version ? S.connected(ms, outcome.wc_version, count) : S.connectedNoVersion(ms, count),
  };
}

export function healthLine(health: StoreHealthModel): ResultLine {
  return outcomeLine({ ...health, detail: null, warning: null });
}
