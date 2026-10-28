// Settings › Stores without React (SET-01, ERR-01): the form's checks with the API's own limits (api/stores.py), the
// seconds ↔ spacing_ms conversion, the address-change rule, where each API error code is shown, and the lines a test
// result or a saved health reads as. Pure functions, so every rule is tested in Node (storesModel.test.ts).

import { ApiError, type ErrorCode } from "../../api/client";
import { type CreateStore, STORE_SHAPES, type Store, type StoreShape, type UpdateStore } from "../../api/stores";
import { S } from "../../lib/storesWording";
import { STORE_PALETTE, type StoreColor } from "../../styles/storePalette";

// ---------- limits (api/stores.py) ----------
export const NAME_MAX = 60;
export const BUTTON_MAX = 40;
export const URL_MAX = 200;
export const SPACING_MIN_MS = 50;
export const SPACING_MAX_MS = 5000;
export const DEFAULT_SPACING_MS = 150;
export const DEFAULT_BUTTON = "Download";
/** ConsumerKey and ConsumerSecret: the prefix, then 20 to 64 letters and digits. */
const CONSUMER_KEY = /^ck_[A-Za-z0-9]{20,64}$/;
const CONSUMER_SECRET = /^cs_[A-Za-z0-9]{20,64}$/;
export const KEY_MAX_LENGTH = 67;
const CODE = /^[A-Z]{2}$/;
/** store_service.py _HOST: dot-separated labels of lowercase letters, digits and inner hyphens. */
const HOST = /^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;
const PATH = /^[A-Za-z0-9._~/-]*$/;
/** A control character or one of the two Unicode line separators: Python's isprintable() refuses them too. */
function notPrintable(value: string): boolean {
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0;
    if (code <= 0x1f || (code >= 0x7f && code <= 0x9f) || code === 0x2028 || code === 0x2029) return true;
  }
  return false;
}

export const STORE_COLORS = Object.keys(STORE_PALETTE) as StoreColor[];

// ---------- Time between requests: seconds on screen, milliseconds in the API ----------

/** 150 → "0.15", 1000 → "1", 50 → "0.05": up to two decimals, no trailing zeros. */
export function secondsFromMs(ms: number): string {
  return (ms / 1000).toFixed(2).replace(/\.?0+$/, "");
}

/** "0.15" → 150, or null for anything that isn't 0.05 to 5 seconds written with up to two decimals. */
export function msFromSeconds(text: string): number | null {
  const trimmed = text.trim();
  if (!/^(?:\d{1,2}(?:\.\d{1,2})?|\.\d{1,2})$/.test(trimmed)) return null;
  const ms = Math.round(Number(trimmed) * 1000);
  return ms >= SPACING_MIN_MS && ms <= SPACING_MAX_MS ? ms : null;
}

// ---------- the store address ----------

/** The address as typed, if it is one the API would take (https, a host name with a dot, no user, query or fragment,
 *  a plain path), or null. The API still normalises and checks it; this only catches what it would refuse. */
