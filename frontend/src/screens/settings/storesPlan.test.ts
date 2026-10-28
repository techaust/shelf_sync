// SET-01: what a Save on a store card and "Add store" send, decided without React (planSave, planAdd, isDirty), and
// where a refusal of each kind of request is shown (placeError with keysSent). Review round 1, item 3.
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { Store } from "../../api/stores";
import { S } from "../../lib/storesWording";
import { isDirty, newForm, placeError, planAdd, planSave } from "./storesModel";

const STORE: Store = {
  id: 3,
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
    state: "connected",
    reason: null,
    http_status: 200,
    latency_ms: 300,
    wc_version: "9.4.2",
    wp_version: "6.8",
    downloadable_count: 10,
    tested_at: "2026-10-29T04:00:00Z",
  },
};
const KEY = `ck_${"a".repeat(24)}`;
const SECRET = `cs_${"b".repeat(24)}`;
const plan = (over: Partial<Parameters<typeof planSave>[0]> = {}) =>
  planSave({ store: STORE, edits: {}, keysOpen: false, typedKey: "", typedSecret: "", takenCodes: ["GF"], ...over });

describe("planSave: the address-change rule", () => {
  it("a new host without new keys sends nothing and asks for them at the pair", () => {
    expect(plan({ edits: { url: "https://other.example" } })).toEqual({
      kind: "errors",
      errors: { keys: S.errors.keys_required },
      openKeys: true,
      openIdentifier: false,
    });
  });

  it("the same, with the pair open but empty", () => {
    const result = plan({ edits: { url: "https://other.example" }, keysOpen: true });
    expect(result).toMatchObject({ kind: "errors", errors: { keys: S.errors.keys_required }, openKeys: true });
  });

  it("the same when the saved keys couldn't be read: they would go to the new server", () => {
    const unreadable: Store = { ...STORE, keys: { consumer_key: null, consumer_secret: null }, keys_readable: false };
    expect(plan({ store: unreadable, edits: { url: "https://other.example" } })).toMatchObject({
      kind: "errors",
      errors: { keys: S.errors.keys_required },
      openKeys: true,
    });
  });

  it("a new host with new keys: one PATCH carries the address and both keys", () => {
    expect(
      plan({ edits: { url: "https://other.example" }, keysOpen: true, typedKey: KEY, typedSecret: SECRET }),
    ).toEqual({
      kind: "patch",
      body: { url: "https://other.example", consumer_key: KEY, consumer_secret: SECRET },
      keysSent: true,
    });
  });

  it("a new path on the same host needs no keys", () => {
    expect(plan({ edits: { url: "https://sample.example/shop" } })).toEqual({
      kind: "patch",
      body: { url: "https://sample.example/shop" },
      keysSent: false,
    });
  });

  it("a typed pair is only read while the pair is open", () => {
    expect(
      plan({ edits: { url: "https://other.example" }, keysOpen: false, typedKey: KEY, typedSecret: SECRET }).kind,
    ).toBe("errors");
  });
});

describe("planSave: what is sent", () => {
  it("keys only: PUT /keys", () => {
    expect(plan({ keysOpen: true, typedKey: ` ${KEY} `, typedSecret: SECRET })).toEqual({
      kind: "keys",
      keys: { consumer_key: KEY, consumer_secret: SECRET },
    });
  });

  it("a name and keys: one PATCH with both", () => {
    expect(plan({ edits: { name: "Renamed" }, keysOpen: true, typedKey: KEY, typedSecret: SECRET })).toEqual({
      kind: "patch",
      body: { name: "Renamed", consumer_key: KEY, consumer_secret: SECRET },
      keysSent: true,
    });
  });

  it("a name alone: a PATCH without keys", () => {
    expect(plan({ edits: { name: "Renamed" } })).toEqual({ kind: "patch", body: { name: "Renamed" }, keysSent: false });
  });

  it("nothing changed (or edited back to the saved value): nothing is sent", () => {
    expect(plan()).toEqual({ kind: "none" });
    expect(plan({ edits: { name: "Sample store", spacing: "0.15" } })).toEqual({ kind: "none" });
    expect(plan({ keysOpen: true })).toEqual({ kind: "none" });
  });

  it("half a pair, or a key of the wrong shape, is refused at the pair", () => {
    expect(plan({ keysOpen: true, typedKey: KEY })).toMatchObject({
      kind: "errors",
      errors: { keys: S.pairNeeded },
      openKeys: true,
    });
    expect(plan({ keysOpen: true, typedKey: "ck_x", typedSecret: SECRET })).toMatchObject({
      kind: "errors",
      errors: { consumerKey: S.keyShape },
    });
  });

  it("a used code opens the identifier picker at the code", () => {
    expect(plan({ edits: { code: "GF" } })).toEqual({
      kind: "errors",
      errors: { code: S.errors.code_taken },
      openKeys: false,
      openIdentifier: true,
    });
  });
});

