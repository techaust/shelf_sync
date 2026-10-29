// The typed calls of Settings › Stores and the shell's HealthArea (SET-01, ERR-01). Every body and answer is a type
// from the generated OpenAPI schema (schema.d.ts), and every call goes through the one API client, which adds what the
// guard needs to each write (X-ShelfSync: 1; the browser adds Origin). No answer holds a consumer key or secret: only
// the masks (`ck_••••abcd`), and `keys_readable` says whether those masks could be read at all.

import { STORE_PALETTE } from "../styles/storePalette";
import type { ApiClient } from "./client";
import type { StoreIdentifier } from "./placeholder";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Store = Schemas["StoreModel"];
export type StoreHealthModel = Schemas["HealthModel"];
export type StoreTest = Schemas["StoreTestResponse"];
export type CreateStore = Schemas["CreateStoreRequest"];
export type UpdateStore = Schemas["UpdateStoreRequest"];
export type StoreShape = Store["shape"];
type Stores = Schemas["StoresResponse"];
type Keys = Schemas["KeysRequest"];

export const STORES_PATH = "/api/stores";
/** One key for the list, shared by Settings › Stores and the HealthArea, so a save or a test refreshes both. */
export const STORES_QUERY_KEY = ["stores"] as const;

/** The shapes the API accepts, in the order 05 section 2.3 hands them out (the next free shape for a new store). */
export const STORE_SHAPES: readonly StoreShape[] = ["circle", "square", "triangle", "diamond"];

/** The path of one store, from its id (a positive whole number; anything else never reaches a request). */
function storePath(id: number, tail = ""): string {
  if (!Number.isSafeInteger(id) || id < 1) throw new Error("Not a store id");
  return `${STORES_PATH}/${id}${tail}`;
}

export async function listStores(api: ApiClient): Promise<Store[]> {
  const answer = await api.get<Stores>(STORES_PATH);
  return answer.stores;
}
export const createStore = (api: ApiClient, body: CreateStore) => api.send<Store>("POST", STORES_PATH, body);
export const updateStore = (api: ApiClient, id: number, body: UpdateStore) =>
  api.send<Store>("PATCH", storePath(id), body);
export function putStoreKeys(api: ApiClient, id: number, consumerKey: string, consumerSecret: string) {
  const body: Keys = { consumer_key: consumerKey, consumer_secret: consumerSecret };
  return api.send("PUT", storePath(id, "/keys"), body);
}
export const deleteStore = (api: ApiClient, id: number) => api.send("DELETE", storePath(id));
export const testStore = (api: ApiClient, id: number) => api.send<StoreTest>("POST", storePath(id, "/test"));

/** A store's identifier for StoreBadge: its shape, its palette pair and its code (05 section 2.3). */
export function identifierOf(store: Pick<Store, "code" | "name" | "shape" | "color">): StoreIdentifier {
  return { code: store.code, name: store.name, shape: store.shape, dot: STORE_PALETTE[store.color] };
}
