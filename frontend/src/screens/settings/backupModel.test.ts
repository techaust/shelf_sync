// SET-05, BAK-01: Settings › Backup without React: the keep settings' limits, the daily backups' facts (none yet, a last
// backup, one due), the passphrase rule, the export's lines (with the left-out line), the import's checks before
// sending (1 MiB, the file's own `encryption`), and every error code's 13 text.
import { describe, expect, it } from "vitest";
import type { BackupSettings } from "../../api/backup";
import { ApiError, ApiUnreachableError, type ErrorCode } from "../../api/client";
import {
  checkKeepForm,
  checkNewPassphrase,
  checkPassphrase,
  dailyFacts,
  exportError,
  exportedLine,
  followStored,
  formatBytes,
  importError,
  importedLine,
  keepDirty,
  keepFormFrom,
  leftOutList,
  MAX_FILE_BYTES,
  passphraseLength,
  preCheckFile,
  sniffEncrypted,
} from "./backupModel";
import { B } from "./backupWording";

const NONE: BackupSettings = {
  db_backups_kept: 7,
  snapshot_retention_days: 30,
  last_backup_at: null,
  last_backup_bytes: null,
  next_backup_at: null,
  daily_count: 0,
};
const LAST: BackupSettings = {
  ...NONE,
  last_backup_at: "2026-10-28T20:30:00Z",
  last_backup_bytes: 1_468_006,
  next_backup_at: "2026-10-29T20:30:00Z",
  daily_count: 3,
};
const when = (iso: string | null | undefined) =>
  iso === "2026-10-28T20:30:00Z"
    ? "29 October 2026 at 02:00 India Standard Time"
    : iso
      ? "30 October 2026 at 02:00 India Standard Time"
      : null;
const NOW = new Date("2026-10-29T06:00:00Z");
const NAMES = new Map([
  ["GF", "GPLFamily"],
  ["PW", "PluginWay"],
]);
const FILE = "shelfsync-export-2026-10-29.ssbak";
const refused = (code: ErrorCode | null, status: number) => new ApiError("POST", "/api/backup/import", status, code);

describe("the keep settings", () => {
  it("1 to 30 backups and 1 to 365 days, the API's limits", () => {
    expect(checkKeepForm({ kept: "1", snapshots: "365" })).toEqual({
      values: { db_backups_kept: 1, snapshot_retention_days: 365 },
      errors: null,
    });
    expect(checkKeepForm({ kept: "30", snapshots: "1" }).errors).toBeNull();
    expect(checkKeepForm({ kept: "0", snapshots: "366" }).errors).toEqual({
      kept: "Use a number from 1 to 30.",
      snapshots: "Use a number of days from 1 to 365.",
    });
    expect(checkKeepForm({ kept: "31", snapshots: "7.5" }).errors).toEqual({
      kept: B.keptError,
      snapshots: B.snapshotsError,
    });
  });

  it("Save is off until a value changed", () => {
    expect(keepDirty(keepFormFrom(NONE), NONE)).toBe(false);
    expect(keepDirty({ ...keepFormFrom(NONE), kept: "10" }, NONE)).toBe(true);
  });
});

describe("the keep form after the stored values change (an import)", () => {
  const before = { db_backups_kept: 7, snapshot_retention_days: 30 };
  const after = { db_backups_kept: 14, snapshot_retention_days: 60 };

  it("an untouched form follows the imported values, so Save stays off and can't write the old ones back", () => {
    const form = followStored(keepFormFrom(before), before, after);
    expect(form).toEqual({ kept: "14", snapshots: "60" });
    expect(keepDirty(form, after)).toBe(false);
  });

  it("field by field: the edited field keeps its edit, the untouched one takes the imported value", () => {
    // kept is being edited (10); snapshots is untouched (30), so it follows the import to 60
    expect(followStored({ kept: "10", snapshots: "30" }, before, after)).toEqual({ kept: "10", snapshots: "60" });
    // the other way round
    expect(followStored({ kept: "7", snapshots: "90" }, before, after)).toEqual({ kept: "14", snapshots: "90" });
  });

  it("both fields edited: the form is kept as it is", () => {
    const edited = { kept: "10", snapshots: "90" };
    expect(followStored(edited, before, after)).toBe(edited);
  });

  it("nothing changed: the same form", () => {
    const form = keepFormFrom(before);
    expect(followStored(form, before, { ...before })).toBe(form);
  });

  it("after its own save (the form already shows the saved values), it stays as it is", () => {
    const saved = keepFormFrom(after);
    expect(followStored(saved, before, after)).toEqual(saved);
  });
});