export function checkAddress(text: string): string | null {
  const typed = text.trim();
  if (!typed || typed.length > URL_MAX || /[^\x21-\x7e]/.test(typed) || /[?#\\@]/.test(typed)) return null;
  if (!/^https:\/\//i.test(typed)) return null;
  let parsed: URL;
  try {
    parsed = new URL(typed);
  } catch {
    return null;
  }
  const host = parsed.hostname;
  const tld = host.split(".").at(-1) ?? "";
  if (parsed.protocol !== "https:" || !HOST.test(host) || !/[a-z]/.test(tld)) return null;
  const rawPath = typed.replace(/^https:\/\/[^/]*/i, "").replace(/\/+$/, "");
  if (!PATH.test(rawPath) || rawPath.includes("//")) return null;
  if (rawPath.split("/").some((part) => part === "." || part === "..")) return null;
  return typed;
}

/** Host and port, as the keys are tied to them (store_service.py _authority); null when it isn't an address. */
export function authorityOf(url: string): string | null {
  try {
    return new URL(url.trim()).host.toLowerCase();
  } catch {
    return null;
  }
}

/** The address-change rule: a different host (or port) needs new keys in the same request. */
export function hostChanged(saved: string, typed: string): boolean {
  const before = authorityOf(saved);
  const after = authorityOf(typed);
  return before !== null && after !== null && before !== after;
}

// ---------- the form ----------

export interface StoreForm {
  name: string;
  url: string;
  mainButton: string;
  code: string;
  shape: StoreShape;
  color: StoreColor;
  spacing: string;
}

export type StoreField = keyof StoreForm | "keys" | "consumerKey" | "consumerSecret";
export type StoreErrors = Partial<Record<StoreField, string>>;

export function formFrom(store: Store): StoreForm {
  return {
    name: store.name,
    url: store.url,
    mainButton: store.main_button,
    code: store.code,
    shape: store.shape,
    color: store.color,
    spacing: secondsFromMs(store.spacing_ms),
  };
}

/** A new store's starting identifier: the next free shape and colour (05 section 2.3), and the default spacing. */
export function newForm(stores: readonly Store[]): StoreForm {
  const shape = STORE_SHAPES.find((s) => !stores.some((store) => store.shape === s)) ?? "circle";
  const color = STORE_COLORS.find((c) => !stores.some((store) => store.color === c)) ?? STORE_COLORS[0] ?? "indigo";
  return {
    name: "",
    url: "",
    mainButton: DEFAULT_BUTTON,
    code: "",
    shape,
    color,
    spacing: secondsFromMs(DEFAULT_SPACING_MS),
  };
}

/** The API's text rule (`_text`): trimmed, printable, 1 to `max` characters. */
function text(value: string, max: number): string | null {
  const trimmed = value.trim();
  if (trimmed.length < 1 || trimmed.length > max) return null;
  // control characters and the two Unicode line separators: Python's isprintable() refuses them too
  if (notPrintable(trimmed)) return null;
  return trimmed;
}

/** Letters typed into the code field: upper case, letters only, at most two. */
export function codeInput(value: string): string {
  return value
    .toUpperCase()
    .replace(/[^A-Z]/g, "")
    .slice(0, 2);
}

export interface CheckedForm {
  name: string;
  url: string;
  main_button: string;
  code: string;
  shape: StoreShape;
  color: StoreColor;
  spacing_ms: number;
}

/** The form's values as the API takes them, or the errors to show at each field. `takenCodes` are the other stores'
 *  codes: the API refuses a used one (`code_taken`), and the form says so before sending. */
export function checkForm(
  form: StoreForm,
  takenCodes: readonly string[],
): { values: CheckedForm; errors: null } | { values: null; errors: StoreErrors } {
  const errors: StoreErrors = {};
  const name = text(form.name, NAME_MAX);
  const url = checkAddress(form.url);
  const button = text(form.mainButton, BUTTON_MAX);
  const spacing = msFromSeconds(form.spacing);
  if (name === null) errors.name = S.nameLimit;
  if (url === null) errors.url = S.addressLimit;
  if (button === null) errors.mainButton = S.buttonLimit;
  if (!CODE.test(form.code)) errors.code = S.codeLimit;
  else if (takenCodes.includes(form.code)) errors.code = S.errors.code_taken;
  if (spacing === null) errors.spacing = S.spacingLimit;
  if (name === null || url === null || button === null || spacing === null || Object.keys(errors).length > 0) {
    return { values: null, errors };
  }
  return {
    values: {
      name,
      url,
      main_button: button,
      code: form.code,
      shape: form.shape,
      color: form.color,
      spacing_ms: spacing,
    },
    errors: null,
  };
}

/** The two typed keys: both empty (nothing to send), both of the right shape, or the errors. */
export function checkKeys(
  key: string,
  secret: string,
): { keys: { consumer_key: string; consumer_secret: string } | null; errors: StoreErrors } {
  const k = key.trim();
  const s = secret.trim();
  if (!k && !s) return { keys: null, errors: {} };
  const errors: StoreErrors = {};
  if (!k || !s) errors.keys = S.pairNeeded;
  if (k && !CONSUMER_KEY.test(k)) errors.consumerKey = S.keyShape;
  if (s && !CONSUMER_SECRET.test(s)) errors.consumerSecret = S.secretShape;
  return Object.keys(errors).length
    ? { keys: null, errors }
    : { keys: { consumer_key: k, consumer_secret: s }, errors };
}

/** Only what changed, so a save never rewrites a field another tab changed meanwhile. */
export function changedFields(store: Store, values: CheckedForm): UpdateStore {
  const body: UpdateStore = {};
  if (values.name !== store.name) body.name = values.name;
  if (values.url !== store.url) body.url = values.url;
  if (values.main_button !== store.main_button) body.main_button = values.main_button;
  if (values.code !== store.code) body.code = values.code;
  if (values.shape !== store.shape) body.shape = values.shape;
  if (values.color !== store.color) body.color = values.color;
  if (values.spacing_ms !== store.spacing_ms) body.spacing_ms = values.spacing_ms;
  return body;
}

export function createBody(values: CheckedForm, keys: { consumer_key: string; consumer_secret: string }): CreateStore {
  return { ...values, ...keys };
}

// ---------- API errors: the 13 wording, at the field it belongs to ----------

export interface Placed {
  field: StoreField | "card";
  text: string;
  tone: "danger" | "info";
}

const FIELD_OF: Partial<Record<ErrorCode, StoreField>> = {
  store_exists: "url",
  code_taken: "code",
  keys_required: "keys",
  secrets_unavailable: "keys",
};

/** Where and how a refused or unanswered store write is shown. `keysSent`: whether the request carried keys (a
 *  Credential Manager failure is the keys' problem then, otherwise the card's). */
export function placeError(failure: unknown, keysSent = true): Placed {
  if (failure instanceof ApiError) {
    const code = failure.code;
    if (code && Object.hasOwn(S.errors, code)) {
      const words = S.errors[code as keyof typeof S.errors];
      let field: Placed["field"] = FIELD_OF[code] ?? "card";
      if (code === "secrets_unavailable" && !keysSent) field = "card";
      return { field, text: words, tone: code === "busy" ? "info" : "danger" };
    }
    return { field: "card", text: S.refused(failure.status), tone: "danger" };
  }
  return { field: "card", text: S.noAnswer, tone: "danger" };
}

// The health helpers (healthKind, outcomeLine, healthLine, testError) live in lib/storeHealth.ts: the shell's
// HealthArea uses them too.
