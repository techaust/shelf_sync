// The Storage settings (SET-02): the five settings, and the two S3 key pairs. The Help panel's S3 guide reads the
// bucket's name from here too. No answer ever holds a key: only masks (`AKIA••••9XYZ`, a secret as `••••`) and
// `keys_readable`. A key pair goes out in one PUT body and is never read back. There is no Test call yet (m2.7).

import type { ApiClient } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type StorageSettings = Schemas["StorageResponse"];
export type StorageValues = Schemas["StorageValues"];
export type KeyMasks = Schemas["KeyMasks"];
type KeyPairRequest = Schemas["KeyPairRequest"];

/** The two S3 key pairs: "rw" uploads and deletes, "ro" only reads (m2.0 section 2). */
export type S3Slot = "rw" | "ro";

export const STORAGE_PATH = "/api/settings/storage";
export const STORAGE_QUERY_KEY = ["settings", "storage"] as const;
const SLOT_PATHS: Record<S3Slot, string> = { rw: "/api/secrets/s3-rw", ro: "/api/secrets/s3-ro" };

export const getStorage = (api: ApiClient) => api.get<StorageSettings>(STORAGE_PATH);

/** All five settings in one PUT (unknown fields are refused by the API); answers what was saved. */
export const saveStorage = (api: ApiClient, values: StorageValues) =>
  api.send<StorageValues>("PUT", STORAGE_PATH, storageValuesOf(values));

export function saveS3Keys(api: ApiClient, slot: S3Slot, accessKeyId: string, secretAccessKey: string) {
  const body: KeyPairRequest = { access_key_id: accessKeyId, secret_access_key: secretAccessKey };
  return api.send("PUT", SLOT_PATHS[slot], body);
}

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
