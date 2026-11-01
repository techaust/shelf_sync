// Every owner-facing string of Settings › Storage (UI-SET; SET-02), with where it comes from:
// - "13": docs/13-content.md section 3, the row "Storage settings (M2.3)" (with the shared `secrets_unavailable`);
// - "13 M2.5a": the row "Settings › Stores, HealthArea and Help guides (M2.5a)" (the key pair's shared words);
// - "13 M1b.4": the row "Settings screens (M1b.4)" (the save, refusal and no-answer patterns);
// - "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js, storagePage());
// - "brief": docs/runs/m2.5b-storage-backup-screens.md section 1;
// - "proposed (m2.5b)": new in this task, listed in that run file's section 3 for the lead;
// - "13 Test": the row "Storage Test (M2.7)", and section 6's "Storage Test, and the wizard's Test step" (the hint);
// - "proposed (T2)": new with the Test button, listed in docs/runs/t2-storage-test-screen.md section 4 for the lead.

import type { S3Slot, StorageTestStep } from "../../api/storage";

type Step = StorageTestStep["step"];
type Reason = NonNullable<StorageTestStep["reason"]>;

/** What a reason sentence may name: the failing step's key ("read and write" / "read-only"), the region the test ran
 *  against, and the step's S3 error code and HTTP status (either can be null). */
export interface ReasonFacts {
  key: string;
  region: string;
  code: string | null;
  status: number | null;
}

/** 13 Test: the reason after "Failed at the <step> step: ". The forms without a code or a status are proposed (T2)
 *  where 13 has none (`refused` with no status, `server_error` with no status). */
const REASONS: Record<Reason, (facts: ReasonFacts) => string> = {
  access_denied: ({ key }) => `the ${key} key got AccessDenied.`,
  key_unknown: ({ key }) => `the ${key} key ID isn't known to the storage service (InvalidAccessKeyId).`,
  secret_wrong: ({ key }) => `the ${key} secret key doesn't match its key ID (SignatureDoesNotMatch).`,
  clock_wrong: () =>
    "this PC's clock is too far off (RequestTimeTooSkewed). Turn on Set time automatically in Windows, then test again.",
  bucket_missing: () => "the bucket doesn't exist (NoSuchBucket). Check its name and region.",
  wrong_region: ({ region, code }) =>
    code
      ? `the bucket isn't in ${region} (${code}). Check the region.`
      : `the bucket isn't in ${region}. Check the region.`,
  not_found: ({ code }) =>
    code ? `the test file wasn't there when read back (${code}).` : "the test file wasn't there when read back.",
  mismatch: () => "the file read back wasn't the one written.",
  confirm_forbidden: () =>
    "the read and write key can't check that the file is gone (HTTP 403). Its policy needs s3:ListBucket on the bucket.",
  still_there: () => "the test file was still there after it was deleted.",
  refused: ({ code, status }) => {
    const said = [code, status === null ? null : `HTTP ${status}`].filter(Boolean).join(", ");
    return said ? `the storage service refused it (${said}).` : "the storage service refused it.";
  },
  server_error: ({ status }) =>
    status === null
      ? "the storage service had an error. Try again in a few minutes."
      : `the storage service had an error (HTTP ${status}). Try again in a few minutes.`,
  unreachable: () => "couldn't reach the storage service. Check the endpoint and your internet connection.",
  timeout: () => "the storage service took too long to answer.",
  tls_error: () => "the storage service's security certificate wasn't accepted.",
  bad_response: () => "the storage service's answer wasn't what ShelfSync expected.",
};

