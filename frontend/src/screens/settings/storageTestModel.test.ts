// SET-02, ERR-03: the Storage Test without React. Whether the saved settings and keys can be tested and why not, every
// reason of docs/13-content.md's row "Storage Test (M2.7)" with its key word and region (and the forms for a null
// `aws_code` and a null `http_status`), the step words, the left-behind key, and the refused and unanswered tests.
import { describe, expect, it } from "vitest";
import { ApiError, ApiUnreachableError } from "../../api/client";
import type { StorageSettings, StorageTest, StorageTestStep } from "../../api/storage";
import { STORAGE_TEST_IDLE } from "../../lib/storageTest";
import {
  planStorageTest,
  storageTestView,
  testAnswerView,
  testedValuesChanged,
  testFailureLine,
} from "./storageTestModel";
import { ST } from "./storageWording";

const SAVED: StorageSettings = {
  s3_endpoint: "",
  s3_region: "ap-south-1",
  s3_bucket: "sample-downloads-bucket",
  keep_previous_files: 2,
  download_link_template: '[amazon_s3 object="{key}"]',
  rw: { access_key_id: "AKIA••••9XYZ", secret_access_key: "••••" },
  ro: { access_key_id: "AKIA••••4QRS", secret_access_key: "••••" },
  keys_readable: true,
};
const NONE = { access_key_id: null, secret_access_key: null };
const WHEN = (iso: string | null | undefined) => (iso ? `at ${iso}` : null);

type Reason = NonNullable<StorageTestStep["reason"]>;
const step = (
  name: StorageTestStep["step"],
  state: StorageTestStep["state"],
  over: Partial<StorageTestStep> = {},
): StorageTestStep => ({
  step: name,
  key_pair: name === "read" ? "ro" : "rw",
  state,
  latency_ms: state === "not_run" ? null : 100,
  reason: null,
  aws_code: null,
  http_status: null,
  ...over,
});
const answer = (steps: StorageTestStep[], over: Partial<StorageTest> = {}): StorageTest => ({
  ok: steps.every((one) => one.state === "passed"),
  tested_at: "2026-11-02T10:00:00Z",
  latency_ms: 412,
  steps,
  left_behind: null,
  ...over,
});
/** The line for one failed step, the others as the server would send them. */
function failedLine(name: StorageTestStep["step"], over: Partial<StorageTestStep>, region = "ap-south-1"): string {
  const steps =
    name === "write"
      ? [step("write", "failed", over), step("read", "not_run"), step("delete", "not_run")]
      : name === "read"
        ? [step("write", "passed"), step("read", "failed", over), step("delete", "passed")]
        : [step("write", "passed"), step("read", "passed"), step("delete", "failed", over)];
  return testAnswerView(answer(steps), region, WHEN).line.text;
}

describe("planStorageTest: what the saved settings and keys allow", () => {
  it("can test what is saved, and says so while the form has unsaved changes", () => {
    expect(planStorageTest(SAVED, false)).toEqual({ can: true, note: null });
    expect(planStorageTest(SAVED, true)).toEqual({
      can: true,
      note: "The test uses the saved settings. Save your changes to test them.",
    });
  });

  it("an empty saved region or bucket: 13's storage_not_set line (before the keys)", () => {
    const why = "Region and bucket must be filled in and saved before the bucket can be tested.";
    expect(planStorageTest({ ...SAVED, s3_region: "" }, false)).toEqual({ can: false, why });
    expect(planStorageTest({ ...SAVED, s3_bucket: "" }, true)).toEqual({ can: false, why });
    expect(planStorageTest({ ...SAVED, s3_bucket: "", rw: NONE }, false)).toEqual({ can: false, why });
  });

  it("either key pair Not set, or only half of one: 13's keys_missing line", () => {
    const why = "Save both key pairs, read and write and read-only, before testing.";
    expect(planStorageTest({ ...SAVED, rw: NONE }, false)).toEqual({ can: false, why });
    expect(planStorageTest({ ...SAVED, ro: NONE }, false)).toEqual({ can: false, why });
    expect(
      planStorageTest({ ...SAVED, ro: { access_key_id: "AKIA••••4QRS", secret_access_key: null } }, false),
    ).toEqual({ can: false, why });
  });

  it("keys that couldn't be read are left to the server (secrets_unavailable or keys_missing)", () => {
    expect(planStorageTest({ ...SAVED, keys_readable: false, rw: NONE, ro: NONE }, false)).toEqual({
      can: true,
      note: null,
    });
  });
});

describe("testedValuesChanged: when a save makes the last answer stale", () => {
  it("endpoint, region or bucket changed; not the files to keep or the template", () => {
    expect(testedValuesChanged(SAVED, SAVED)).toBe(false);
    expect(testedValuesChanged(SAVED, { ...SAVED, keep_previous_files: 4, download_link_template: "{key}" })).toBe(
      false,
    );
    expect(testedValuesChanged(SAVED, { ...SAVED, s3_endpoint: "http://127.0.0.1:9000" })).toBe(true);
    expect(testedValuesChanged(SAVED, { ...SAVED, s3_region: "eu-west-1" })).toBe(true);
    expect(testedValuesChanged(SAVED, { ...SAVED, s3_bucket: "other-bucket" })).toBe(true);
  });
});