describe("planSave and isDirty: the spacing is sent only when it was edited", () => {
  const odd: Store = { ...STORE, spacing_ms: 155 }; // the API and an import take any 50 to 5000 ms; shown as "0.16"

  it("an unedited odd spacing is never rewritten, even when another field is saved", () => {
    expect(plan({ store: odd, edits: { name: "Renamed" } })).toEqual({
      kind: "patch",
      body: { name: "Renamed" },
      keysSent: false,
    });
  });

  it("an edited spacing is sent in ms", () => {
    expect(plan({ store: odd, edits: { spacing: "0.5" } })).toEqual({
      kind: "patch",
      body: { spacing_ms: 500 },
      keysSent: false,
    });
  });

  it("an edited spacing out of range is refused", () => {
    expect(plan({ edits: { spacing: "9" } })).toMatchObject({ kind: "errors", errors: { spacing: S.spacingLimit } });
  });

  it("Save stays off for an odd spacing nobody touched, and lights for a real change", () => {
    expect(isDirty(odd, {}, false)).toBe(false);
    expect(isDirty(odd, { spacing: "0.155" }, false)).toBe(true); // refused when saved, but it is an edit
    expect(isDirty(STORE, { spacing: "0.15" }, false)).toBe(false); // typed back to the stored 150 ms
    expect(isDirty(STORE, { spacing: "0.2" }, false)).toBe(true);
    expect(isDirty(STORE, { name: "Sample store" }, false)).toBe(false);
    expect(isDirty(STORE, { name: "Renamed" }, false)).toBe(true);
    expect(isDirty(STORE, {}, true)).toBe(true);
  });
});

describe("planAdd", () => {
  const form = { ...newForm([STORE]), name: "New sample", url: "https://new.example", code: "NE" };

  it("good values and a pair: one POST with everything", () => {
    expect(planAdd({ form, typedKey: KEY, typedSecret: SECRET, takenCodes: ["SA"] })).toEqual({
      kind: "create",
      body: {
        name: "New sample",
        url: "https://new.example",
        main_button: "Download",
        code: "NE",
        shape: "square",
        color: "teal",
        spacing_ms: 150,
        consumer_key: KEY,
        consumer_secret: SECRET,
      },
    });
  });

  it("a store is never added without keys", () => {
    expect(planAdd({ form, typedKey: "", typedSecret: "", takenCodes: [] })).toEqual({
      kind: "errors",
      errors: { keys: S.pairNeeded },
    });
  });

  it("every field's error at once, with a used code", () => {
    const result = planAdd({ form: { ...newForm([]), code: "SA" }, typedKey: "", typedSecret: "", takenCodes: ["SA"] });
    expect(result).toEqual({
      kind: "errors",
      errors: { name: S.nameLimit, url: S.addressLimit, code: S.errors.code_taken, keys: S.pairNeeded },
    });
  });
});

describe("where secrets_unavailable is shown", () => {
  const unavailable = new ApiError("PATCH", "/api/stores/3", 503, "secrets_unavailable");

  it("at the key pair when the request carried keys (PUT /keys, a PATCH with keys, the Add card)", () => {
    expect(placeError(unavailable, true)).toMatchObject({ field: "keys", text: S.errors.secrets_unavailable });
  });

  it("at the top of the card when it didn't (a field-only PATCH, a pause, a removal)", () => {
    expect(placeError(unavailable, false)).toMatchObject({ field: "card", text: S.errors.secrets_unavailable });
  });

  it("the plan says which it was", () => {
    const withKeys = plan({ edits: { name: "Renamed" }, keysOpen: true, typedKey: KEY, typedSecret: SECRET });
    const without = plan({ edits: { name: "Renamed" } });
    expect(withKeys.kind === "patch" && withKeys.keysSent).toBe(true);
    expect(without.kind === "patch" && without.keysSent).toBe(false);
  });
});
