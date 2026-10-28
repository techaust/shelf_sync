// Every owner-facing string of Settings › Stores and the store chips in the HealthArea (SET-01, ERR-01), with where it
// comes from:
// - "13 test": docs/13-content.md section 3, the row "Store Test connection (M2.1)";
// - "13 API": the row "Stores API errors (M2.1)" (with `secrets_unavailable` shared with Storage, and
//   `too_many_stores` from M2.4);
// - "13 ERR": the rows ERR-01 and ERR-07;
// - "mockup": the approved P3.4 mockup (docs/05-design-system-appendix/mockup/js/screens-b.js, storesPage());
// - "proposed (m2.5a)": new in this task, listed in docs/runs/m2.5a-stores-screens.md section 3 for the lead.

import type { ErrorCode } from "../../api/client";
import type { StoreShape } from "../../api/stores";
import type { StoreColor } from "../../styles/storePalette";

/** 13 test: the reason codes of a failed (or warned) Test connection. `<status>`, `<host>` and `<version>` are filled
 *  in from the answer; a value the answer doesn't have is left out (proposed (m2.5a): the three "without" forms). */
export function reasonText(
  reason: string,
  facts: { status: number | null; host: string | null; version: string | null },
): string | null {
  switch (reason) {
    case "unreachable":
      return "Couldn't reach the store. Check the address and your internet connection.";
    case "timeout":
      return "The store took too long to answer.";
    case "tls_error":
      return "The store's security certificate wasn't accepted.";
    case "redirected":
      return facts.host
        ? `The store sent the request to another address (${facts.host}). Update the store's address.`
        : "The store sent the request to another address. Update the store's address.";
    case "blocked":
      return "Something in front of the store (a firewall or a security check) blocked the request.";
    case "not_woocommerce":
      return "That address answers, but it isn't a WooCommerce store's REST API.";
    case "rate_limited":
      return "The store is limiting requests (HTTP 429). Try again in a few minutes.";
    case "cloudflare_52x":
      return facts.status
        ? `Cloudflare couldn't reach the store's server (HTTP ${facts.status}).`
        : "Cloudflare couldn't reach the store's server.";
    case "server_error":
      return facts.status ? `The store had an error (HTTP ${facts.status}).` : "The store had an error.";
    case "bad_response":
      return "The store's answer wasn't what ShelfSync expected.";
    case "keys_refused":
      return "HTTP 401: the Shop Manager key was refused.";
    case "forbidden":
      return "HTTP 403: the key is valid but isn't allowed to read this. It needs the Shop Manager role.";
    case "wc_too_old":
      return facts.version
        ? `WooCommerce ${facts.version} is too old. ShelfSync needs 5.8 or newer.`
        : "The store's WooCommerce is too old. ShelfSync needs 5.8 or newer.";
    default:
      return null; // a code this screen has no words for is never echoed
  }
}

/** The fixed reasons whose sentence already names the HTTP status, or where it would read wrong (a redirect). */
export const REASONS_WITH_STATUS = new Set([
  "rate_limited",
  "cloudflare_52x",
  "server_error",
  "keys_refused",
  "forbidden",
]);

