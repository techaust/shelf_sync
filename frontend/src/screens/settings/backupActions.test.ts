// SET-05: one export and one import try, with fakes for the API and the inputs. The passphrase is emptied from its
// input after every try (a check that fails, an accepted request, a refusal, no answer), sent only in the body, and
// a plain file never carries one.
import { describe, expect, it, vi } from "vitest";
import type { ExportedFile, ImportResult } from "../../api/backup";
import { ApiError, ApiUnreachableError } from "../../api/client";
import { attemptExport, attemptImport, clearInputs } from "./backupActions";
import { B } from "./backupWording";

const PASSPHRASE = "sample passphrase for tests"; // made up, 27 characters
const FILE: ExportedFile = {
  blob: new Blob(['{"format":"shelfsync-export"}'], { type: "application/json" }),
  fileName: "shelfsync-export-2026-10-29.ssbak",
  leftOut: null,
};
const NAMES = new Map([["GF", "GPLFamily"]]);
const input = (value = "") => ({ value });

describe("export", () => {
  it("without secrets: sends null, saves the file, says so", async () => {
    const send = vi.fn(async () => FILE);
    const save = vi.fn();
    const outcome = await attemptExport({ includeSecrets: false, first: null, second: null, names: NAMES, send, save });
    expect(send).toHaveBeenCalledWith(null);
    expect(save).toHaveBeenCalledWith(FILE);
    expect(outcome).toEqual({ kind: "done", line: { tone: "success", text: `Exported ${FILE.fileName}.` } });
  });

  it("with secrets: sends the passphrase and empties both inputs", async () => {
    const first = input(PASSPHRASE);
    const second = input(PASSPHRASE);
    const send = vi.fn(async () => FILE);
    const onSend = vi.fn();
    await attemptExport({ includeSecrets: true, first, second, names: NAMES, send, save: vi.fn(), onSend });
    expect(send).toHaveBeenCalledWith(PASSPHRASE);
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(first.value).toBe("");
    expect(second.value).toBe("");
  });

  it("a passphrase that fails the check is emptied too, and nothing is sent", async () => {
    for (const [a, b, errors] of [
      ["short", "short", { first: B.passphraseError }],
      [PASSPHRASE, `${PASSPHRASE}!`, { second: B.passphraseMismatch }],
    ] as const) {
      const first = input(a);
      const second = input(b);
      const send = vi.fn(async () => FILE);
      const onSend = vi.fn();
      const outcome = await attemptExport({
        includeSecrets: true,
        first,
        second,
        names: NAMES,
        send,
        save: vi.fn(),
        onSend,
      });
      expect(outcome).toEqual({ kind: "refused", errors });
      expect(send).not.toHaveBeenCalled();
      expect(onSend).not.toHaveBeenCalled(); // a refused value never shows the busy button
      expect([first.value, second.value]).toEqual(["", ""]);
    }
  });

  it("a refusal or no answer: the inputs are empty and the line says why", async () => {
    for (const failure of [
      new ApiError("POST", "/api/backup/export", 503, "secrets_unavailable"),
      new ApiUnreachableError("POST", "/api/backup/export"),
    ]) {
      const first = input(PASSPHRASE);
      const second = input(PASSPHRASE);
      const save = vi.fn();
      const outcome = await attemptExport({
        includeSecrets: true,
        first,
        second,
        names: NAMES,
        send: async () => {
          throw failure;
        },
        save,
      });
      expect(save).not.toHaveBeenCalled();
      expect(outcome.kind).toBe("done");
      expect([first.value, second.value]).toEqual(["", ""]);
    }
  });

  it("the left-out line, with the store's name", async () => {
    const outcome = await attemptExport({
      includeSecrets: true,
      first: input(PASSPHRASE),
      second: input(PASSPHRASE),
      names: NAMES,
      send: async () => ({ ...FILE, leftOut: { stores: ["GF"], s3: [], github: false } }),
      save: vi.fn(),
    });
    expect(outcome).toEqual({
      kind: "done",
      line: {
        tone: "warning",
        text: `Exported ${FILE.fileName}, but left out the keys of GPLFamily: ShelfSync couldn't read them in a usable form. Save them again, then export again.`,
      },
    });
  });
});

describe("import", () => {
  const TEXT = '{"format":"shelfsync-export","encryption":null}';
  const DONE: ImportResult = { stores: 2, settings: 12, secrets: 9, encrypted: true };

  it("a plain file sends no passphrase (one would be refused)", async () => {
    const send = vi.fn(async () => ({ ...DONE, secrets: 0, encrypted: false }));
    const outcome = await attemptImport({
      encrypted: false,
      input: input("left over"),
      text: TEXT,
      fileName: "a.ssbak",
      send,
    });
    expect(send).toHaveBeenCalledWith(TEXT, null);
    expect(outcome.kind).toBe("imported");
  });

  it("an encrypted file: the passphrase is sent and emptied, and the result is 13's", async () => {
    const field = input(PASSPHRASE);
    const send = vi.fn(async () => DONE);
    const outcome = await attemptImport({ encrypted: true, input: field, text: TEXT, fileName: "a.ssbak", send });
    expect(send).toHaveBeenCalledWith(TEXT, PASSPHRASE);
    expect(field.value).toBe("");
    expect(outcome).toEqual({
      kind: "imported",
      line: {
        tone: "success",
        text: "Imported 2 stores, 12 settings and 9 keys. Restart ShelfSync to apply the imported settings.",
      },
    });
  });

  it("a wrong passphrase: emptied, 'Nothing was imported.', focus back to it", async () => {
    const field = input(PASSPHRASE);
    const outcome = await attemptImport({
      encrypted: true,
      input: field,
      text: TEXT,
      fileName: "shelfsync-export-2026-10-29.ssbak",
      send: async () => {
        throw new ApiError("POST", "/api/backup/import", 422, "wrong_passphrase");
      },
    });
    expect(field.value).toBe("");
    expect(outcome).toEqual({
      kind: "failed",
      failure: {
        tone: "danger",
        text: "Can't open shelfsync-export-2026-10-29.ssbak: the passphrase doesn't match. Nothing was imported.",
        passphrase: "wrong",
      },
    });
  });

  it("a passphrase too short is emptied and nothing is sent", async () => {
    const field = input("short");
    const send = vi.fn(async () => DONE);
    const outcome = await attemptImport({ encrypted: true, input: field, text: TEXT, fileName: "a.ssbak", send });
    expect(outcome).toEqual({ kind: "refused", passphraseError: B.passphraseError });
    expect(send).not.toHaveBeenCalled();
    expect(field.value).toBe("");
  });

  it("clearInputs skips what isn't there", () => {
    const one = input("x");
    clearInputs(one, null, undefined);
    expect(one.value).toBe("");
  });
});
