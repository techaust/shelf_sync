// Settings › Storage without React (SET-02): the form's checks, with the API's own rules (backend db/settings.py and
// secure/credentials.py), the key pair's trimming and checks, what the card shows, and where each refusal goes. Pure,
// so every rule is tested in Node (storageModel.test.ts). The server's answer is still the one that counts: a value
// these checks let through and the API refuses gets the general refusal line.

import { ApiError } from "../../api/client";
import type { S3Slot, StorageSettings, StorageValues } from "../../api/storage";
import { inRange } from "./forms";
import { ST } from "./storageWording";

/** db/settings.py: KEEP_PREVIOUS_MIN/MAX, LINK_TEMPLATE_MAX, S3_ENDPOINT_MAX; api/storage.py: the field caps. */
export const KEEP_MIN = 1;
export const KEEP_MAX = 5;
export const TEMPLATE_MAX = 200;
export const ENDPOINT_MAX = 200;
export const REGION_MAX = 32;
export const BUCKET_MAX = 63;
/** A pasted value may carry spaces around it, so the input allows a little more than the API's 128. */
export const KEY_INPUT_MAX = 160;

const REGION = /^[a-z0-9-]{2,32}$/;
const BUCKET = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;
const IPV4_SHAPE = /^[0-9]{1,3}(\.[0-9]{1,3}){3}$/;
const BUCKET_PREFIXES = ["xn--", "sthree-", "amzn-s3-demo-"];
const BUCKET_SUFFIXES = ["-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3"];
const DNS_HOST = /^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;
const LOOPBACK_HOSTS = ["127.0.0.1", "localhost"];
/** secure/credentials.py S3_KEY_ID and S3_SECRET. */
const KEY_ID = /^[A-Za-z0-9]{16,128}$/;
const SECRET = /^[A-Za-z0-9/+=]{16,128}$/;

/** The form as typed: every field is text until it is checked. */
export interface StorageForm {
  endpoint: string;
  region: string;
  bucket: string;
  keep: string;
  template: string;
}

export type StorageField = keyof StorageForm;
export type StorageErrors = Partial<Record<StorageField, string>>;

/** The order the fields are shown and checked in, so the first invalid one takes the focus. */
export const STORAGE_FIELDS: readonly StorageField[] = ["endpoint", "region", "bucket", "keep", "template"];

export function storageFormFrom(values: StorageValues): StorageForm {
  return {
    endpoint: values.s3_endpoint,
    region: values.s3_region,
    bucket: values.s3_bucket,
    keep: String(values.keep_previous_files),
    template: values.download_link_template,
  };
}

/** check_s3_endpoint: "" is Amazon S3; otherwise https to a named host, or http(s) to 127.0.0.1 or localhost only;
 *  no user information, query, fragment, empty port or path beyond "/". */
