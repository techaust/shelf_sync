// The Storage settings (SET-02): the five settings, and the two S3 key pairs. The Help panel's S3 guide reads the
// bucket's name from here too. No answer ever holds a key: only masks (`AKIA••••9XYZ`, a secret as `••••`) and
// `keys_readable`. A key pair goes out in one PUT body and is never read back. The Test (m2.7, ERR-03) sends no body:
// the server tests what is saved, and its answer holds no endpoint, bucket or key, only the test file's key when it
// may be left behind.

import type { ApiClient } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type StorageSettings = Schemas["StorageResponse"];
export type StorageValues = Schemas["StorageValues"];
export type KeyMasks = Schemas["KeyMasks"];
type KeyPairRequest = Schemas["KeyPairRequest"];
export type StorageTest = Schemas["StorageTestResponse"];
export type StorageTestStep = Schemas["StorageTestStep"];

/** The two S3 key pairs: "rw" uploads and deletes, "ro" only reads (m2.0 section 2). */
export type S3Slot = "rw" | "ro";

export const STORAGE_PATH = "/api/settings/storage";
export const STORAGE_QUERY_KEY = ["settings", "storage"] as const;
export const STORAGE_TEST_PATH = "/api/storage/test";
const SLOT_PATHS: Record<S3Slot, string> = { rw: "/api/secrets/s3-rw", ro: "/api/secrets/s3-ro" };

export const getStorage = (api: ApiClient) => api.get<StorageSettings>(STORAGE_PATH);

/** All five settings in one PUT (unknown fields are refused by the API); answers what was saved. */
export const saveStorage = (api: ApiClient, values: StorageValues) =>
  api.send<StorageValues>("PUT", STORAGE_PATH, storageValuesOf(values));

export function saveS3Keys(api: ApiClient, slot: S3Slot, accessKeyId: string, secretAccessKey: string) {
  const body: KeyPairRequest = { access_key_id: accessKeyId, secret_access_key: secretAccessKey };
  return api.send("PUT", SLOT_PATHS[slot], body);
}

/** The 3-step Test of the saved settings and keys: 200 with `ok` and the steps even when it fails; 409 `busy`,
 *  `storage_not_set` or `keys_missing`, and 503 `secrets_unavailable`, are thrown as ApiError. */
export const testStorage = (api: ApiClient) => api.send<StorageTest>("POST", STORAGE_TEST_PATH);

export const removeS3Keys = (api: ApiClient, slot: S3Slot) => api.send("DELETE", SLOT_PATHS[slot]);

/** The five saved values of a GET or PUT answer, as a PUT body (never the masks or `keys_readable`). */
export function storageValuesOf(values: StorageValues): StorageValues {
  return {
    s3_endpoint: values.s3_endpoint,
    s3_region: values.s3_region,
    s3_bucket: values.s3_bucket,
    keep_previous_files: values.keep_previous_files,
    download_link_template: values.download_link_template,
  };
}
