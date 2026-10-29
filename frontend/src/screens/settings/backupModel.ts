// Settings › Backup without React (SET-05, BAK-01): the keep settings' checks (the API's limits, db/settings.py), what
// the daily backups' facts say, the passphrase rule, the export's and the import's lines for every answer, and the
// import's checks before anything is sent (the 1 MiB cap, the file's own `encryption` field). Pure, so every rule
// is tested in Node (backupModel.test.ts).

import type { BackupSettings, BackupSettingsValues, ImportResult, LeftOut } from "../../api/backup";
import { ApiError } from "../../api/client";
import type { WhenFormat } from "../../lib/time";
import { B } from "./backupWording";
import { inRange } from "./forms";

/** db/settings.py BACKUPS_KEPT_MIN/MAX and SNAPSHOT_DAYS_MIN/MAX. */
export const KEPT_MIN = 1;
export const KEPT_MAX = 30;
export const SNAPSHOT_MIN = 1;
export const SNAPSHOT_MAX = 365;
/** secure/backup_crypto.py PASSPHRASE_MIN/MAX (counted after NFC, in code points, as Python's len does). */
export const PASSPHRASE_MIN = 12;
export const PASSPHRASE_MAX = 1024;
/** The input's own cap: the API takes up to 4 × 1024 typed characters (the NFC form can be shorter). */
export const PASSPHRASE_INPUT_MAX = 4096;
/** 11, 2026-10-29: a v1 backup file is at most 1 MiB of text (MAX_FILE_CHARS); a real one is tens of KiB. */
export const MAX_FILE_BYTES = 1024 * 1024;

export type Tone = "info" | "success" | "warning" | "danger";
export interface Line {
  tone: Tone;
  text: string;
}

// ---------- the keep settings ----------

export interface KeepForm {
  kept: string;
  snapshots: string;
}
export type KeepErrors = Partial<Record<keyof KeepForm, string>>;

export function keepFormFrom(values: BackupSettingsValues): KeepForm {
  return { kept: String(values.db_backups_kept), snapshots: String(values.snapshot_retention_days) };
}

export function checkKeepForm(
  form: KeepForm,
): { values: BackupSettingsValues; errors: null } | { values: null; errors: KeepErrors } {
  const kept = inRange(form.kept, KEPT_MIN, KEPT_MAX);
  const snapshots = inRange(form.snapshots, SNAPSHOT_MIN, SNAPSHOT_MAX);
  const errors: KeepErrors = {};
  if (kept === null) errors.kept = B.keptError;
  if (snapshots === null) errors.snapshots = B.snapshotsError;
  if (kept === null || snapshots === null) return { values: null, errors };
  return { values: { db_backups_kept: kept, snapshot_retention_days: snapshots }, errors: null };
}

export function keepDirty(form: KeepForm, stored: BackupSettingsValues): boolean {
  const saved = keepFormFrom(stored);
  return form.kept !== saved.kept || form.snapshots !== saved.snapshots;
}

/** When the stored values change under the form (an import, another tab): an untouched form follows them; a form
 *  being edited keeps its edits (m2.5b round 1). */
export function followStored(form: KeepForm, before: BackupSettingsValues, now: BackupSettingsValues): KeepForm {
  const changed =
    before.db_backups_kept !== now.db_backups_kept || before.snapshot_retention_days !== now.snapshot_retention_days;
  if (!changed || keepDirty(form, before)) return form;
  return keepFormFrom(now);
}

// ---------- the daily backups ----------

/** "820 KB", "1.4 MB": Windows' own units (1 KB = 1024 bytes), so the size matches File Explorer. */
export function formatBytes(bytes: number): string {
  const number = (value: number, digits: number) =>
    value.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  if (bytes < 1024) return `${number(bytes, 0)} bytes`;
  if (bytes < 1024 * 1024) return `${number(Math.max(1, Math.round(bytes / 1024)), 0)} KB`;
  if (bytes < 1024 ** 3) return `${number(bytes / 1024 ** 2, 1)} MB`;
  return `${number(bytes / 1024 ** 3, 1)} GB`;
}

export interface DailyFacts {
  /** "29 October 2026 at 02:00 India Standard Time", or null before the first backup. */
  last: string | null;
  size: string | null;
  /** The next run, "now" when one is due, or null with no schedule (a copy run from source in tests). */
  next: string | null;
  count: number;
}

export function dailyFacts(settings: BackupSettings, when: WhenFormat, now: Date): DailyFacts {
  const last = when(settings.last_backup_at);
  const nextAt = settings.next_backup_at ? new Date(settings.next_backup_at) : null;
  let next: string | null = null;
  if (nextAt && !Number.isNaN(nextAt.getTime())) {
    next = nextAt.getTime() <= now.getTime() + 60_000 ? B.dueNow : when(settings.next_backup_at);
  }
  return {
    last,
    size: last && settings.last_backup_bytes !== null ? formatBytes(settings.last_backup_bytes) : null,
    next,
    count: settings.daily_count,
  };
}

// ---------- the passphrase ----------

/** Its length as the API counts it: code points after NFC. */
export function passphraseLength(text: string): number {
  return [...text.normalize("NFC")].length;
}

