// SET-01, ERR-01: Settings › Stores without React. The seconds ↔ spacing_ms conversion and its limits, the form's
// checks with the API's limits, the address-change rule, where every API error code is shown and in which 13 words,
// and the line each test reason reads as.
import { describe, expect, it } from "vitest";
import { ApiError, ApiUnreachableError, type ErrorCode } from "../../api/client";
import type { Store, StoreTest } from "../../api/stores";
import {
  authorityOf,
  changedFields,
  checkAddress,
  checkForm,
  checkKeys,
  codeInput,
  formFrom,
  healthKind,
  hostChanged,
  msFromSeconds,
  newForm,
  outcomeLine,
  placeError,
  secondsFromMs,
  testError,
} from "./storesModel";
import { S } from "./storesWording";

const SAMPLE_STORE: Store = {
  id: 1,
  name: "Sample store",
  url: "https://sample.example",
  code: "SA",
  shape: "circle",
  color: "indigo",
  spacing_ms: 150,
  main_button: "Download",
  state: "active",
  keys: { consumer_key: "ck_••••a1b2", consumer_secret: "cs_••••c3d4" },
  keys_readable: true,
  health: {
    state: "unknown",
    reason: null,
    http_status: null,
    latency_ms: null,
    wc_version: null,
    wp_version: null,
    downloadable_count: null,
    tested_at: null,
  },
};
const KEY = `ck_${"a".repeat(24)}`;
const SECRET = `cs_${"b".repeat(24)}`;
const refused = (status: number, code: ErrorCode | null) => new ApiError("PATCH", "/api/stores/1", status, code);

describe("Time between requests: seconds on screen, spacing_ms in the API", () => {
  it.each([
    [150, "0.15"],
    [50, "0.05"],
    [1000, "1"],
    [1500, "1.5"],
    [5000, "5"],
    [250, "0.25"],
  ])("%i ms shows as %s seconds", (ms, text) => {
    expect(secondsFromMs(ms)).toBe(text);
  });

  it.each([
    ["0.15", 150],
    ["0.05", 50],
    ["5", 5000],
    ["5.00", 5000],
    [".5", 500],
    [" 1.25 ", 1250],
  ])("%s seconds is sent as %i ms", (text, ms) => {
    expect(msFromSeconds(text)).toBe(ms);
  });

  it.each(["0.04", "5.01", "0", "6", "", "abc", "1,5", "0.125", "-1", "1e3", "10.5.1"])(
    "%s is refused (0.05 to 5 s, two decimals at most)",
    (text) => {
      expect(msFromSeconds(text)).toBeNull();
    },
  );

  it("every value the screen shows reads back to itself", () => {
    for (let ms = 50; ms <= 5000; ms += 10) expect(msFromSeconds(secondsFromMs(ms))).toBe(ms);
  });
});

describe("the store address", () => {
  it.each([
    "https://shop.example.com",
    "https://shop.example.com/",
    "https://shop.example.com/store",
    "https://a.example:8443",
  ])("%s is taken", (url) => {
    expect(checkAddress(url)).toBe(url);
  });

  it.each([
    "http://shop.example.com",
    "shop.example.com",
    "https://localhost",
    "https://192.168.1.10",
    "https://user@shop.example.com",
    "https://shop.example.com/?a=1",
    "https://shop.example.com/#x",
    "https://shop.example.com/a//b",
    "https://shop.example.com/a/../b",
    "https://shöp.example.com",
    "https://shop example.com",
    `https://${"a".repeat(200)}.com`,
    "",
  ])("%s is refused before anything is sent", (url) => {
    expect(checkAddress(url)).toBeNull();
  });

  it("the address-change rule compares host and port, as the API does", () => {
    expect(authorityOf("https://Shop.Example.com/store")).toBe("shop.example.com");
    expect(authorityOf("https://shop.example.com:443")).toBe("shop.example.com");
    expect(hostChanged("https://shop.example.com", "https://shop.example.com/store")).toBe(false);
    expect(hostChanged("https://shop.example.com", "https://SHOP.example.com")).toBe(false);
    expect(hostChanged("https://shop.example.com", "https://other.example.com")).toBe(true);
    expect(hostChanged("https://shop.example.com", "https://shop.example.com:8443")).toBe(true);
    expect(hostChanged("https://shop.example.com", "not an address")).toBe(false);
  });

  it("keys_required is shown at the key pair, in 13's words", () => {
    expect(placeError(refused(422, "keys_required"))).toEqual({
      field: "keys",
      text: S.errors.keys_required,
      tone: "danger",
    });
  });
});

