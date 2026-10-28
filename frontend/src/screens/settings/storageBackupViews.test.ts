// SET-02, SET-05, BAK-01: each state of Settings › Storage and Settings › Backup as the pages draw them. The unit tests
// run in Node with no DOM, so the views are rendered to static HTML (react-dom/server); focus and the dialog were
// checked by hand in the built-in browser pane (run file section 3).
import { createRef, createElement as h, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { StorageSettings } from "../../api/storage";
import { DailyCard, ExportSection, FileText, ImportSection } from "./BackupView";
import { B } from "./backupWording";
import {
  KeyPairPanel,
  type KeyPairState,
  StorageEmpty,
  StorageFailed,
  StorageLoading,
  StorageSettingsCard,
  StorageTestNote,
} from "./StorageView";
import { pairState, storageFormFrom, testLines } from "./storageModel";
import { ST } from "./storageWording";

const decode = (html: string) =>
  html.replaceAll("&#x27;", "'").replaceAll("&quot;", '"').replaceAll("&amp;", "&").replaceAll("&gt;", ">");
const markup = (element: ReactElement) => decode(renderToStaticMarkup(element));
const FILE = "shelfsync-export-2026-10-29.ssbak";

const EMPTY: StorageSettings = {
  s3_endpoint: "",
  s3_region: "",
  s3_bucket: "",
  keep_previous_files: 1,
  download_link_template: '[amazon_s3 object="{key}"]',
  rw: { access_key_id: null, secret_access_key: null },
  ro: { access_key_id: null, secret_access_key: null },
  keys_readable: true,
};
const SAVED: StorageSettings = {
  ...EMPTY,
  s3_region: "ap-south-1",
  s3_bucket: "sample-downloads-bucket",
  keep_previous_files: 2,
  rw: { access_key_id: "AKIA••••9XYZ", secret_access_key: "••••" },
  ro: { access_key_id: "AKIA••••4QRS", secret_access_key: "••••" },
};

function card(over: Partial<Parameters<typeof StorageSettingsCard>[0]> = {}) {
  return markup(
    h(StorageSettingsCard, {
      form: storageFormFrom(SAVED),
      errors: {},
      aws: true,
      dirty: false,
      saving: false,
      result: null,
      onChange: vi.fn(),
      onSave: vi.fn(),
      ...over,
    }),
  );
}

function pair(storage: StorageSettings, slot: "rw" | "ro", over: Partial<KeyPairState> = {}) {
  const { set, masks } = pairState(storage, slot);
  return markup(
    h(KeyPairPanel, {
      slot,
      pair: {
        masks,
        readable: storage.keys_readable,
        set,
        open: storage.keys_readable && !set,
        saving: false,
        removing: false,
        errors: {},
        done: null,
        firstRef: createRef<HTMLInputElement>(),
        secondRef: createRef<HTMLInputElement>(),
        ...over,
      },
      handlers: { onOpen: vi.fn(), onCancel: vi.fn(), onTyped: vi.fn(), onSave: vi.fn(), onRemove: vi.fn() },
    }),
  );
}

describe("Settings › Storage", () => {
  it("loading, failed and empty", () => {
    expect(markup(h(StorageLoading))).toContain('aria-busy="true"');
    const failed = markup(h(StorageFailed, { text: ST.loadFailed, onRetry: vi.fn() }));
    expect(failed).toContain("ShelfSync didn't answer, so the storage settings can't be shown.");
    expect(failed).toContain("Try again");
    const empty = markup(h(StorageEmpty, { onAdd: vi.fn() }));
    expect(empty).toContain("Add the S3 bucket ShelfSync uploads to.");
    expect(empty).toContain("You need its name, region and two access keys: one that can write, one read-only.");
    expect(empty).toContain(">Add storage</button>");
  });

  it("saved: the five fields with their labels and 13's hints, Save off until something changes", () => {
    const html = card();
    for (const label of ["Endpoint", "Region", "Bucket", "Previous files to keep", "Download link template"]) {
      expect(html).toContain(`>${label}</label>`);
    }
    expect(html).toContain('value="ap-south-1"');
    expect(html).toContain('value="sample-downloads-bucket"');
    expect(html).toContain("Leave empty to use Amazon S3.");
    expect(html).toContain("Region, for example ap-south-1.");
    expect(html).toContain(">per slot</span>");
    expect(html).toContain('<span class="mono">{key}</span> becomes the file name.');
    expect(html).toContain(">Amazon S3</h3>");
    expect(html).toMatch(/id="storage-save"[^>]*aria-disabled="true"/);
    expect(card({ dirty: true })).not.toMatch(/id="storage-save"[^>]*aria-disabled/);
    expect(card({ aws: false })).toContain(">S3-compatible storage</h3>");
  });

  it("field errors: each at its field, aria-invalid and described", () => {
    const html = card({
      errors: { endpoint: ST.endpointError, bucket: ST.bucketError, template: ST.templateError },
    });
    expect(html).toMatch(/id="storage-endpoint"[^>]*aria-invalid="true"[^>]*aria-describedby="storage-endpoint-error/);
    expect(html).toContain(ST.endpointError);
    expect(html).toContain(ST.bucketError);
    expect(html).toContain(ST.templateError);
    expect(html).not.toMatch(/id="storage-region"[^>]*aria-invalid/);
  });

  it("the save's answer", () => {
    expect(card({ result: { tone: "success", text: ST.saved } })).toContain("Storage settings saved.");
  });

  it("keys not set: the inputs are open with Save keys, and nothing to remove", () => {
    const html = pair(EMPTY, "rw");
    expect(html).toContain(">Read and write</legend>");
    expect(html).toContain("Uploads new files and deletes old ones.");
    expect(html).toContain('id="storage-rw-first"');
    expect(html).toContain('type="password"');
    expect(html).toContain(">Save keys</button>");
    expect(html).not.toContain("Remove keys");
    expect(html).not.toContain("value=");
  });

  it("keys saved: the key ID's mask and the secret as ••••, Replace keys and Remove keys", () => {
    const html = pair(SAVED, "ro");
    expect(html).toContain(">Read only</legend>");
    expect(html).toContain('<span class="mono secret-pair__mask">AKIA••••4QRS</span>');
    expect(html).toContain('<span class="mono secret-pair__mask">••••</span>');
    expect(html).toContain(">Replace keys</button>");
    expect(html).toContain(">Remove keys</button>");
    expect(html).not.toContain('type="password"');
  });

  it("keys unreadable: 'Couldn't be read', never 'Not set'", () => {
    const html = pair({ ...EMPTY, keys_readable: false }, "rw");
    expect(html.match(/Couldn't be read/g)).toHaveLength(2);
    expect(html).not.toContain("Not set");
    expect(html).toContain(">Replace keys</button>");
    expect(html).toContain(">Remove keys</button>");
  });

  it("a pair's errors and its done line", () => {
    const errors = pair(EMPTY, "rw", { errors: { first: ST.keyIdError, second: ST.secretError } });
    expect(errors).toContain(ST.keyIdError);
    expect(errors).toContain(ST.secretError);
    expect(errors).toMatch(/id="storage-rw-first"[^>]*aria-invalid="true"/);
    expect(pair(EMPTY, "rw", { errors: { pair: ST.pairError } })).toContain(
      "Enter both the key ID and the secret key.",
    );
    expect(pair(SAVED, "rw", { done: ST.keysSaved })).toContain("Keys saved.");
    expect(pair(EMPTY, "rw", { done: ST.keysRemoved })).toContain("Keys removed.");
  });

  it("no Test button: the line in its place, with 13's line while region or bucket is empty", () => {
    const saved = markup(h(StorageTestNote, { lines: testLines(SAVED), onGuide: vi.fn() }));
    expect(saved).toContain(ST.testLater);
    expect(saved).not.toContain(ST.testNeeds);
    expect(saved).toContain(">S3 access policy guide</button>");
    expect(saved).not.toContain("Test connection");
    expect(markup(h(StorageTestNote, { lines: testLines(EMPTY), onGuide: vi.fn() }))).toContain(
      "Region and bucket must be filled in before the bucket can be tested.",
    );
  });
});

describe("Settings › Backup: what's kept", () => {
  const daily = (facts: Parameters<typeof DailyCard>[0]["facts"]) =>
    markup(
      h(DailyCard, {
        facts,
        form: { kept: "7", snapshots: "30" },
        errors: {},
        dirty: false,
        saving: false,
        result: null,
        onChange: vi.fn(),
        onSave: vi.fn(),
        onRestoreGuide: vi.fn(),
      }),
    );

  it("no backup yet: None yet, and 13's restore line for an empty folder", () => {
    const html = daily({ last: null, size: null, next: B.dueNow, count: 0 });
    expect(html).toContain(">What's kept</h3>");
    expect(html).toContain("None yet");
    expect(html).toContain("0 daily copies");
    expect(html).toContain("There are no backups to restore yet.");
    expect(html).not.toContain(B.restoreLink);
  });

  it("a last backup: its time with the zone and its size, the next one, the count, and how to restore", () => {
    const html = daily({
      last: "29 October 2026 at 02:00 India Standard Time",
      size: "1.4 MB",
      next: "30 October 2026 at 02:00 India Standard Time",
      count: 3,
    });
    expect(html).toContain("29 October 2026 at 02:00 India Standard Time");
    expect(html).toContain('<span class="backup-facts__size">1.4 MB</span>');
    expect(html).toContain("30 October 2026 at 02:00 India Standard Time");
    expect(html).toContain("3 daily copies");
    expect(html).toContain(B.restoreLine);
    expect(html).toContain(">How to restore a backup</button>");
    expect(html).not.toMatch(/<button[^>]*>Restore</); // a command, never a button
  });

  it("the two settings, with the snapshots line", () => {
    const html = daily({ last: null, size: null, next: null, count: 0 });
    expect(html).toContain(">Database backups to keep</label>");
    expect(html).toContain(">Keep snapshots for</label>");
    expect(html).toContain(B.snapshotsHint);
    expect(html).not.toContain(B.nextLabel); // no schedule: no next line
  });
});

describe("Settings › Backup: export and import", () => {
  const exportState = (over: Partial<Parameters<typeof ExportSection>[0]["state"]> = {}) => ({
    includeSecrets: false,
    errors: {},
    running: false,
    blocked: false,
    result: null,
    firstRef: createRef<HTMLInputElement>(),
    secondRef: createRef<HTMLInputElement>(),
    ...over,
  });
  const exportHandlers = { onIncludeSecrets: vi.fn(), onTyped: vi.fn(), onExport: vi.fn() };
  const importState = (over: Partial<Parameters<typeof ImportSection>[0]["state"]> = {}) => ({
    chosen: null,
    passphraseError: undefined,
    running: false,
    blocked: false,
    result: null,
    resultFile: null,
    passRef: createRef<HTMLInputElement>(),
    fileRef: createRef<HTMLInputElement>(),
    ...over,
  });
  const importHandlers = {
    onPick: vi.fn(),
    onFile: vi.fn(),
    onTyped: vi.fn(),
    onImport: vi.fn(),
    onRetryPassphrase: vi.fn(),
  };

  it("export without secrets: 13's line, no passphrase field", () => {
    const html = markup(h(ExportSection, { state: exportState(), handlers: exportHandlers }));
    expect(html).toContain("This file holds your settings and stores, but no keys or tokens.");
    expect(html).toContain("Include secrets (needs a passphrase)");
    expect(html).toContain(">Export settings</button>");
    expect(html).not.toContain('type="password"');
  });

  it("export with secrets: two password fields, never with a value", () => {
    const html = markup(h(ExportSection, { state: exportState({ includeSecrets: true }), handlers: exportHandlers }));
    expect(html.match(/type="password"/g)).toHaveLength(2);
    expect(html).toContain(">Passphrase</label>");
    expect(html).toContain(">Type the passphrase again</label>");
    expect(html).toContain("At least 12 characters. You need it to import this file, and ShelfSync can't recover it.");
    expect(html).toMatch(/autocomplete="new-password"/i);
    expect(html).not.toMatch(/type="password"[^>]*value=/);
    expect(html).toContain("checked");
  });

  it("export errors and results, the file's name in mono", () => {
    const errors = markup(
      h(ExportSection, {
        state: exportState({ includeSecrets: true, errors: { second: B.passphraseMismatch } }),
        handlers: exportHandlers,
      }),
    );
    expect(errors).toContain("The two passphrases don't match.");
    const done = markup(
      h(ExportSection, {
        state: exportState({ result: { tone: "success", text: B.exported(FILE) } }),
        handlers: exportHandlers,
      }),
    );
    expect(done).toContain(`Exported <span class="mono file-name">${FILE}</span>.`);
    const leftOut = markup(
      h(ExportSection, {
        state: exportState({ result: { tone: "warning", text: B.leftOut(FILE, "the keys of GPLFamily") } }),
        handlers: exportHandlers,
      }),
    );
    expect(leftOut).toContain("but left out the keys of GPLFamily: ShelfSync couldn't read them in a usable form.");
    expect(leftOut).toContain('class="alert is-warning"');
  });

  it("while an import runs, export waits (and the other way round)", () => {
    const html = markup(h(ExportSection, { state: exportState({ blocked: true }), handlers: exportHandlers }));
    expect(html).toMatch(/id="backup-export"[^>]*aria-disabled="true"/);
    const importing = markup(h(ImportSection, { state: importState({ blocked: true }), handlers: importHandlers }));
    expect(importing).toMatch(/id="backup-pick"[^>]*aria-disabled="true"/);
  });

  it("import, nothing chosen: 13's line and Import from file…", () => {
    const html = markup(h(ImportSection, { state: importState(), handlers: importHandlers }));
    expect(html).toContain("Import is for a new install or a new PC. It adds the stores and settings in the file.");
    expect(html).toContain(">Import from file…</button>");
    expect(html).toContain('type="file"');
    expect(html).toContain('accept=".ssbak,application/json"');
    expect(html).not.toContain('type="password"');
  });

  it("an encrypted file: its name, 'Passphrase for <file>' and Import", () => {
    const html = markup(
      h(ImportSection, { state: importState({ chosen: { name: FILE, encrypted: true } }), handlers: importHandlers }),
    );
    expect(html).toContain(`<span class="mono file-name">${FILE}</span>`);
    expect(html).toContain(B.chosenEncrypted);
    expect(html).toContain(`Passphrase for <span class="mono file-name">${FILE}</span>`);
    expect(html).toContain(">Import</button>");
    expect(html).toContain(">Choose another file</button>");
  });

  it("a plain file: no passphrase field", () => {
    const html = markup(
      h(ImportSection, { state: importState({ chosen: { name: FILE, encrypted: false } }), handlers: importHandlers }),
    );
    expect(html).toContain(B.chosenPlain);
    expect(html).not.toContain('type="password"');
  });

  it("a wrong passphrase: the danger line with Try another passphrase", () => {
    const html = markup(
      h(ImportSection, {
        state: importState({
          chosen: { name: FILE, encrypted: true },
          result: {
            tone: "danger",
            text: `${B.wrongPassphrase(FILE)} ${B.nothingImported}`,
            passphrase: "wrong",
          },
          resultFile: FILE,
        }),
        handlers: importHandlers,
      }),
    );
    expect(html).toContain('class="alert is-danger" role="alert"');
    expect(html).toContain(`Can't open <span class="mono file-name">${FILE}</span>: the passphrase doesn't match.`);
    expect(html).toContain("Nothing was imported.");
    expect(html).toContain(">Try another passphrase</button>");
  });

  it("a finished encrypted import: 13's line with the restart", () => {
    const html = markup(
      h(ImportSection, {
        state: importState({
          result: { tone: "success", text: B.importedEncrypted(2, 12, 9) },
          resultFile: FILE,
        }),
        handlers: importHandlers,
      }),
    );
    expect(html).toContain(
      "Imported 2 stores, 12 settings and 9 keys. Restart ShelfSync to apply the imported settings.",
    );
    expect(html).toContain('class="alert is-success"');
  });

  it("FileText marks the file's name once, and leaves a line without it alone", () => {
    expect(markup(h(FileText, { text: `${FILE} is encrypted.`, name: FILE }))).toBe(
      `<span class="mono file-name">${FILE}</span> is encrypted.`,
    );
    expect(markup(h(FileText, { text: B.needsEmpty, name: FILE }))).toBe(B.needsEmpty);
  });
});
