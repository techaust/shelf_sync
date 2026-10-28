// The Storage settings read (SET-02), for now only what the Help panel's S3 guide needs: the bucket's name, which it
// writes into both IAM policies. Settings › Storage (m2.5b) adds the writes here. The answer never holds a key: only
// masks and `keys_readable`.

import type { ApiClient } from "./client";
import type { components } from "./schema";

export type StorageSettings = components["schemas"]["StorageResponse"];

export const STORAGE_PATH = "/api/settings/storage";
export const STORAGE_QUERY_KEY = ["settings", "storage"] as const;

export const getStorage = (api: ApiClient) => api.get<StorageSettings>(STORAGE_PATH);
