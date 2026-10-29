// Every owner-facing string of Settings › Storage (UI-SET; SET-02), with where it comes from:
// - "13": docs/13-content.md section 3, the row "Storage settings (M2.3)" (with the shared `secrets_unavailable`);
// - "13 M2.5a": the row "Settings › Stores, HealthArea and Help guides (M2.5a)" (the key pair's shared words);
// - "13 M1b.4": the row "Settings screens (M1b.4)" (the save, refusal and no-answer patterns);
// - "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js, storagePage());
// - "brief": docs/runs/m2.5b-storage-backup-screens.md section 1;
// - "proposed (m2.5b)": new in this task, listed in that run file's section 3 for the lead.

import type { S3Slot } from "../../api/storage";

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
  regionError: "Use lowercase letters, digits and hyphens, 2 to 32 characters.",
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

  // where the Test button will be (m2.7)
  // brief (m2.0, proposed): "Testing the bucket arrives with the S3 update. Your settings and keys are saved." The
  // second sentence reads as a claim when nothing is saved yet, so this task proposes the line below instead.
  testLater: "Testing the bucket arrives with the S3 update. Until then, settings and keys are saved without a test.",
  testNeeds: "Region and bucket must be filled in before the bucket can be tested.", // 13
  guide: "S3 access policy guide", // mockup
};
