// Settings › Backup's calls (BAK-01, SET-05): the daily backups' state and the two keep settings, and the backup file's
// export and import (m2.4). The passphrase goes out in one POST body and nowhere else: never in a URL, storage or a
// log. The export's answer is the file itself, read as a Blob with its headers through the client's `sendRaw`.

import type { ApiClient } from "./client";
import type { components } from "./schema";
import type { S3Slot } from "./storage";

type Schemas = components["schemas"];
export type BackupSettings = Schemas["BackupSettingsResponse"];
export type BackupSettingsValues = Schemas["BackupSettingsValues"];
export type ImportResult = Schemas["ImportResult"];
type ExportRequest = Schemas["ExportRequest"];
type ImportRequest = Schemas["ImportRequest"];

export const BACKUP_SETTINGS_PATH = "/api/settings/backup";
export const BACKUP_SETTINGS_QUERY_KEY = ["settings", "backup"] as const;
export const BACKUP_EXPORT_PATH = "/api/backup/export";
export const BACKUP_IMPORT_PATH = "/api/backup/import";
export const LEFT_OUT_HEADER = "X-ShelfSync-Left-Out";

/** The name a file gets when the answer doesn't give a usable one (13's own example name). */
export const FALLBACK_FILE_NAME = "shelfsync-export.ssbak";

export const getBackupSettings = (api: ApiClient) => api.get<BackupSettings>(BACKUP_SETTINGS_PATH);

export function saveBackupSettings(api: ApiClient, values: BackupSettingsValues) {
  const body: BackupSettingsValues = {
    db_backups_kept: values.db_backups_kept,
    snapshot_retention_days: values.snapshot_retention_days,
  };
  return api.send<BackupSettingsValues>("PUT", BACKUP_SETTINGS_PATH, body);
}

/** What `X-ShelfSync-Left-Out` names: store codes and slot names only, never a value (11, 2026-10-29). */
export interface LeftOut {
  stores: string[];
  s3: S3Slot[];
  github: boolean;
}

export interface ExportedFile {
  blob: Blob;
  fileName: string;
  /** null when nothing was left out (the header is absent). */
  leftOut: LeftOut | null;
}

/**
 * The file name from `Content-Disposition: attachment; filename="shelfsync-export-<date>.ssbak"`. Only a plain
 * `.ssbak` name of letters, digits, dots, hyphens and underscores is used; anything else (a path, quotes, another
 * extension) falls back to 13's example name, so a header can never choose where or what is saved.
 */
export function fileNameFrom(header: string | null): string {
  const match = header ? /filename="([^"]*)"/i.exec(header) : null;
  const name = match?.[1] ?? "";
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.ssbak$/.test(name) ? name : FALLBACK_FILE_NAME;
}

/** `stores:SA,SB;s3:rw,ro;github` (backend api/backup.py). Parts this page doesn't know are skipped. */
export function parseLeftOut(header: string | null): LeftOut | null {
  if (header === null) return null;
  const leftOut: LeftOut = { stores: [], s3: [], github: false };
  for (const part of header.split(";")) {
    const [kind = "", list = ""] = part.trim().split(":", 2);
    const items = list
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (kind === "stores") leftOut.stores.push(...items.filter((code) => /^[A-Z]{2}$/.test(code)));
    else if (kind === "s3") leftOut.s3.push(...items.filter((slot): slot is S3Slot => slot === "rw" || slot === "ro"));
    else if (kind === "github") leftOut.github = true;
  }
  return leftOut;
}

/** POST /api/backup/export: `passphrase` null makes a file without secrets. */
export async function exportBackup(api: ApiClient, passphrase: string | null): Promise<ExportedFile> {
  const body: ExportRequest = { passphrase };
  const response = await api.sendRaw("POST", BACKUP_EXPORT_PATH, body);
  const blob = await response.blob();
  return {
    blob,
    fileName: fileNameFrom(response.headers.get("Content-Disposition")),
    leftOut: parseLeftOut(response.headers.get(LEFT_OUT_HEADER)),
  };
}

export function importBackup(api: ApiClient, file: string, passphrase: string | null) {
  const body: ImportRequest = { file, passphrase };
  return api.send<ImportResult>("POST", BACKUP_IMPORT_PATH, body);
}

/** What `saveBlob` needs from the page (the real window by default; fakes in tests: there is no DOM in Vitest). */
export interface DownloadHost {
  createObjectURL(blob: Blob): string;
  revokeObjectURL(url: string): void;
  /** Clicks a temporary `<a href download>`: the browser saves the file under its own download rules. */
  clickLink(href: string, fileName: string): void;
  later(run: () => void, ms: number): void;
}

export const browserDownloadHost: DownloadHost = {
  createObjectURL: (blob) => URL.createObjectURL(blob),
  revokeObjectURL: (url) => URL.revokeObjectURL(url),
  clickLink(href, fileName) {
    const link = document.createElement("a");
    link.href = href;
    link.download = fileName;
    link.rel = "noopener";
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
  },
  later: (run, ms) => {
    window.setTimeout(run, ms);
  },
};

/** How long the blob: address stays valid after the click (the download has started long before). */
export const REVOKE_AFTER_MS = 10_000;

/** Saves an exported file through the browser's own download (a same-page blob: link; nothing leaves this PC). */
export function saveBlob(file: { blob: Blob; fileName: string }, host: DownloadHost = browserDownloadHost): void {
  const url = host.createObjectURL(file.blob);
  try {
    host.clickLink(url, file.fileName);
  } finally {
    host.later(() => host.revokeObjectURL(url), REVOKE_AFTER_MS);
  }
}