describe("testAnswerView: a 200 answer, passed or failed", () => {
  it("passed: 13's line with thousands separators, when, and three passed steps in order with their keys", () => {
    const view = testAnswerView(
      answer([step("delete", "passed"), step("write", "passed"), step("read", "passed")], { latency_ms: 2398 }),
      "ap-south-1",
      WHEN,
    );
    expect(view.line).toEqual({ tone: "success", text: "Passed in 2,398 ms." });
    expect(view.when).toBe("Tested at 2026-11-02T10:00:00Z.");
    expect(view.leftBehind).toBeNull();
    expect(view.steps).toEqual([
      { step: "write", what: "Write a test file", key: "with the read and write key", state: "passed", word: "Passed" },
      { step: "read", what: "Read it back", key: "with the read-only key", state: "passed", word: "Passed" },
      { step: "delete", what: "Delete it", key: "with the read and write key", state: "passed", word: "Passed" },
    ]);
  });

  it("a time that isn't one: no 'Tested' line", () => {
    expect(testAnswerView(answer([step("write", "passed")]), "ap-south-1", () => null).when).toBeNull();
  });

  it("failed at write (ERR-03): the reason line, the step's code as its word, the later steps not run", () => {
    const view = testAnswerView(
      answer([
        step("write", "failed", { reason: "access_denied", aws_code: "AccessDenied", http_status: 403 }),
        step("read", "not_run"),
        step("delete", "not_run"),
      ]),
      "ap-south-1",
      WHEN,
    );
    expect(view.line).toEqual({
      tone: "danger",
      text: "Failed at the write step: the read and write key got AccessDenied.",
    });
    expect(view.steps.map((one) => one.word)).toEqual(["Failed: AccessDenied", "Not run", "Not run"]);
  });

  it("the first failed step is the one the line names; the key word is that step's own pair", () => {
    expect(failedLine("read", { reason: "access_denied", aws_code: "AccessDenied", http_status: 403 })).toBe(
      "Failed at the read step: the read-only key got AccessDenied.",
    );
    expect(failedLine("read", { reason: "key_unknown", aws_code: "InvalidAccessKeyId", http_status: 403 })).toBe(
      "Failed at the read step: the read-only key ID isn't known to the storage service (InvalidAccessKeyId).",
    );
    expect(failedLine("write", { reason: "secret_wrong", aws_code: "SignatureDoesNotMatch", http_status: 403 })).toBe(
      "Failed at the write step: the read and write secret key doesn't match its key ID (SignatureDoesNotMatch).",
    );
  });

  it("every reason in 13's words", () => {
    const cases: [Reason, Partial<StorageTestStep>, string][] = [
      [
        "clock_wrong",
        { aws_code: "RequestTimeTooSkewed", http_status: 403 },
        "this PC's clock is too far off (RequestTimeTooSkewed). Turn on Set time automatically in Windows, then test again.",
      ],
      [
        "bucket_missing",
        { aws_code: "NoSuchBucket", http_status: 404 },
        "the bucket doesn't exist (NoSuchBucket). Check its name and region.",
      ],
      [
        "wrong_region",
        { aws_code: "AuthorizationHeaderMalformed", http_status: 400 },
        "the bucket isn't in ap-south-1 (AuthorizationHeaderMalformed). Check the region.",
      ],
      ["wrong_region", { http_status: 301 }, "the bucket isn't in ap-south-1. Check the region."],
      [
        "not_found",
        { aws_code: "NoSuchKey", http_status: 404 },
        "the test file wasn't there when read back (NoSuchKey).",
      ],
      ["not_found", { http_status: 404 }, "the test file wasn't there when read back."],
      ["mismatch", {}, "the file read back wasn't the one written."],
      [
        "confirm_forbidden",
        { http_status: 403 },
        "the read and write key can't check that the file is gone (HTTP 403). Its policy needs s3:ListBucket on the bucket.",
      ],
      ["still_there", { http_status: 200 }, "the test file was still there after it was deleted."],
      [
        "refused",
        { aws_code: "InvalidRequest", http_status: 400 },
        "the storage service refused it (InvalidRequest, HTTP 400).",
      ],
      ["refused", { http_status: 400 }, "the storage service refused it (HTTP 400)."],
      ["refused", { aws_code: "InvalidRequest" }, "the storage service refused it (InvalidRequest)."],
      ["refused", {}, "the storage service refused it."],
      [
        "server_error",
        { http_status: 503 },
        "the storage service had an error (HTTP 503). Try again in a few minutes.",
      ],
      ["server_error", {}, "the storage service had an error. Try again in a few minutes."],
      ["unreachable", {}, "couldn't reach the storage service. Check the endpoint and your internet connection."],
      ["timeout", {}, "the storage service took too long to answer."],
      ["tls_error", {}, "the storage service's security certificate wasn't accepted."],
      ["bad_response", {}, "the storage service's answer wasn't what ShelfSync expected."],
    ];
    for (const [reason, over, words] of cases) {
      expect(failedLine("delete", { reason, ...over })).toBe(`Failed at the delete step: ${words}`);
    }
  });

  it("wrong_region names the region the test ran against", () => {
    expect(failedLine("write", { reason: "wrong_region", http_status: 301 }, "eu-west-1")).toBe(
      "Failed at the write step: the bucket isn't in eu-west-1. Check the region.",
    );
  });

  it("a failed step's word: its code, else its HTTP status, else 'Failed' alone", () => {
    const words = (over: Partial<StorageTestStep>) =>
      testAnswerView(answer([step("write", "failed", { reason: "refused", ...over })]), "r", WHEN).steps[0]?.word;
    expect(words({ aws_code: "AccessDenied", http_status: 403 })).toBe("Failed: AccessDenied");
    expect(words({ http_status: 503 })).toBe("Failed: HTTP 503");
    expect(words({})).toBe("Failed");
  });

  it("a failed step with no reason, and a failed answer with no failed step", () => {
    expect(failedLine("read", {})).toBe("Failed at the read step.");
    const view = testAnswerView(answer([step("write", "passed")], { ok: false }), "r", WHEN);
    expect(view.line).toEqual({ tone: "danger", text: "The test failed." });
  });

  it("left behind: the key, for the view to show in IBM Plex Mono", () => {
    const key = "shelfsync-test/20261102T100000Z-0123456789abcdef0123456789abcdef.txt";
    const view = testAnswerView(
      answer([step("write", "passed"), step("read", "passed"), step("delete", "failed", { reason: "timeout" })], {
        left_behind: key,
      }),
      "r",
      WHEN,
    );
    expect(view.leftBehind).toBe(key);
    expect(ST.leftBehind.join(key)).toBe(
      `The test file ${key} may still be in the bucket. You can delete it in the S3 console.`,
    );
  });
});