export function endpointOk(value: string): boolean {
  if (value === "") return true;
  if (value.length > ENDPOINT_MAX || !/^[\x21-\x7e]+$/.test(value)) return false;
  if (/[?#\\]/.test(value) || !/^https?:\/\//.test(value)) return false;
  const rest = value.slice(value.indexOf("//") + 2);
  const slash = rest.indexOf("/");
  const authority = slash === -1 ? rest : rest.slice(0, slash);
  const path = slash === -1 ? "" : rest.slice(slash);
  if (authority === "" || authority.includes("@") || authority.endsWith(":") || (path !== "" && path !== "/")) {
    return false;
  }
  const port = /:([0-9]+)$/.exec(authority)?.[1];
  if (port !== undefined && !(Number(port) >= 1 && Number(port) <= 65535)) return false;
  let host: string;
  try {
    host = new URL(value).hostname;
  } catch {
    return false;
  }
  if (LOOPBACK_HOSTS.includes(host)) return true;
  const last = host.split(".").pop() ?? "";
  return value.startsWith("https://") && DNS_HOST.test(host) && /[a-z]/.test(last);
}

export const regionOk = (value: string): boolean => value === "" || REGION.test(value);

/** check_s3_bucket: S3's naming rules, plus no ".-" or "-." (RFC 1123). */
export function bucketOk(value: string): boolean {
  if (value === "") return true;
  return (
    BUCKET.test(value) &&
    !["..", ".-", "-."].some((bad) => value.includes(bad)) &&
    !IPV4_SHAPE.test(value) &&
    !BUCKET_PREFIXES.some((prefix) => value.startsWith(prefix)) &&
    !BUCKET_SUFFIXES.some((suffix) => value.endsWith(suffix))
  );
}

/** check_link_template: {key} exactly once, no other brace, printable, at most 200 characters (Python counts code
 *  points, so this does too). */
export function templateOk(value: string): boolean {
  const rest = value.replace("{key}", "");
  const printable = !/[\p{C}\p{Zl}\p{Zp}]/u.test(value) && !/\p{Zs}/u.test(value.replaceAll(" ", ""));
  return (
    [...value].length <= TEMPLATE_MAX &&
    value.split("{key}").length === 2 &&
    !rest.includes("{") &&
    !rest.includes("}") &&
    printable
  );
}

/** The PUT body (all five, as the API requires), or the errors to show. Spaces around the endpoint, region and
 *  bucket are dropped (none of them can hold a space); the template is sent as typed. */
export function checkStorageForm(
  form: StorageForm,
): { values: StorageValues; errors: null } | { values: null; errors: StorageErrors } {
  const endpoint = form.endpoint.trim();
  const region = form.region.trim();
  const bucket = form.bucket.trim();
  const keep = inRange(form.keep, KEEP_MIN, KEEP_MAX);
  const errors: StorageErrors = {};
  if (!endpointOk(endpoint)) errors.endpoint = ST.endpointError;
  if (!regionOk(region)) errors.region = ST.regionError;
  if (!bucketOk(bucket)) errors.bucket = ST.bucketError;
  if (keep === null) errors.keep = ST.keepError;
  if (!templateOk(form.template)) errors.template = ST.templateError;
  if (Object.keys(errors).length > 0 || keep === null) return { values: null, errors };
  return {
    values: {
      s3_endpoint: endpoint,
      s3_region: region,
      s3_bucket: bucket,
      keep_previous_files: keep,
      download_link_template: form.template,
    },
    errors: null,
  };
}

export function firstError(errors: StorageErrors): StorageField | null {
  return STORAGE_FIELDS.find((field) => errors[field]) ?? null;
}

/** Whether the form differs from what is stored (Save says so with aria-disabled when it doesn't). */
export function storageDirty(form: StorageForm, stored: StorageValues): boolean {
  const saved = storageFormFrom(stored);
  return STORAGE_FIELDS.some((field) => form[field] !== saved[field]);
}

// ---------- the key pairs ----------

export interface KeyPairErrors {
  pair?: string;
  first?: string;
  second?: string;
}

/**
 * The pair to send, trimmed (an AWS CSV copy often carries spaces), or the errors. Both halves go together or not at
 * all (13: "Enter both the key ID and the secret key.").
 */
export function checkKeyPair(
  typedId: string,
  typedSecret: string,
): { pair: { accessKeyId: string; secretAccessKey: string }; errors: null } | { pair: null; errors: KeyPairErrors } {
  const accessKeyId = typedId.trim();
  const secretAccessKey = typedSecret.trim();
  if (!accessKeyId || !secretAccessKey) return { pair: null, errors: { pair: ST.pairError } };
  const errors: KeyPairErrors = {};
  if (!KEY_ID.test(accessKeyId)) errors.first = ST.keyIdError;
  if (!SECRET.test(secretAccessKey)) errors.second = ST.secretError;
  if (errors.first || errors.second) return { pair: null, errors };
  return { pair: { accessKeyId, secretAccessKey }, errors: null };
}

/** What one key pair's row shows: the API's masks, "Not set", or "Couldn't be read" (11, 2026-10-28). */
export function pairState(
  storage: StorageSettings,
  slot: S3Slot,
): { set: boolean; masks: { first: string | null; second: string | null } } {
  const masks = storage[slot];
  return {
    set: storage.keys_readable && masks.access_key_id !== null && masks.secret_access_key !== null,
    masks: { first: masks.access_key_id, second: masks.secret_access_key },
  };
}

/** Storage that nothing has been put into yet: no region, no bucket, no keys (and the keys could be read, so "no
 *  keys" is known). The page starts with the mockup's empty state then. */
export function storageEmpty(storage: StorageSettings): boolean {
  const none = (slot: S3Slot) => storage[slot].access_key_id === null && storage[slot].secret_access_key === null;
  return (
    storage.keys_readable &&
    storage.s3_region === "" &&
    storage.s3_bucket === "" &&
    storage.s3_endpoint === "" &&
    none("rw") &&
    none("ro")
  );
}

/** The lines where the Test button will be: 13's "before the test" line only while region or bucket is empty. */
export function testLines(stored: StorageValues): string[] {
  return stored.s3_region === "" || stored.s3_bucket === "" ? [ST.testLater, ST.testNeeds] : [ST.testLater];
}

/** The line for a refused or unanswered write. */
export function storageError(failure: unknown, kind: "settings" | "keys" | "remove"): string {
  if (failure instanceof ApiError) {
    if (failure.code === "secrets_unavailable") return ST.secretsUnavailable;
    return kind === "settings" ? ST.saveRefused(failure.status) : ST.keysRefused(failure.status);
  }
  if (kind === "settings") return ST.saveFailed;
  return kind === "keys" ? ST.keysSaveFailed : ST.keysRemoveFailed;
}