/** The export's two fields: 13's rule, then that they match. Null when both are fine. */
export function checkNewPassphrase(first: string, second: string): { first?: string; second?: string } | null {
  const length = passphraseLength(first);
  if (length < PASSPHRASE_MIN || length > PASSPHRASE_MAX) return { first: B.passphraseError };
  if (first !== second) return { second: B.passphraseMismatch };
  return null;
}

/** The import's one field. */
export function checkPassphrase(text: string): string | null {
  const length = passphraseLength(text);
  return length < PASSPHRASE_MIN || length > PASSPHRASE_MAX ? B.passphraseError : null;
}

// ---------- export ----------

/** "the keys of GPLFamily and PluginWay, the read-only S3 keys and the GitHub token" (13's list). A code this page
 *  doesn't know (a store removed since) is shown as its code. */
export function leftOutList(leftOut: LeftOut, names: ReadonlyMap<string, string>): string {
  const and = new Intl.ListFormat("en-GB", { style: "long", type: "conjunction" });
  const parts: string[] = [];
  if (leftOut.stores.length)
    parts.push(B.leftOutStores(and.format(leftOut.stores.map((code) => names.get(code) ?? code))));
  if (leftOut.s3.includes("rw")) parts.push(B.leftOutRw);
  if (leftOut.s3.includes("ro")) parts.push(B.leftOutRo);
  if (leftOut.github) parts.push(B.leftOutGithub);
  return parts.length ? and.format(parts) : B.leftOutSome;
}

export function exportedLine(fileName: string, leftOut: LeftOut | null, names: ReadonlyMap<string, string>): Line {
  if (leftOut) return { tone: "warning", text: B.leftOut(fileName, leftOutList(leftOut, names)) };
  return { tone: "success", text: B.exported(fileName) };
}

export function exportError(failure: unknown): Line {
  if (!(failure instanceof ApiError)) return { tone: "danger", text: B.exportNoAnswer };
  switch (failure.code) {
    case "busy":
      return { tone: "info", text: B.exportBusy };
    case "backup_failed":
      return { tone: "danger", text: `${B.exportFailed} ${B.nothingExported}` };
    case "secrets_unavailable":
      return { tone: "danger", text: B.exportSecretsUnavailable };
    default:
      return { tone: "danger", text: `${B.exportRefused(failure.status)} ${B.nothingExported}` };
  }
}

// ---------- import ----------

/** The file's own header says whether it is encrypted (`encryption` is null or an object). Null when the text isn't
 *  one of ours at all: the server answers that one (`export_invalid`). */
export function sniffEncrypted(text: string): boolean | null {
  try {
    const value: unknown = JSON.parse(text);
    if (!value || typeof value !== "object" || Array.isArray(value) || !("encryption" in value)) return null;
    const encryption = (value as { encryption: unknown }).encryption;
    if (encryption === null) return false;
    return typeof encryption === "object" ? true : null;
  } catch {
    return null;
  }
}

/** Before reading the file: one bigger than 1 MiB (or empty) isn't a v1 backup file, so nothing is sent. */
export function preCheckFile(name: string, size: number): Line | null {
  if (size > MAX_FILE_BYTES || size === 0) {
    return { tone: "danger", text: `${B.exportInvalid(name)} ${B.nothingImported}` };
  }
  return null;
}

/** 13's line for the kind of file, then the restart sentence whenever settings were written (plain files too). */
export function importedLine(result: ImportResult): Line {
  const done = result.encrypted
    ? B.importedEncrypted(result.stores, result.settings, result.secrets)
    : B.importedPlain(result.stores, result.settings);
  return { tone: "success", text: result.settings > 0 ? `${done} ${B.restartToApply}` : done };
}

export interface ImportFailure extends Line {
  /** The passphrase field takes the focus (a wrong passphrase, or one that's needed). */
  passphrase: "wrong" | "needed" | null;
}

/** Every import answer's 13 line, with "Nothing was imported." where it applies. */
export function importError(failure: unknown, fileName: string): ImportFailure {
  const line = (tone: Tone, text: string, passphrase: ImportFailure["passphrase"] = null): ImportFailure => ({
    tone,
    text,
    passphrase,
  });
  if (!(failure instanceof ApiError)) return line("danger", B.importNoAnswer);
  switch (failure.code) {
    case "wrong_passphrase":
      return line("danger", `${B.wrongPassphrase(fileName)} ${B.nothingImported}`, "wrong");
    case "passphrase_required":
      return line("warning", B.passphraseRequired(fileName), "needed");
    case "export_invalid":
      return line("danger", `${B.exportInvalid(fileName)} ${B.nothingImported}`);
    case "export_not_encrypted":
      return line("danger", B.notEncrypted(fileName));
    case "export_too_new":
      return line("danger", `${B.tooNew(fileName)} ${B.nothingImported}`);
    case "import_needs_empty":
      return line("warning", B.needsEmpty);
    case "busy":
      return line("info", B.importBusy);
    case "backup_failed":
      return line("danger", `${B.importFailed} ${B.nothingImported}`);
    case "secrets_unavailable":
      return line("danger", `${B.importSecretsUnavailable} ${B.nothingImported}`);
    default:
      return line("danger", `${B.importRefused(failure.status)} ${B.nothingImported}`);
  }
}
