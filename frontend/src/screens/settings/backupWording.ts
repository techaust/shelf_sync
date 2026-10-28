// Every owner-facing string of Settings › Backup (UI-SET; SET-05, BAK-01), with where it comes from:
// - "13": docs/13-content.md section 3, the row "Backup export and import (M2.4)";
// - "13 restore": the row "Restore command (M2.2)";
// - "13 M1b.4": the row "Settings screens (M1b.4)" (the save, refusal and no-answer patterns);
// - "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js, backupPage());
// - "brief": docs/runs/m2.5b-storage-backup-screens.md section 1;
// - "proposed (m2.5b)": new in this task, listed in that run file's section 3 for the lead.
// `<file>` in 13 (written there as shelfsync-export.ssbak) is the name of the file the owner chose or got.

export const B = {
  // ---------- the daily backups ----------
  dailyTitle: "What's kept", // mockup
  lastLabel: "Last backup", // proposed (m2.5b)
  nextLabel: "Next backup", // proposed (m2.5b)
  countLabel: "Kept now", // proposed (m2.5b)
  none: "None yet", // proposed (m2.5b)
  dueNow: "Now, then every day at 02:00", // proposed (m2.5b): one is due (the first start, or a missed 02:00)
  /** "1 daily copy" / "7 daily copies" (the mockup's unit). */
  copies: (n: number) => `${n.toLocaleString("en-GB")} daily ${n === 1 ? "copy" : "copies"}`,
  restoreNone: "There are no backups to restore yet.", // 13 restore ("Empty")
  // proposed (m2.5b): the restore runbook's summary (docs/runbooks/restore-database.md)
  restoreLine:
    "Restoring a backup is a command, not a button: quit ShelfSync from the tray icon, then run the restore command in Windows PowerShell.",
  restoreLink: "How to restore a backup", // proposed (m2.5b): opens the Help panel's restore guide
  kept: "Database backups to keep", // mockup, brief
  keptUnit: "daily copies", // mockup
  keptError: "Use a number from 1 to 30.", // 13 M2.3 pattern ("Use a number from 1 to 5.")
  snapshots: "Keep snapshots for", // brief
  snapshotsUnit: "days", // mockup
  snapshotsHint: "Saved now. ShelfSync starts taking nightly snapshots of your products in a later version.", // proposed
  snapshotsError: "Use a number of days from 1 to 365.", // 13 M1b.4
  save: "Save backup settings", // proposed (m2.5b), the pattern of "Save app"
  saved: "Backup settings saved.", // proposed (m2.5b), the pattern of 13's "Storage settings saved."
  saveFailed: "ShelfSync didn't answer, so the backup settings may not have been saved. Reload this page to check.",
  saveRefused: (status: number) => `ShelfSync refused the backup settings (HTTP ${status}), so nothing was saved.`,
  loadFailed: "ShelfSync didn't answer, so the backup settings can't be shown.",
  loadRefused: (status: number) => `ShelfSync refused to show the backup settings (HTTP ${status}).`,
  staleNotice: "ShelfSync didn't answer just now, so this may be out of date.", // 13 M1b.4
  tryAgain: "Try again",

  // ---------- export ----------
  transferTitle: "Export and import", // mockup
  exportTitle: "Export", // proposed (m2.5b): the section's heading
  exportPlain: "This file holds your settings and stores, but no keys or tokens.", // 13
  // proposed (m2.5b): the same line when secrets are included
  exportSecrets: "This file holds your settings, your stores and their keys, locked with your passphrase.",
  includeSecrets: "Include secrets (needs a passphrase)", // 13
  passphrase: "Passphrase", // mockup
  passphraseHint: "At least 12 characters. You need it to import this file, and ShelfSync can't recover it.", // 13
  passphraseAgain: "Type the passphrase again", // proposed (m2.5b)
  passphraseError: "Use a passphrase of 12 to 1024 characters.", // 13
  passphraseMismatch: "The two passphrases don't match.", // proposed (m2.5b)
  exportButton: "Export settings", // 13
  exported: (file: string) => `Exported ${file}.`, // 13
  leftOut: (file: string, list: string) =>
    `Exported ${file}, but left out ${list}: ShelfSync couldn't read them in a usable form. Save them again, then export again.`, // 13
  leftOutStores: (names: string) => `the keys of ${names}`, // 13
  leftOutRw: "the read and write S3 keys", // 13
  leftOutRo: "the read-only S3 keys", // 13
  leftOutGithub: "the GitHub token", // 13
  leftOutSome: "some of the keys", // proposed (m2.5b): a header this page can't read
  exportBusy: "Another export or import is still running. Try again in a moment.", // 13 `busy`
  exportFailed:
    "ShelfSync couldn't finish the export. Check that its data folder isn't full or locked, then try again.", // 13
  exportSecretsUnavailable:
    "Windows Credential Manager couldn't be read, so the keys couldn't be included. Nothing was exported.", // 13
  exportNoAnswer: "ShelfSync didn't answer, so nothing was exported. Try again.", // proposed (m2.5b)
  exportRefused: (status: number) => `ShelfSync refused the export (HTTP ${status}).`, // proposed (m2.5b)
  nothingExported: "Nothing was exported.", // 13

  // ---------- import ----------
  importTitle: "Import", // proposed (m2.5b): the section's heading
  importText: "Import is for a new install or a new PC. It adds the stores and settings in the file.", // 13
  importButton: "Import from file…", // 13
  importAnother: "Choose another file", // proposed (m2.5b)
  chosenEncrypted: "Encrypted: it holds keys.", // proposed (m2.5b)
  chosenPlain: "Not encrypted: it holds no keys.", // proposed (m2.5b)
  importPassphrase: (file: string) => `Passphrase for ${file}`, // 13
  importGo: "Import", // proposed (m2.5b)
  importedEncrypted: (stores: number, settings: number, keys: number) =>
    `Imported ${count(stores, "store")}, ${count(settings, "setting")} and ${count(keys, "key")}. Restart ShelfSync to apply the imported settings.`, // 13
  importedPlain: (stores: number, settings: number) =>
    `Imported ${count(stores, "store")} and ${count(settings, "setting")}. This file holds no keys: add each store's keys and the S3 keys yourself.`, // 13
  nothingImported: "Nothing was imported.", // 13
  wrongPassphrase: (file: string) => `Can't open ${file}: the passphrase doesn't match.`, // 13
  passphraseRequired: (file: string) => `${file} is encrypted. Enter the passphrase it was exported with.`, // 13
  exportInvalid: (file: string) => `Can't open ${file}: it isn't a ShelfSync export, or it was changed or damaged.`, // 13
  notEncrypted: (file: string) =>
    `${file} isn't encrypted, so it can't be opened with a passphrase. Clear the passphrase and try again, or ask whoever sent it. Nothing was imported.`, // 13
  tooNew: (file: string) => `${file} was made by a newer ShelfSync. Update ShelfSync, then try again.`, // 13
  needsEmpty:
    "Import works on a fresh ShelfSync with no stores. This one already has a store, so nothing was imported.", // 13
  importBusy: "Another export or import is still running. Try again in a moment.", // 13 `busy`
  importFailed:
    "ShelfSync couldn't finish the import. Check that its data folder isn't full or locked, then try again.", // 13
  // proposed (m2.5b): 13's shared line ("Check the keys and try again") doesn't fit a file
  importSecretsUnavailable: "Windows Credential Manager couldn't be used, so the file's keys couldn't be saved.",
  importNoAnswer: "ShelfSync didn't answer, so the import may not have happened. Reload this page to check.", // 13 M1b.4
  importRefused: (status: number) => `ShelfSync refused the import (HTTP ${status}).`, // proposed (m2.5b)
  readFailed: (file: string) => `Can't read ${file} from this PC. Choose the file again.`, // proposed (m2.5b)
  tryAnother: "Try another passphrase", // mockup
};

/** "1 store", "3 stores" (13 writes "<n> stores"; proposed (m2.5b): the singular for one). */
function count(n: number, word: string): string {
  return `${n.toLocaleString("en-GB")} ${word}${n === 1 ? "" : "s"}`;
}