describe("the daily backups' facts", () => {
  it("no backup yet: no time, no size, none kept", () => {
    expect(dailyFacts(NONE, when, NOW)).toEqual({ last: null, size: null, next: null, count: 0 });
  });

  it("a last backup: its local time with the zone, its size, the next one and the count", () => {
    expect(dailyFacts(LAST, when, NOW)).toEqual({
      last: "29 October 2026 at 02:00 India Standard Time",
      size: "1.4 MB",
      next: "30 October 2026 at 02:00 India Standard Time",
      count: 3,
    });
  });

  it("one due now (the first start, or a missed 02:00)", () => {
    expect(dailyFacts({ ...NONE, next_backup_at: "2026-10-29T06:00:00Z" }, when, NOW).next).toBe(B.dueNow);
  });

  it("a last backup whose size couldn't be read shows no size", () => {
    expect(dailyFacts({ ...LAST, last_backup_bytes: null }, when, NOW).size).toBeNull();
  });

  it("sizes in Windows' units", () => {
    expect(formatBytes(0)).toBe("0 bytes");
    expect(formatBytes(1023)).toBe("1,023 bytes");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(839_680)).toBe("820 KB");
    expect(formatBytes(1024 * 1024)).toBe("1 MB");
    expect(formatBytes(1_468_006)).toBe("1.4 MB");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3 GB");
    expect(B.copies(1)).toBe("1 daily copy");
    expect(B.copies(7)).toBe("7 daily copies");
  });
});

describe("the passphrase", () => {
  it("12 to 1024 characters, counted after NFC as the API counts them", () => {
    expect(checkNewPassphrase("a".repeat(11), "a".repeat(11))).toEqual({ first: B.passphraseError });
    expect(checkNewPassphrase("a".repeat(12), "a".repeat(12))).toBeNull();
    expect(checkNewPassphrase("a".repeat(1024), "a".repeat(1024))).toBeNull();
    expect(checkNewPassphrase("a".repeat(1025), "a".repeat(1025))).toEqual({ first: B.passphraseError });
    // "e" + a combining accent is one character after NFC: 12 typed, 11 counted
    const decomposed = `${"é".repeat(1)}${"a".repeat(10)}`;
    expect(passphraseLength(decomposed)).toBe(11);
    expect(checkPassphrase(decomposed)).toBe(B.passphraseError);
    // an emoji is one code point, as Python's len counts it
    expect(passphraseLength("🔑".repeat(12))).toBe(12);
    expect(B.passphraseError).toBe("Use a passphrase of 12 to 1024 characters.");
  });

  it("the second field must match", () => {
    expect(checkNewPassphrase("sample passphrase one", "sample passphrase two")).toEqual({
      second: B.passphraseMismatch,
    });
  });
});

describe("export", () => {
  it("with nothing left out: 13's line", () => {
    expect(exportedLine(FILE, null, NAMES)).toEqual({ tone: "success", text: `Exported ${FILE}.` });
  });

  it("the left-out line names the stores and the slots (X-ShelfSync-Left-Out)", () => {
    const line = exportedLine(FILE, { stores: ["GF", "PW"], s3: ["rw", "ro"], github: true }, NAMES);
    expect(line).toEqual({
      tone: "warning",
      text: `Exported ${FILE}, but left out the keys of GPLFamily and PluginWay, the read and write S3 keys, the read-only S3 keys and the GitHub token: ShelfSync couldn't read them in a usable form. Save them again, then export again.`,
    });
    expect(leftOutList({ stores: ["GF"], s3: [], github: false }, NAMES)).toBe("the keys of GPLFamily");
    expect(leftOutList({ stores: [], s3: ["ro"], github: false }, NAMES)).toBe("the read-only S3 keys");
    // a store removed since: its code
    expect(leftOutList({ stores: ["ZZ"], s3: [], github: true }, NAMES)).toBe("the keys of ZZ and the GitHub token");
    expect(leftOutList({ stores: [], s3: [], github: false }, NAMES)).toBe(B.leftOutSome);
  });

  it("every refusal's 13 line", () => {
    const at = (code: ErrorCode | null, status: number) =>
      exportError(new ApiError("POST", "/api/backup/export", status, code));
    expect(at("busy", 409)).toEqual({
      tone: "info",
      text: "Another export or import is still running. Try again in a moment.",
    });
    expect(at("backup_failed", 503).text).toBe(
      "ShelfSync couldn't finish the export. Check that its data folder isn't full or locked, then try again. Nothing was exported.",
    );
    expect(at("secrets_unavailable", 503).text).toBe(
      "Windows Credential Manager couldn't be read, so the keys couldn't be included. Nothing was exported.",
    );
    expect(at("invalid_request", 422).text).toBe("ShelfSync refused the export (HTTP 422). Nothing was exported.");
    expect(exportError(new ApiUnreachableError("POST", "/api/backup/export")).text).toBe(B.exportNoAnswer);
  });
});

