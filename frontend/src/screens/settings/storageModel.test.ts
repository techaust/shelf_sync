// SET-02: Settings › Storage's checks with the API's own rules (backend db/settings.py, secure/credentials.py), the key
// pair's trimming, what the card shows (empty, saved, keys unreadable) and where each refusal's 13 line goes.
import { describe, expect, it } from "vitest";
import { ApiError, ApiUnreachableError } from "../../api/client";
import type { StorageSettings } from "../../api/storage";
import {
  bucketOk,
  checkKeyPair,
  checkStorageForm,
  endpointOk,
  firstError,
  pairState,
  regionOk,
  storageDirty,
  storageEmpty,
  storageError,
  storageFormFrom,
  templateOk,
  testLines,
} from "./storageModel";
import { ST } from "./storageWording";

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
const KEY_ID = "AKIASAMPLE0000000001"; // a made-up key ID of the right shape
const SECRET = "sampleSecret/0000+000000000000000000000="; // a made-up secret of the right shape

describe("the endpoint (check_s3_endpoint)", () => {
  it.each([
    "",
    "https://s3.example.com",
    "https://s3.example.com/",
    "https://s3.example.com:8443",
    "https://S3.Example.COM",
    "http://127.0.0.1:9000",
    "http://localhost:4566",
    "https://localhost",
  ])("accepts %s", (value) => expect(endpointOk(value)).toBe(true));

  it.each([
    "s3.example.com",
    "http://s3.example.com",
    "ftp://s3.example.com",
    "https://s3.example.com/bucket",
    "https://s3.example.com?x=1",
    "https://s3.example.com#top",
    "https://user@s3.example.com",
    "https://s3.example.com:",
    "https://s3.example.com:0",
    "https://s3.example.com:70000",
    "https://s3",
    "https://10.0.0.1",
    "https://s3.example.123",
    "https://s3 .example.com",
    "https://s3.exämple.com",
    `https://${"a".repeat(200)}.com`,
  ])("refuses %s", (value) => expect(endpointOk(value)).toBe(false));
});

describe("region, bucket and template", () => {
  it("region: empty, or 2 to 32 lowercase letters, digits and hyphens", () => {
    for (const ok of ["", "ap-south-1", "eu", "a".repeat(32)]) expect(regionOk(ok)).toBe(true);
    for (const bad of ["a", "AP-SOUTH-1", "ap_south_1", "a".repeat(33), "ap south"]) expect(regionOk(bad)).toBe(false);
  });

  it("bucket: S3's naming rules plus RFC 1123", () => {
    for (const ok of ["", "abc", "sample-downloads-bucket", "my.bucket.name", "a".repeat(63)]) {
      expect(bucketOk(ok)).toBe(true);
    }
    for (const bad of [
      "ab",
      "a".repeat(64),
      "Bucket",
      "-bucket",
      "bucket-",
      "my..bucket",
      "my.-bucket",
      "my-.bucket",
      "192.168.1.1",
      "xn--bucket",
      "sthree-bucket",
      "amzn-s3-demo-bucket",
      "bucket-s3alias",
      "bucket--ol-s3",
      "bucket.mrap",
      "bucket--x-s3",
      "bucket--table-s3",
    ]) {
      expect(bucketOk(bad), bad).toBe(false);
    }
  });

  it("template: {key} exactly once, no other brace, one line, 200 characters or fewer", () => {
    for (const ok of [
      '[amazon_s3 object="{key}"]',
      "https://files.example/{key}",
      "{key}",
      `${"a".repeat(195)}{key}`,
    ]) {
      expect(templateOk(ok)).toBe(true);
    }
    for (const bad of [
      "no key here",
      "{key}{key}",
      "{key} {0}",
      "{key}}",
      "{{key}",
      "line\n{key}",
      "tab\t{key}",
      `${"a".repeat(196)}{key}`,
    ]) {
      expect(templateOk(bad), bad).toBe(false);
    }
  });
});

describe("the settings form", () => {
  it("saves all five, with spaces around endpoint, region and bucket dropped", () => {
    const form = { ...storageFormFrom(SAVED), region: " ap-south-1 ", bucket: "sample-downloads-bucket\t", keep: "3" };
    expect(checkStorageForm(form)).toEqual({
      values: {
        s3_endpoint: "",
        s3_region: "ap-south-1",
        s3_bucket: "sample-downloads-bucket",
        keep_previous_files: 3,
        download_link_template: '[amazon_s3 object="{key}"]',
      },
      errors: null,
    });
  });

  it("empty region and bucket are allowed (11, 2026-10-28)", () => {
    expect(checkStorageForm(storageFormFrom(EMPTY)).errors).toBeNull();
  });

  it("each field has its 13 error, and the first one takes the focus", () => {
    const checked = checkStorageForm({
      endpoint: "http://s3.example.com",
      region: "AP",
      bucket: "x",
      keep: "6",
      template: "nothing",
    });
    expect(checked.errors).toEqual({
      endpoint: ST.endpointError,
      region: ST.regionError,
      bucket: ST.bucketError,
      keep: ST.keepError,
      template: ST.templateError,
    });
    expect(firstError(checked.errors ?? {})).toBe("endpoint");
    expect(firstError({ keep: ST.keepError, template: ST.templateError })).toBe("keep");
  });

  it("previous files to keep: 1 to 5, digits only", () => {
    for (const keep of ["1", "5", " 2 "])
      expect(checkStorageForm({ ...storageFormFrom(EMPTY), keep }).errors).toBeNull();
    for (const keep of ["0", "6", "1.5", "-1", "", "two"]) {
      expect(checkStorageForm({ ...storageFormFrom(EMPTY), keep }).errors).toEqual({ keep: ST.keepError });
    }
  });

  it("Save is off until something changed", () => {
    expect(storageDirty(storageFormFrom(SAVED), SAVED)).toBe(false);
    expect(storageDirty({ ...storageFormFrom(SAVED), bucket: "other-bucket" }, SAVED)).toBe(true);
  });
});

