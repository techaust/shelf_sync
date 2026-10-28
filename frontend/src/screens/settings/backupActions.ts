// Export and import, one try each, as plain functions (SET-05): each reads the passphrase from its input, empties the
// input at once (the passphrase leaves the page after every try, accepted, refused or unanswered), checks it, sends,
// and returns what to show. The page only calls them; the tests run every path with fakes (backupActions.test.ts).

import type { ExportedFile, ImportResult } from "../../api/backup";
import {
  checkNewPassphrase,
  checkPassphrase,
  exportError,
  exportedLine,
  type ImportFailure,
  importError,
  importedLine,
  type Line,
} from "./backupModel";

/** A password input as these functions need it (the real element in the page, a plain object in tests). */
export interface SecretInput {
  value: string;
}

/** Empties password inputs. */
export function clearInputs(...inputs: (SecretInput | null | undefined)[]): void {
  for (const input of inputs) if (input) input.value = "";
}

export type ExportOutcome =
  | { kind: "refused"; errors: { first?: string; second?: string } }
  | { kind: "done"; line: Line };

/** One Export settings: with secrets, the two passphrase inputs are read, emptied, checked and sent. */
export async function attemptExport(options: {
  includeSecrets: boolean;
  first: SecretInput | null;
  second: SecretInput | null;
  names: ReadonlyMap<string, string>;
  send: (passphrase: string | null) => Promise<ExportedFile>;
  save: (file: ExportedFile) => void;
  /** Called once the checks passed, just before the request (the page shows the busy button from here). */
  onSend?: () => void;
}): Promise<ExportOutcome> {
  let passphrase: string | null = null;
  if (options.includeSecrets) {
    const first = options.first?.value ?? "";
    const second = options.second?.value ?? "";
    clearInputs(options.first, options.second);
    const refused = checkNewPassphrase(first, second);
    if (refused) return { kind: "refused", errors: refused };
    passphrase = first;
  }
  options.onSend?.();
  try {
    const file = await options.send(passphrase);
    options.save(file);
    return { kind: "done", line: exportedLine(file.fileName, file.leftOut, options.names) };
  } catch (failure) {
    return { kind: "done", line: exportError(failure) };
  }
}

export type ImportOutcome =
  | { kind: "refused"; passphraseError: string }
  | { kind: "imported"; line: Line }
  | { kind: "failed"; failure: ImportFailure };

/** One Import: an encrypted file's passphrase input is read, emptied, checked and sent; a plain file sends none (a
 *  passphrase with a plain file is refused by the API, 11 2026-10-29). */
export async function attemptImport(options: {
  encrypted: boolean | null;
  input: SecretInput | null;
  text: string;
  fileName: string;
  send: (text: string, passphrase: string | null) => Promise<ImportResult>;
  onSend?: () => void;
}): Promise<ImportOutcome> {
  let passphrase: string | null = null;
  if (options.encrypted) {
    const typed = options.input?.value ?? "";
    clearInputs(options.input);
    const refused = checkPassphrase(typed);
    if (refused) return { kind: "refused", passphraseError: refused };
    passphrase = typed;
  }
  options.onSend?.();
  try {
    return { kind: "imported", line: importedLine(await options.send(options.text, passphrase)) };
  } catch (failure) {
    return { kind: "failed", failure: importError(failure, options.fileName) };
  }
}