describe("import: before anything is sent", () => {
  it("a file over 1 MiB (or empty) gets 13's export_invalid text and is never read", () => {
    expect(preCheckFile(FILE, MAX_FILE_BYTES)).toBeNull();
    expect(preCheckFile(FILE, 40_000)).toBeNull();
    expect(preCheckFile(FILE, MAX_FILE_BYTES + 1)).toEqual({
      tone: "danger",
      text: `Can't open ${FILE}: it isn't a ShelfSync export, or it was changed or damaged. Nothing was imported.`,
    });
    expect(preCheckFile(FILE, 0)?.text).toContain("isn't a ShelfSync export");
  });

  it("the file's own header says whether it is encrypted", () => {
    const header = { format: "shelfsync-export", version: 1, created_at: "2026-10-29T04:00:00Z", schema: 7 };
    expect(sniffEncrypted(JSON.stringify({ ...header, encryption: null, payload: {}, sha256: "0" }))).toBe(false);
    expect(sniffEncrypted(JSON.stringify({ ...header, encryption: { cipher: "AES-256-GCM" }, ciphertext: "x" }))).toBe(
      true,
    );
    expect(sniffEncrypted("not json")).toBeNull();
    expect(sniffEncrypted("[1, 2]")).toBeNull();
    expect(sniffEncrypted(JSON.stringify(header))).toBeNull();
    expect(sniffEncrypted(JSON.stringify({ ...header, encryption: "yes" }))).toBeNull();
  });
});

describe("import: the answers", () => {
  it("an encrypted file: stores, settings and keys, and the restart line", () => {
    expect(importedLine({ stores: 2, settings: 12, secrets: 9, encrypted: true })).toEqual({
      tone: "success",
      text: "Imported 2 stores, 12 settings and 9 keys. Restart ShelfSync to apply the imported settings.",
    });
    expect(importedLine({ stores: 1, settings: 1, secrets: 1, encrypted: true }).text).toBe(
      "Imported 1 store, 1 setting and 1 key. Restart ShelfSync to apply the imported settings.",
    );
  });

  it("a plain file: no keys, what to do about them, and the restart (it wrote settings too)", () => {
    expect(importedLine({ stores: 2, settings: 12, secrets: 0, encrypted: false })).toEqual({
      tone: "success",
      text: "Imported 2 stores and 12 settings. This file holds no keys: add each store's keys and the S3 keys yourself. Restart ShelfSync to apply the imported settings.",
    });
  });

  it("no restart sentence when no setting was written (either kind)", () => {
    expect(importedLine({ stores: 1, settings: 0, secrets: 2, encrypted: true }).text).toBe(
      "Imported 1 store, 0 settings and 2 keys.",
    );
    expect(importedLine({ stores: 1, settings: 0, secrets: 0, encrypted: false }).text).not.toContain("Restart");
  });

  it("every error code's 13 text, with 'Nothing was imported.' where it applies", () => {
    const text = (code: ErrorCode | null, status: number) => importError(refused(code, status), FILE).text;
    expect(text("wrong_passphrase", 422)).toBe(
      `Can't open ${FILE}: the passphrase doesn't match. Nothing was imported.`,
    );
    expect(text("passphrase_required", 422)).toBe(`${FILE} is encrypted. Enter the passphrase it was exported with.`);
    expect(text("export_invalid", 422)).toBe(
      `Can't open ${FILE}: it isn't a ShelfSync export, or it was changed or damaged. Nothing was imported.`,
    );
    expect(text("export_not_encrypted", 422)).toBe(
      `${FILE} isn't encrypted, so it can't be opened with a passphrase. Clear the passphrase and try again, or ask whoever sent it. Nothing was imported.`,
    );
    expect(text("export_too_new", 409)).toBe(
      `${FILE} was made by a newer ShelfSync. Update ShelfSync, then try again. Nothing was imported.`,
    );
    expect(text("import_needs_empty", 409)).toBe(
      "Import works on a fresh ShelfSync with no stores. This one already has a store, so nothing was imported.",
    );
    expect(text("busy", 409)).toBe("Another export or import is still running. Try again in a moment.");
    expect(text("backup_failed", 503)).toBe(
      "ShelfSync couldn't finish the import. Check that its data folder isn't full or locked, then try again. Nothing was imported.",
    );
    expect(text("secrets_unavailable", 503)).toBe(
      "Windows Credential Manager couldn't be used, so the file's keys couldn't be saved. Nothing was imported.",
    );
    expect(text("invalid_request", 422)).toBe("ShelfSync refused the import (HTTP 422). Nothing was imported.");
    expect(text(null, 500)).toBe("ShelfSync refused the import (HTTP 500). Nothing was imported.");
    expect(importError(new ApiUnreachableError("POST", "/api/backup/import"), FILE).text).toBe(
      "ShelfSync didn't answer, so the import may not have happened. Reload this page to check.",
    );
  });

  it("which answers send the focus back to the passphrase", () => {
    expect(importError(refused("wrong_passphrase", 422), FILE).passphrase).toBe("wrong");
    expect(importError(refused("passphrase_required", 422), FILE).passphrase).toBe("needed");
    expect(importError(refused("export_invalid", 422), FILE).passphrase).toBeNull();
  });
});