describe("the key pairs", () => {
  it("trims spaces around a pasted key ID and secret (an AWS CSV copy)", () => {
    expect(checkKeyPair(`  ${KEY_ID} `, `\t${SECRET}  `)).toEqual({
      pair: { accessKeyId: KEY_ID, secretAccessKey: SECRET },
      errors: null,
    });
  });

  it("both halves or nothing", () => {
    expect(checkKeyPair(KEY_ID, "")).toEqual({ pair: null, errors: { pair: ST.pairError } });
    expect(checkKeyPair("   ", SECRET)).toEqual({ pair: null, errors: { pair: ST.pairError } });
  });

  it("each half has its shape (16 to 128; the secret also / + =)", () => {
    expect(checkKeyPair("AKIA-SAMPLE-00000001", SECRET).errors).toEqual({ first: ST.keyIdError });
    expect(checkKeyPair(KEY_ID, "short").errors).toEqual({ second: ST.secretError });
    expect(checkKeyPair("A".repeat(129), "s".repeat(129)).errors).toEqual({
      first: ST.keyIdError,
      second: ST.secretError,
    });
    expect(checkKeyPair("A".repeat(16), "s/+=".repeat(4)).errors).toBeNull();
  });

  it("what a pair shows: masks when saved, Not set when not, unknown when Credential Manager couldn't be read", () => {
    expect(pairState(SAVED, "rw")).toEqual({ set: true, masks: { first: "AKIA••••9XYZ", second: "••••" } });
    expect(pairState(EMPTY, "ro")).toEqual({ set: false, masks: { first: null, second: null } });
    // unreadable: the nulls mean "unknown", never "not set"; the view shows "Couldn't be read"
    expect(pairState({ ...EMPTY, keys_readable: false }, "rw").set).toBe(false);
  });
});

describe("the page's states", () => {
  it("empty only when nothing was put in and the keys are known to be missing", () => {
    expect(storageEmpty(EMPTY)).toBe(true);
    expect(storageEmpty(SAVED)).toBe(false);
    expect(storageEmpty({ ...EMPTY, s3_bucket: "sample-downloads-bucket" })).toBe(false);
    expect(storageEmpty({ ...EMPTY, s3_endpoint: "http://127.0.0.1:9000" })).toBe(false);
    expect(storageEmpty({ ...EMPTY, ro: { access_key_id: "AKIA••••4QRS", secret_access_key: "••••" } })).toBe(false);
    expect(storageEmpty({ ...EMPTY, keys_readable: false })).toBe(false);
  });

  it("where the Test will be: 13's line only while region or bucket is empty", () => {
    expect(testLines(SAVED)).toEqual([ST.testLater]);
    expect(testLines(EMPTY)).toEqual([ST.testLater, ST.testNeeds]);
    expect(testLines({ ...SAVED, s3_region: "" })).toEqual([ST.testLater, ST.testNeeds]);
    expect(ST.testNeeds).toBe("Region and bucket must be filled in before the bucket can be tested.");
  });

  it("refusals and silence: 13's lines", () => {
    const refused = (code: "secrets_unavailable" | "invalid_request" | null, status: number) =>
      new ApiError("PUT", "/api/secrets/s3-rw", status, code);
    expect(storageError(refused("secrets_unavailable", 503), "keys")).toBe(
      "Windows Credential Manager couldn't be used. Check the keys and try again.",
    );
    expect(storageError(refused("secrets_unavailable", 503), "remove")).toBe(ST.secretsUnavailable);
    expect(storageError(refused("invalid_request", 422), "keys")).toBe(
      "ShelfSync refused the keys (HTTP 422), so nothing was changed.",
    );
    expect(storageError(refused("invalid_request", 422), "settings")).toBe(
      "ShelfSync refused the storage settings (HTTP 422), so nothing was saved.",
    );
    const silent = new ApiUnreachableError("PUT", "/api/settings/storage");
    expect(storageError(silent, "settings")).toBe(ST.saveFailed);
    expect(storageError(silent, "keys")).toBe(ST.keysSaveFailed);
    expect(storageError(silent, "remove")).toBe(ST.keysRemoveFailed);
  });
});