describe("testFailureLine: a refused or unanswered test", () => {
  const refused = (code: ConstructorParameters<typeof ApiError>[3], status: number) =>
    testFailureLine(new ApiError("POST", "/api/storage/test", status, code));

  it("409 busy is information; storage_not_set, keys_missing and 503 secrets_unavailable are failures, from 13", () => {
    expect(refused("busy", 409)).toEqual({ tone: "info", text: "A test of the bucket is already running." });
    expect(refused("storage_not_set", 409)).toEqual({
      tone: "danger",
      text: "Region and bucket must be filled in and saved before the bucket can be tested.",
    });
    expect(refused("keys_missing", 409)).toEqual({
      tone: "danger",
      text: "Save both key pairs, read and write and read-only, before testing.",
    });
    expect(refused("secrets_unavailable", 503)).toEqual({
      tone: "danger",
      text: "Windows Credential Manager couldn't be used. Check the keys and try again.",
    });
  });

  it("any other refusal names its status; no answer says the test may not have finished", () => {
    expect(refused("forbidden", 403)).toEqual({ tone: "danger", text: "ShelfSync refused the test (HTTP 403)." });
    expect(refused(null, 500)).toEqual({ tone: "danger", text: "ShelfSync refused the test (HTTP 500)." });
    expect(testFailureLine(new ApiUnreachableError("POST", "/api/storage/test"))).toEqual({
      tone: "danger",
      text: "ShelfSync didn't answer, so the test may not have finished. Test again to check.",
    });
  });
});

describe("storageTestView: what the Test row shows for the tab's test", () => {
  it("not tested yet, running, an answer, a refusal", () => {
    expect(storageTestView(STORAGE_TEST_IDLE, WHEN)).toEqual({
      line: { tone: "neutral", text: "Not tested yet." },
      when: null,
      steps: [],
      leftBehind: null,
    });
    expect(storageTestView({ ...STORAGE_TEST_IDLE, running: true }, WHEN).line).toEqual({
      tone: "neutral",
      text: "Testing the bucket. This can take up to a minute.",
    });
    const passed = storageTestView({ ...STORAGE_TEST_IDLE, result: answer([step("write", "passed")]) }, WHEN);
    expect(passed.line.tone).toBe("success");
    const busy = storageTestView(
      { ...STORAGE_TEST_IDLE, failure: new ApiError("POST", "/api/storage/test", 409, "busy") },
      WHEN,
    );
    expect(busy).toEqual({
      line: { tone: "info", text: "A test of the bucket is already running." },
      when: null,
      steps: [],
      leftBehind: null,
    });
  });
});
