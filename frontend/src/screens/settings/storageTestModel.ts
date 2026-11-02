// The Storage Test without React (SET-02, ERR-03): whether the saved settings and keys can be tested and why not, and
// what an answer, a refusal or no answer reads as, in 13's words (storageWording.ts). Pure, so every case is tested in
// Node (storageTestModel.test.ts). The server checks the same things again and its answer is the one that counts: a
// test this plan lets through and the API refuses gets the API's line.

import { ApiError } from "../../api/client";
import type { StorageSettings, StorageTest, StorageTestStep, StorageValues } from "../../api/storage";
import type { StorageTestEntry, StorageTestRun } from "../../lib/storageTest";
import { n } from "../../lib/storesWording";
import type { WhenFormat } from "../../lib/time";
import { pairState } from "./storageModel";
import { ST } from "./storageWording";

// ---------- before the test ----------

export type StorageTestPlan =
  /** The button tests what is saved; `note` says so when the form above has unsaved changes. */
  | { can: true; note: string | null }
  /** The button is aria-disabled, with the reason beside it (the API would refuse with the same words). */
  | { can: false; why: string };

/**
 * What the Test button may do, from the saved settings (never the form being typed) and the key masks:
 * - an empty region or bucket: 13's `storage_not_set` line;
 * - either key pair "Not set" (only when the keys could be read; "Couldn't be read" is left to the server, which
 *   answers `secrets_unavailable` or `keys_missing`): 13's `keys_missing` line;
 * - otherwise it can test, and says it tests the saved settings while the form has unsaved changes.
 */
export function planStorageTest(saved: StorageSettings, formDirty: boolean): StorageTestPlan {
  if (saved.s3_region === "" || saved.s3_bucket === "") return { can: false, why: ST.storageNotSet };
  if (saved.keys_readable && !(pairState(saved, "rw").set && pairState(saved, "ro").set)) {
    return { can: false, why: ST.keysMissing };
  }
  return { can: true, note: formDirty ? ST.unsaved : null };
}

/** Whether a save changed what the Test uses (endpoint, region, bucket), so its last answer no longer applies. The
 *  number of files to keep and the link template aren't tested, so changing them keeps it. */
export function testedValuesChanged(before: StorageValues, after: StorageValues): boolean {
  return (
    before.s3_endpoint !== after.s3_endpoint ||
    before.s3_region !== after.s3_region ||
    before.s3_bucket !== after.s3_bucket
  );
}

/** What the page does after a settings save: the last answer (or the running test's, marked stale) no longer
 *  applies when the endpoint, region or bucket changed. */
export function afterStorageSaved(
  run: Pick<StorageTestRun, "forget">,
  before: StorageValues,
  after: StorageValues,
): void {
  if (testedValuesChanged(before, after)) run.forget();
}

/** What the page does after a key pair was saved or removed: the last answer was about the old keys. */
export function afterKeysChanged(run: Pick<StorageTestRun, "forget">): void {
  run.forget();
}

// ---------- the answer ----------

export type TestTone = "success" | "danger" | "info" | "neutral";

export interface TestStepLine {
  step: StorageTestStep["step"];
  /** "Write a test file" */
  what: string;
  /** "with the read and write key" */
  key: string;
  state: StorageTestStep["state"];
  /** "Passed" / "Failed: AccessDenied" / "Not run" */
  word: string;
}

export interface StorageTestView {
  /** The one line beside the button. */
  line: { tone: TestTone; text: string };
  /** "Tested <date> at <time> <zone>." once an answer came back. */
  when: string | null;
  /** The three steps, once an answer came back; empty before a test, while it runs and after a refusal. */
  steps: TestStepLine[];
  /** The test file's key when it may still be in the bucket (shown in IBM Plex Mono). */
  leftBehind: string | null;
  /** The answer is about the settings or keys from before a save made while it ran (T2 review 1). */
  stale: string | null;
}

const STEP_ORDER: readonly StorageTestStep["step"][] = ["write", "read", "delete"];

/** The failed step's reason sentence, from its own key pair and the region the test ran against. */
function reasonOf(step: StorageTestStep, region: string): string | null {
  if (step.reason === null) return null;
  return ST.reason(step.reason, {
    key: ST.keyWord[step.key_pair],
    region,
    code: step.aws_code,
    status: step.http_status,
  });
}

/** A failed step's word: its S3 error code, else its HTTP status, else "Failed" alone (the line above says why). */
function failedWord(step: StorageTestStep): string {
  if (step.aws_code) return ST.stepFailed(step.aws_code);
  return ST.stepFailed(step.http_status === null ? null : `HTTP ${step.http_status}`);
}

function stepLine(step: StorageTestStep): TestStepLine {
  const key = ST.keyWord[step.key_pair];
  const word = step.state === "passed" ? ST.stepPassed : step.state === "failed" ? failedWord(step) : ST.stepNotRun;
  return { step: step.step, what: ST.stepWhat[step.step], key: ST.stepKey(key), state: step.state, word };
}

/** A 200 answer, passed or failed: the line, the three steps in their order, and the left-behind key. */
export function testAnswerView(result: StorageTest, region: string, when: WhenFormat): StorageTestView {
  const steps = [...result.steps].sort((a, b) => STEP_ORDER.indexOf(a.step) - STEP_ORDER.indexOf(b.step));
  const failed = steps.find((step) => step.state === "failed");
  let line: StorageTestView["line"];
  if (result.ok) {
    line = { tone: "success", text: ST.passed(n(result.latency_ms)) };
  } else if (failed) {
    const reason = reasonOf(failed, region);
    line = { tone: "danger", text: reason ? ST.failedAt(failed.step, reason) : ST.failedAtNoReason(failed.step) };
  } else {
    line = { tone: "danger", text: ST.failedUnknown };
  }
  const tested = when(result.tested_at);
  return {
    line,
    when: tested ? ST.testedAt(tested) : null,
    steps: steps.map(stepLine),
    leftBehind: result.left_behind,
    stale: null,
  };
}

/** A refused or unanswered test, in 13's words: `busy` is information (a test is running), the rest are failures. */
export function testFailureLine(failure: unknown): StorageTestView["line"] {
  if (failure instanceof ApiError) {
    switch (failure.code) {
      case "busy":
        return { tone: "info", text: ST.testBusy };
      case "storage_not_set":
        return { tone: "danger", text: ST.storageNotSet };
      case "keys_missing":
        return { tone: "danger", text: ST.keysMissing };
      case "secrets_unavailable":
        return { tone: "danger", text: ST.secretsUnavailable };
      default:
        return { tone: "danger", text: ST.testRefused(failure.status) };
    }
  }
  return { tone: "danger", text: ST.testNoAnswer };
}

/** What the Test row shows for the tab's test: running, an answer (with a note when a save came while it ran), a
 *  refusal, or not tested yet. A refusal says nothing about the settings, so it never gets the note. */
export function storageTestView(entry: StorageTestEntry, when: WhenFormat): StorageTestView {
  const nothing = { when: null, steps: [], leftBehind: null, stale: null };
  if (entry.running) return { line: { tone: "neutral", text: ST.testing }, ...nothing };
  if (entry.result) {
    return { ...testAnswerView(entry.result, entry.region, when), stale: entry.stale ? ST.staleAnswer : null };
  }
  if (entry.failure !== null) return { line: testFailureLine(entry.failure), ...nothing };
  return { line: { tone: "neutral", text: ST.notTested }, ...nothing };
}