export const ST = {
  // the card
  titleAws: "Amazon S3", // mockup
  titleOther: "S3-compatible storage", // proposed (m2.5b): the endpoint names another service
  emptyText: "Add the S3 bucket ShelfSync uploads to.", // mockup
  emptySub: "You need its name, region and two access keys: one that can write, one read-only.", // mockup
  add: "Add storage", // mockup
  // the five settings (13; labels and two hints from the mockup)
  endpoint: "Endpoint",
  endpointHint:
    "Leave empty to use Amazon S3. For another S3-compatible service, give its address starting with https://.",
  endpointError: "Use an address that starts with https://. http:// only works for this PC (127.0.0.1 or localhost).",
  region: "Region",
  regionHint: "Region, for example ap-south-1.",
  regionError:
    "Use lowercase letters, digits and hyphens, 2 to 32 characters, not only digits, and not starting or ending with a hyphen.",
  bucket: "Bucket",
  bucketHint: "The S3 bucket ShelfSync uploads to.",
  bucketError:
    "Use a valid bucket name: 3 to 63 lowercase letters, digits, dots or hyphens, starting and ending with a letter or digit.",
  keep: "Previous files to keep",
  keepUnit: "per slot", // mockup
  keepHint: "Kept for rollback. Older files are deleted only after every store succeeded.", // mockup
  keepError: "Use a number from 1 to 5.",
  template: "Download link template",
  /** mockup: "{key}" is shown in mono, so the hint is in two parts around it. */
  templateHint: ["What each store's download points at. ", "{key}", " becomes the file name."] as const,
  templateError: "The template must contain {key} exactly once, on one line, in 200 characters or fewer.",
  save: "Save storage", // mockup pattern ("Save app")
  saved: "Storage settings saved.", // 13
  // 13 M1b.4 patterns, for the storage settings
  saveFailed: "ShelfSync didn't answer, so the storage settings may not have been saved. Reload this page to check.",
  saveRefused: (status: number) => `ShelfSync refused the storage settings (HTTP ${status}), so nothing was saved.`,
  loadFailed: "ShelfSync didn't answer, so the storage settings can't be shown.",
  loadRefused: (status: number) => `ShelfSync refused to show the storage settings (HTTP ${status}).`,
  staleNotice: "ShelfSync didn't answer just now, so this may be out of date.", // 13 M1b.4
  tryAgain: "Try again",

  // the two key pairs
  keysTitle: "Access keys", // proposed (m2.5b): the section's heading
  keysHint: "Kept in Windows Credential Manager. They're never shown again or sent to this page.", // 13 M2.5a
  legend: { rw: "Read and write", ro: "Read only" } satisfies Record<S3Slot, string>, // brief
  purpose: {
    rw: "Uploads new files and deletes old ones.", // proposed (m2.5b)
    ro: "Only reads files back, to check them.", // proposed (m2.5b)
  } satisfies Record<S3Slot, string>,
  keyId: "Access key ID", // mockup
  secret: "Secret access key", // mockup
  placeholder: "Paste the new value", // mockup
  keyIdError: "A key ID has 16 to 128 letters and digits.", // 13
  secretError: "A secret key has 16 to 128 letters, digits and / + = characters.", // 13
  pairError: "Enter both the key ID and the secret key.", // 13
  notSet: "Not set", // 13
  unreadable: "Couldn't be read", // 13
  replace: "Replace keys", // 13 M2.5a
  cancel: "Cancel",
  saveKeys: "Save keys", // proposed (m2.5b)
  removeKeys: "Remove keys", // proposed (m2.5b)
  keysSaved: "Keys saved.", // 13
  keysRemoved: "Keys removed.", // 13
  secretsUnavailable: "Windows Credential Manager couldn't be used. Check the keys and try again.", // 13 (shared)
  keysSaveFailed: "ShelfSync didn't answer, so the keys may not have been saved. Reload this page to check.",
  keysRemoveFailed: "ShelfSync didn't answer, so the keys may not have been removed. Reload this page to check.",
  keysRefused: (status: number) => `ShelfSync refused the keys (HTTP ${status}), so nothing was changed.`,
  // the Remove dialog (proposed (m2.5b))
  removeTitle: { rw: "Remove the read and write keys?", ro: "Remove the read-only keys?" } satisfies Record<
    S3Slot,
    string
  >,
  removeLead: "ShelfSync deletes this key pair from Windows Credential Manager at once.",
  removeNote: {
    rw: "Nothing can be uploaded to the bucket until a new read and write pair is saved here.",
    ro: "Files can't be read back from the bucket until a new read-only pair is saved here.",
  } satisfies Record<S3Slot, string>,

  // the Test (m2.7; T2)
  test: "Test connection", // mockup
  testing: "Testing the bucket. This can take up to a minute.", // proposed (T2), after 13 M2.5a's store line
  notTested: "Not tested yet.", // 13 M2.5a (shared with the stores)
  testedAt: (when: string) => `Tested ${when}.`, // 13 M2.5a (shared with the stores)
  passed: (ms: string) => `Passed in ${ms} ms.`, // 13 Test
  failedAt: (step: Step, reason: string) => `Failed at the ${step} step: ${reason}`, // 13 Test
  failedAtNoReason: (step: Step) => `Failed at the ${step} step.`, // proposed (T2): a failed step with no reason
  failedUnknown: "The test failed.", // 13 M2.5a: a failed answer with no failed step
  reason: (reason: Reason, facts: ReasonFacts) => REASONS[reason](facts),
  /** The key pair's word inside a reason or a step: "the read-only key got AccessDenied." (13 Test) */
  keyWord: { rw: "read and write", ro: "read-only" } satisfies Record<S3Slot, string>,
  /** mockup s3Steps(): each step and the key it uses ("Write a test file with the read and write key"). */
  stepsLabel: "Test steps", // mockup
  stepWhat: { write: "Write a test file", read: "Read it back", delete: "Delete it" } satisfies Record<Step, string>,
  stepKey: (key: string) => `with the ${key} key`, // mockup
  stepPassed: "Passed", // 13 Test
  stepFailed: (said: string | null) => (said ? `Failed: ${said}` : "Failed"), // 13 Test; "Failed" alone proposed (T2)
  stepNotRun: "Not run", // 13 Test
  /** 13 Test, left behind: the key is shown in IBM Plex Mono, so the line is in two parts around it. */
  leftBehind: ["The test file ", " may still be in the bucket. You can delete it in the S3 console."] as const,
  // why the button can't test yet (13 Test, the API's own words), and what it tests when the form has changes
  storageNotSet: "Region and bucket must be filled in and saved before the bucket can be tested.", // 13 Test
  keysMissing: "Save both key pairs, read and write and read-only, before testing.", // 13 Test
  testBusy: "A test of the bucket is already running.", // 13 Test
  unsaved: "The test uses the saved settings. Save your changes to test them.", // proposed (T2)
  testRefused: (status: number) => `ShelfSync refused the test (HTTP ${status}).`, // 13 M2.5a pattern (stores)
  testNoAnswer: "ShelfSync didn't answer, so the test may not have finished. Test again to check.", // proposed (T2)
  /** 13 section 6: "shelfsync-test/" is shown in IBM Plex Mono, so the hint is in three parts. */
  testHint: [
    "ShelfSync writes a tiny test file under ",
    "shelfsync-test/",
    " with the read and write key, reads it back with the read-only key, then deletes it: about 4 small S3 requests, a tiny AWS charge.",
  ] as const,
  guide: "S3 access policy guide", // mockup
};