export const S = {
  // ---------- 13 test ----------
  connected: (ms: number, wc: string, count: number) =>
    `Connected in ${ms} ms. WooCommerce ${wc}, ${count} downloadable ${count === 1 ? "product" : "products"}.`,
  noDownloadable: "Connected, but the store has no downloadable products yet.",
  // proposed (m2.5a): the version wasn't readable (m2.0 risk R1: a Shop Manager key may not read system_status)
  connectedNoVersion: (ms: number, count: number) =>
    `Connected in ${ms} ms. ${count} downloadable ${count === 1 ? "product" : "products"}.`,
  connectedOnly: (ms: number) => `Connected in ${ms} ms.`, // proposed (m2.5a): no count in the answer
  // proposed (m2.5a)
  testFailedUnknown: "The test failed.",
  notTested: "Not tested yet.",
  testing: "Testing the connection. This can take up to a minute.",
  testedAt: (when: string) => `Tested ${when}.`,

  // ---------- 13 API ----------
  errors: {
    not_found: "That store no longer exists.",
    store_exists: "A store with this address is already added.",
    code_taken: "Another store already uses this two-letter code.",
    keys_missing: "This store has no keys saved. Enter its consumer key and secret first.",
    keys_required:
      "The address now points at a different server. Enter the new keys too, so the old ones aren't sent there.",
    secrets_unavailable: "Windows Credential Manager couldn't be used. Check the keys and try again.",
    busy: "A test of this store is already running.",
    too_many_stores: "ShelfSync keeps up to 50 stores. Remove one before adding another.",
  } satisfies Partial<Record<ErrorCode, string>>,

  // ---------- 13 ERR ----------
  /** ERR-01, split in two lines (proposed (m2.5a)): the store and the state, then the 13 test reason. */
  cantReach: (store: string) => `${store} can't be reached.`,
  waiting: "Updates for it are waiting.",
  emptyText: "Add your first store to start.", // 13 ERR-07
  emptySub: "You need its address and a Shop Manager key.", // mockup

  // ---------- mockup ----------
  active: "Active",
  pause: "Pause store",
  remove: "Remove",
  address: "Store address",
  mainButton: "Main button name",
  consumerKey: "Consumer key",
  consumerSecret: "Consumer secret",
  keysHint: "Kept in Windows Credential Manager. They're never shown again or sent to this page.", // mockup, plural
  placeholder: "Paste the new value",
  identifier: "Identifier",
  change: "Change",
  spacing: "Time between requests",
  seconds: "seconds",
  test: "Test connection",
  keyGuide: "Shop Manager key guide",
  addStore: "Add a store",
  cancel: "Cancel",

  // ---------- proposed (m2.5a) ----------
  paused: "Paused",
  resume: "Resume store",
  pausedLine: (store: string) => `${store} is paused. Its updates wait until you resume it.`, // the mockup's mock text
  pausedDone: (store: string) => `${store} is paused.`,
  resumedDone: (store: string) => `${store} is active again.`,
  name: "Store name",
  keysLegend: "Shop Manager key",
  replaceKeys: "Replace keys", // runbooks/key-rotation.md
  notSet: "Not set", // 13 Storage masks
  unreadable: "Couldn't be read", // 13 Storage masks (keys_readable false)
  spacingHint: "How long ShelfSync waits between two requests to this store.",
  identifierHint: "Its shape, colour and code show the store everywhere in ShelfSync.",
  shape: "Shape",
  colour: "Colour",
  code: "Two-letter code",
  shapes: { circle: "Circle", square: "Square", triangle: "Triangle", diamond: "Diamond" } satisfies Record<
    StoreShape,
    string
  >,
  colours: { indigo: "Indigo", teal: "Teal" } satisfies Record<StoreColor, string>,
  identSummary: (shape: string, colour: string, code: string) => `${shape}, ${colour.toLowerCase()}, code ${code}`,
  preview: "Preview",
  done: "Done",
  save: "Save store",
  saved: "Store saved.",
  keysSaved: "Keys saved.", // 13 Storage
  add: "Add store",
  addTitle: "Add a store",
  added: (store: string) => `${store} added. Test the connection to check its keys.`,
  removeTitle: (store: string) => `Remove ${store}?`,
  removeLead: (store: string) => `ShelfSync stops updating ${store}. Nothing on the store itself changes.`,
  removeKeys:
    "Its consumer key and secret are deleted from Windows Credential Manager at once. To add the store again, you need its keys.",
  removeConfirm: "Remove store",
  removed: (store: string) => `${store} removed.`,
  // the form's checks, with the API's own limits
  nameLimit: "Use a name of 1 to 60 characters.",
  addressLimit: "Use the store's address, starting with https://, for example https://shop.example.com.",
  buttonLimit: "Use a button name of 1 to 40 characters.",
  codeLimit: "Use two capital letters, for example GF.",
  spacingLimit: "Use a number of seconds from 0.05 to 5, with up to two decimals.",
  keyShape: "A consumer key starts with ck_ followed by 20 to 64 letters and digits.",
  secretShape: "A consumer secret starts with cs_ followed by 20 to 64 letters and digits.",
  pairNeeded: "Enter both the consumer key and the consumer secret.", // 13 Storage's "Enter both…" pattern
  // the general lines (13 Settings screens' patterns): an unanswered request never states an outcome
  refused: (status: number) => `ShelfSync refused that (HTTP ${status}), so nothing was changed.`,
  noAnswer: "ShelfSync didn't answer, so that may not have happened. Reload this page to check.",
  testRefused: (status: number) => `ShelfSync refused the test (HTTP ${status}).`,
  testNoAnswer: "ShelfSync didn't answer, so the test may not have run. Reload this page to check.",
  loadFailed: "ShelfSync didn't answer, so the stores can't be shown.",
  loadRefused: (status: number) => `ShelfSync refused to show the stores (HTTP ${status}).`,
  staleNotice: "ShelfSync didn't answer just now, so this may be out of date.", // 13 Settings screens
  tryAgain: "Try again",

  // ---------- the HealthArea (shell; 13 Shell and proposed (m2.5a)) ----------
  chip: {
    unreachable: "Can't reach", // mockup
    refused: "Refused", // M1a.3
    unknown: "Not tested",
    paused: "Paused",
  },
  neverTested: (store: string) => `${store} hasn't been tested yet.`,
  neverTestedSub: "Test the connection to check its address and keys.",
  connectionsUnknown: "Connections can't be shown",
  showReason: "Show the reason",
  chipConnected: (store: string, ms: number | null) => `${store}: connected${ms === null ? "" : `, ${ms} ms`}`,
  chipPaused: (store: string) => `${store}: paused`,
};