describe("the form", () => {
  const takenCodes = ["GF", "PW"];
  const filled = { ...newForm([]), name: "Sample", url: "https://sample.example", code: "SA" };

  it("a new store starts with the next free shape and colour, Download and 0.15 s", () => {
    expect(newForm([])).toMatchObject({ shape: "circle", color: "indigo", mainButton: "Download", spacing: "0.15" });
    const two = [
      SAMPLE_STORE,
      { ...SAMPLE_STORE, id: 2, code: "SB", shape: "square" as const, color: "teal" as const },
    ];
    expect(newForm(two)).toMatchObject({ shape: "triangle", color: "indigo" });
  });

  it("a saved store fills the form, with its spacing in seconds", () => {
    expect(formFrom({ ...SAMPLE_STORE, spacing_ms: 1250 })).toMatchObject({ name: "Sample store", spacing: "1.25" });
  });

  it("good values become the API's body, trimmed", () => {
    const checked = checkForm({ ...filled, name: "  Sample  " }, takenCodes);
    expect(checked.errors).toBeNull();
    expect(checked.values).toEqual({
      name: "Sample",
      url: "https://sample.example",
      main_button: "Download",
      code: "SA",
      shape: "circle",
      color: "indigo",
      spacing_ms: 150,
    });
  });

  it("each refused field has its own line", () => {
    const { errors } = checkForm(
      { ...filled, name: " ", url: "http://x", mainButton: "", code: "s", spacing: "9" },
      takenCodes,
    );
    expect(errors).toEqual({
      name: S.nameLimit,
      url: S.addressLimit,
      mainButton: S.buttonLimit,
      code: S.codeLimit,
      spacing: S.spacingLimit,
    });
  });

  it("names and button names over the API's limits, or with control characters, are refused", () => {
    expect(checkForm({ ...filled, name: "x".repeat(61) }, []).errors?.name).toBe(S.nameLimit);
    expect(checkForm({ ...filled, name: "a\u0007b" }, []).errors?.name).toBe(S.nameLimit);
    expect(checkForm({ ...filled, mainButton: "x".repeat(41) }, []).errors?.mainButton).toBe(S.buttonLimit);
  });

  it("a code another store uses is refused at the field, with 13's code_taken words", () => {
    expect(checkForm({ ...filled, code: "GF" }, takenCodes).errors).toEqual({ code: S.errors.code_taken });
  });

  it("the code field keeps two capital letters", () => {
    expect(codeInput("gf")).toBe("GF");
    expect(codeInput("g1f2x")).toBe("GF");
    expect(codeInput("")).toBe("");
  });

  it("a key pair is both or neither, each of its shape", () => {
    expect(checkKeys("", "")).toEqual({ keys: null, errors: {} });
    expect(checkKeys(` ${KEY} `, SECRET).keys).toEqual({ consumer_key: KEY, consumer_secret: SECRET });
    expect(checkKeys(KEY, "").errors).toEqual({ keys: S.pairNeeded });
    expect(checkKeys("", SECRET).errors).toEqual({ keys: S.pairNeeded });
    expect(checkKeys("ck_short", SECRET).errors).toEqual({ consumerKey: S.keyShape });
    expect(checkKeys(KEY, KEY).errors).toEqual({ consumerSecret: S.secretShape });
  });

  it("only what changed is sent", () => {
    const values = checkForm({ ...formFrom(SAMPLE_STORE), spacing: "0.5", shape: "diamond" }, []).values;
    expect(values).not.toBeNull();
    if (values) expect(changedFields(SAMPLE_STORE, values)).toEqual({ spacing_ms: 500, shape: "diamond" });
  });
});

describe("every API error code: the 13 wording, at its field", () => {
  it.each<[ErrorCode, string, string]>([
    ["store_exists", "url", S.errors.store_exists],
    ["code_taken", "code", S.errors.code_taken],
    ["keys_required", "keys", S.errors.keys_required],
    ["secrets_unavailable", "keys", S.errors.secrets_unavailable],
    ["not_found", "card", S.errors.not_found],
    ["too_many_stores", "card", S.errors.too_many_stores],
    ["keys_missing", "card", S.errors.keys_missing],
  ])("%s goes to %s", (code, field, text) => {
    expect(placeError(refused(409, code))).toMatchObject({ field, text, tone: "danger" });
  });

  it("busy is information, not a failure", () => {
    expect(placeError(refused(409, "busy"))).toEqual({ field: "card", text: S.errors.busy, tone: "info" });
  });

  it("secrets_unavailable without keys in the request is the card's (a remove, a pause)", () => {
    expect(placeError(refused(503, "secrets_unavailable"), false).field).toBe("card");
  });

  it("13's exact words", () => {
    expect(S.errors).toEqual({
      not_found: "That store no longer exists.",
      store_exists: "A store with this address is already added.",
      code_taken: "Another store already uses this two-letter code.",
      keys_missing: "This store has no keys saved. Enter its consumer key and secret first.",
      keys_required:
        "The address now points at a different server. Enter the new keys too, so the old ones aren't sent there.",
      secrets_unavailable: "Windows Credential Manager couldn't be used. Check the keys and try again.",
      busy: "A test of this store is already running.",
      too_many_stores: "ShelfSync keeps up to 50 stores. Remove one before adding another.",
    });
  });

  it("any other refusal names the status, and no answer never claims an outcome", () => {
    expect(placeError(refused(422, "invalid_request")).text).toBe(S.refused(422));
    expect(placeError(refused(500, null)).text).toBe("ShelfSync refused that (HTTP 500), so nothing was changed.");
    expect(placeError(new ApiUnreachableError("PATCH", "/api/stores/1")).text).toBe(S.noAnswer);
  });

  it("Test connection's refusals", () => {
    expect(testError(refused(409, "busy"))).toEqual({ text: S.errors.busy, tone: "info" });
    expect(testError(refused(409, "keys_missing"))).toEqual({ text: S.errors.keys_missing, tone: "danger" });
    expect(testError(refused(404, "not_found"))).toEqual({ text: S.errors.not_found, tone: "danger" });
    expect(testError(refused(500, null)).text).toBe("ShelfSync refused the test (HTTP 500).");
    expect(testError(new Error("network")).text).toBe(S.testNoAnswer);
  });
});

