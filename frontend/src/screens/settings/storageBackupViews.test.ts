// SET-02, SET-05, BAK-01: each state of Settings › Storage and Settings › Backup as the pages draw them. The unit tests
// run in Node with no DOM, so the views are rendered to static HTML (react-dom/server); focus and the dialog were
// checked by hand in the built-in browser pane (run file section 3).
import { createRef, createElement as h, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { StorageSettings, StorageTest, StorageTestStep } from "../../api/storage";
import { STORAGE_TEST_IDLE, type StorageTestEntry } from "../../lib/storageTest";
import { DailyCard, ExportSection, FileText, ImportSection } from "./BackupView";
import { importedLine } from "./backupModel";
import { B } from "./backupWording";
import {
  KeyPairPanel,
  type KeyPairState,
  StorageEmpty,
  StorageFailed,
  StorageLoading,
  StorageSettingsCard,
  StorageTestCard,
} from "./StorageView";
import { pairState, storageFormFrom } from "./storageModel";
import { planStorageTest, storageTestView } from "./storageTestModel";
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
});

describe("Settings › Storage: the Test card (SET-02, ERR-03)", () => {
  const WHEN = () => "2 November 2026 at 15:30 India Standard Time";
  const step = (
    name: StorageTestStep["step"],
    state: StorageTestStep["state"],
    over: Partial<StorageTestStep> = {},
  ): StorageTestStep => ({
    step: name,
    key_pair: name === "read" ? "ro" : "rw",
    state,
    latency_ms: state === "not_run" ? null : 120,
    reason: null,
    aws_code: null,
    http_status: null,
    ...over,
  });
  const PASSED: StorageTest = {
    ok: true,
    tested_at: "2026-11-02T10:00:00Z",
    latency_ms: 412,
    steps: [step("write", "passed"), step("read", "passed"), step("delete", "passed")],
    left_behind: null,
  };
  const testCard = (
    entry: Partial<StorageTestEntry> = {},
    { saved = SAVED, dirty = false }: { saved?: StorageSettings; dirty?: boolean } = {},
  ) => {
    const full = { ...STORAGE_TEST_IDLE, region: saved.s3_region, ...entry };
    return markup(
      h(StorageTestCard, {
        plan: planStorageTest(saved, dirty),
        running: full.running,
        view: storageTestView(full, WHEN),
        onTest: vi.fn(),
        onGuide: vi.fn(),
      }),
    );
  };

  it("never tested: the button, 13's 'Not tested yet.', the guide and the cost hint, no steps", () => {
    const html = testCard();
    expect(html).toContain('id="storage-test-button"');
    expect(html).toContain(">Test connection</button>");
    expect(html).not.toMatch(/id="storage-test-button"[^>]*aria-disabled/);
    expect(html).toContain("Not tested yet.");
    expect(html).toContain(">S3 access policy guide</button>");
    expect(html).toContain('ShelfSync writes a tiny test file under <span class="mono">shelfsync-test/</span>');
    expect(html).toContain("about 4 small S3 requests, a tiny AWS charge.");
    expect(html).not.toContain('class="test-steps"');
    expect(html).not.toContain("arrives with the S3 update");
  });

  it("passed: the line with tabular milliseconds and when, and three passed steps with their keys", () => {
    const html = testCard({ result: { ...PASSED, latency_ms: 1412 } });
    expect(html).toContain("Passed in 1,412 ms.");
    expect(html).toContain("Tested 2 November 2026 at 15:30 India Standard Time.");
    expect(html).toContain('<ol class="test-steps" aria-label="Test steps">');
    expect(html).toContain('Write a test file <span class="muted">with the read and write key</span>');
    expect(html).toContain('Read it back <span class="muted">with the read-only key</span>');
    expect(html).toContain('Delete it <span class="muted">with the read and write key</span>');
    expect(html.match(/class="is-ok"/g)).toHaveLength(3);
    expect(html.match(/>Passed<\/strong>/g)).toHaveLength(3);
  });

  it("failed at write (ERR-03, no such bucket): the reason line, the failed step's code, the rest not run", () => {
    const html = testCard({
      result: {
        ...PASSED,
        ok: false,
        steps: [
          step("write", "failed", { reason: "bucket_missing", aws_code: "NoSuchBucket", http_status: 404 }),
          step("read", "not_run"),
          step("delete", "not_run"),
        ],
      },
    });
    expect(html).toContain('class="test-result is-danger"');
    expect(html).toContain(
      "Failed at the write step: the bucket doesn't exist (NoSuchBucket). Check its name and region.",
    );
    expect(html).toContain('class="is-bad"');
    expect(html).toContain(">Failed: NoSuchBucket</strong>");
    expect(html.match(/>Not run<\/strong>/g)).toHaveLength(2);
    expect(html.match(/class="is-skip"/g)).toHaveLength(2);
  });

  it("left behind: the warning with the key in IBM Plex Mono", () => {
    const key = "shelfsync-test/20261102T100000Z-0123456789abcdef0123456789abcdef.txt";
    const html = testCard({
      result: {
        ...PASSED,
        ok: false,
        steps: [
          step("write", "passed"),
          step("read", "passed"),
          step("delete", "failed", { reason: "still_there", http_status: 200 }),
        ],
        left_behind: key,
      },
    });
    expect(html).toContain(
      `The test file <span class="mono file-name">${key}</span> may still be in the bucket. You can delete it in the S3 console.`,
    );
    expect(html).toContain('class="alert is-warning"');
    expect(html).toContain(">Failed: HTTP 200</strong>");
  });

  it("can't test: aria-disabled with the reason tied to it; 13's storage_not_set, then keys_missing", () => {
    const noBucket = testCard({}, { saved: { ...SAVED, s3_bucket: "" } });
    expect(noBucket).toMatch(
      /id="storage-test-button"[^>]*aria-disabled="true"[^>]*aria-describedby="storage-test-line"/,
    );
    expect(noBucket).toContain('id="storage-test-line"><svg');
    expect(noBucket).toContain("Region and bucket must be filled in and saved before the bucket can be tested.");
    const noKeys = testCard({}, { saved: { ...SAVED, ro: { access_key_id: null, secret_access_key: null } } });
    expect(noKeys).toContain("Save both key pairs, read and write and read-only, before testing.");
    expect(noKeys).toMatch(/id="storage-test-button"[^>]*aria-disabled="true"/);
  });

  it("unsaved changes: it can test, and says it tests what is saved", () => {
    const html = testCard({}, { dirty: true });
    expect(html).not.toMatch(/id="storage-test-button"[^>]*aria-disabled/);
    expect(html).toMatch(/id="storage-test-button"[^>]*aria-describedby="storage-test-note"/);
    expect(html).toContain("The test uses the saved settings. Save your changes to test them.");
  });

  it("running: the button busy, the progress line, no steps", () => {
    const html = testCard({ running: true });
    expect(html).toMatch(/id="storage-test-button"[^>]*aria-disabled="true"[^>]*aria-busy="true"/);
    expect(html).toContain("is-spinning");
    expect(html).toContain("Testing the bucket. This can take up to a minute.");
    expect(html).not.toContain('class="test-steps"');
  });

  it("a save landed while it ran (T2 review 1): the answer stays, with the note inside the live region", () => {
    const html = testCard({ result: PASSED, stale: true });
    expect(html).toContain("Passed in 412 ms.");
    expect(html).toMatch(
      /role="status">[\s\S]*class="storage-test__note is-stale"[\s\S]*This test used the settings from before your last save\. Test again to check them\.[\s\S]*<\/div>/,
    );
    expect(testCard({ result: PASSED })).not.toContain("is-stale");
  });

  it("the reason it can't test wins over a test still running: no spinner beside it (T2 review 5)", () => {
    const html = testCard(
      { running: true },
      { saved: { ...SAVED, ro: { access_key_id: null, secret_access_key: null } } },
    );
    expect(html).toContain('class="test-result is-neutral" id="storage-test-line"');
    expect(html).not.toMatch(/id="storage-test-line"><svg[^>]*is-spinning/);
    expect(html).toContain("Save both key pairs, read and write and read-only, before testing.");
  });

  it("the announced line and its time are two sentences (a space between them)", () => {
    expect(testCard({ result: PASSED })).toContain(
      'Passed in 412 ms.</span> <span class="test-result__when num">Tested 2 November 2026',
    );
  });

  it("refused: busy is information, the others are failures, in 13's words", () => {
    const busy = testCard({ failure: new ApiError("POST", "/api/storage/test", 409, "busy") });
    expect(busy).toContain('class="test-result is-info"');
    expect(busy).toContain("A test of the bucket is already running.");
    const locked = testCard({ failure: new ApiError("POST", "/api/storage/test", 503, "secrets_unavailable") });
    expect(locked).toContain('class="test-result is-danger"');
    expect(locked).toContain("Windows Credential Manager couldn't be used. Check the keys and try again.");
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
          result: importedLine({ stores: 2, settings: 12, secrets: 9, encrypted: true }),
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

  it("a finished plain import: 13's plain line, then the restart (m2.5b round 1)", () => {
    const html = markup(
      h(ImportSection, {
        state: importState({
          result: importedLine({ stores: 2, settings: 12, secrets: 0, encrypted: false }),
          resultFile: FILE,
        }),
        handlers: importHandlers,
      }),
    );
    expect(html).toContain(
      "This file holds no keys: add each store's keys and the S3 keys yourself. Restart ShelfSync to apply the imported settings.",
    );
  });

  it("FileText marks the file's name once, and leaves a line without it alone", () => {
    expect(markup(h(FileText, { text: `${FILE} is encrypted.`, name: FILE }))).toBe(
      `<span class="mono file-name">${FILE}</span> is encrypted.`,
    );
    expect(markup(h(FileText, { text: B.needsEmpty, name: FILE }))).toBe(B.needsEmpty);
  });
});