describe("test results (13 Store Test connection)", () => {
  const base: Pick<StoreTest, "state" | "reason" | "http_status" | "latency_ms" | "wc_version" | "downloadable_count"> =
    {
      state: "connected",
      reason: null,
      http_status: 200,
      latency_ms: 312,
      wc_version: "9.4.2",
      downloadable_count: 2398,
    };
  const failed = (reason: string, http_status: number | null = null, extra: Partial<StoreTest> = {}) =>
    outcomeLine({ ...base, state: "unreachable", reason, http_status, latency_ms: null, ...extra });

  it("success: latency, WooCommerce version and the count, with thousands separators", () => {
    expect(outcomeLine(base)).toEqual({
      tone: "success",
      text: "Connected in 312 ms. WooCommerce 9.4.2, 2,398 downloadable products.",
    });
    expect(outcomeLine({ ...base, downloadable_count: 1 }).text).toBe(
      "Connected in 312 ms. WooCommerce 9.4.2, 1 downloadable product.",
    );
  });

  it("no downloadable products is a warning, from the answer's warning or a count of 0", () => {
    expect(outcomeLine({ ...base, warning: "no_downloadable_products" })).toEqual({
      tone: "warning",
      text: S.noDownloadable,
    });
    expect(outcomeLine({ ...base, downloadable_count: 0 }).tone).toBe("warning");
  });

  it("a version that couldn't be read is left out", () => {
    expect(outcomeLine({ ...base, wc_version: null }).text).toBe("Connected in 312 ms. 2,398 downloadable products.");
  });

  it("never tested", () => {
    expect(outcomeLine({ ...base, state: "unknown" })).toEqual({ tone: "neutral", text: S.notTested });
  });

  it.each<[string, number | null, string]>([
    ["unreachable", null, "Couldn't reach the store. Check the address and your internet connection."],
    ["timeout", null, "The store took too long to answer."],
    ["tls_error", null, "The store's security certificate wasn't accepted."],
    [
      "blocked",
      403,
      "Something in front of the store (a firewall or a security check) blocked the request (HTTP 403).",
    ],
    ["not_woocommerce", 404, "That address answers, but it isn't a WooCommerce store's REST API (HTTP 404)."],
    ["rate_limited", 429, "The store is limiting requests (HTTP 429). Try again in a few minutes."],
    ["cloudflare_52x", 524, "Cloudflare couldn't reach the store's server (HTTP 524)."],
    ["server_error", 500, "The store had an error (HTTP 500)."],
    ["bad_response", 200, "The store's answer wasn't what ShelfSync expected."],
    ["keys_refused", 401, "HTTP 401: the Shop Manager key was refused."],
    ["forbidden", 403, "HTTP 403: the key is valid but isn't allowed to read this. It needs the Shop Manager role."],
    ["something_new", 418, S.testFailedUnknown],
  ])("%s (HTTP %s)", (reason, status, text) => {
    expect(failed(reason, status)).toEqual({ tone: "danger", text });
  });

  it("redirected names the host when the answer has it", () => {
    expect(failed("redirected", 301, { detail: "www.sample.example" }).text).toBe(
      "The store sent the request to another address (www.sample.example). Update the store's address.",
    );
    expect(failed("redirected", 301).text).toBe(
      "The store sent the request to another address. Update the store's address.",
    );
  });

  it("wc_too_old names the version", () => {
    expect(failed("wc_too_old", 200, { wc_version: "5.2.0" }).text).toBe(
      "WooCommerce 5.2.0 is too old. ShelfSync needs 5.8 or newer.",
    );
  });
});

describe("the chip's kind", () => {
  const health = (state: Store["health"]["state"]) => ({ ...SAMPLE_STORE.health, state });
  it("paused wins over any health: a paused store is never shown as failed", () => {
    expect(healthKind({ state: "paused", health: health("refused") })).toBe("paused");
    expect(healthKind({ state: "paused", health: health("unreachable") })).toBe("paused");
  });
  it("then the saved health", () => {
    expect(healthKind({ state: "active", health: health("connected") })).toBe("connected");
    expect(healthKind({ state: "active", health: health("unknown") })).toBe("unknown");
    expect(healthKind({ state: "active", health: health("refused") })).toBe("failed");
    expect(healthKind({ state: "active", health: health("unreachable") })).toBe("failed");
  });
});
