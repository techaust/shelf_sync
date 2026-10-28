// SET-01, ERR-01: each state of a store card, the Add card, the Remove dialog and the HealthArea as the page draws
// them. The unit tests run in Node with no DOM, so the views are rendered to static HTML (react-dom/server); the
// dialog's keyboard behaviour is tested with a fake <dialog> (dialog.ts), and the rest was checked by hand in the
// built-in browser pane (run file section 3).
import { type ComponentProps, createRef, type FunctionComponent, createElement as h, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Store } from "../../api/stores";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { type DialogElement, dialogBehaviour, type Focusable } from "../../components/dialog";
import { HealthArea } from "../../components/HealthArea";
import { TipProvider } from "../../components/Tip";
import { S } from "../../lib/storesWording";
import type { TestEntry } from "../../lib/storeTests";
import { AddStoreView, type PairState, StoreCardView, StoresEmpty, StoresFailed, StoresLoading } from "./StoresView";
import { formFrom, newForm } from "./storesModel";

const decode = (html: string) =>
  html.replaceAll("&#x27;", "'").replaceAll("&quot;", '"').replaceAll("&amp;", "&").replaceAll("&gt;", ">");
const markup = (element: ReactElement) => decode(renderToStaticMarkup(element));
const when = (iso: string | null | undefined) => (iso ? "29 October 2026 at 09:30 India Standard Time" : null);

const SAMPLE: Store = {
  id: 7,
  name: "Sample store",
  url: "https://sample.example",
  code: "SA",
  shape: "square",
  color: "teal",
  spacing_ms: 250,
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
const CONNECTED = {
  ...SAMPLE.health,
  state: "connected" as const,
  http_status: 200,
  latency_ms: 312,
  wc_version: "9.4.2",
  downloadable_count: 2398,
  tested_at: "2026-10-29T04:00:00Z",
};
const REFUSED = {
  ...SAMPLE.health,
  state: "refused" as const,
  reason: "keys_refused",
  http_status: 401,
  tested_at: "2026-10-29T04:00:00Z",
};
const IDLE: TestEntry = { running: false, result: null, error: null };

function pair(over: Partial<PairState> = {}): PairState {
  return {
    masks: { first: "ck_••••a1b2", second: "cs_••••c3d4" },
    readable: true,
    open: false,
    closable: true,
    keyRef: createRef(),
    secretRef: createRef(),
    onOpen: vi.fn(),
    onCancel: vi.fn(),
    onTyped: vi.fn(),
    ...over,
  };
}
const handlers = {
  onChange: vi.fn(),
  onIdentToggle: vi.fn(),
  onSave: vi.fn(),
  onTest: vi.fn(),
  onPause: vi.fn(),
  onRemove: vi.fn(),
  onGuide: vi.fn(),
};
function card(store: Store, over: Partial<Parameters<typeof StoreCardView>[0]> = {}) {
  const keysSet = store.keys.consumer_key !== null;
  return markup(
    h(StoreCardView, {
      store,
      form: formFrom(store),
      errors: {},
      identOpen: false,
      pair: pair({
        masks: { first: store.keys.consumer_key, second: store.keys.consumer_secret },
        readable: store.keys_readable,
        open: store.keys_readable && !keysSet,
      }),
      dirty: false,
      saving: false,
      pausing: false,
      message: null,
      saved: null,
      test: IDLE,
      when,
      handlers,
      ...over,
    }),
  );
}

describe("the page's states", () => {
  it("loading: two quiet cards, marked busy", () => {
    const html = markup(h(StoresLoading));
    expect(html).toContain('aria-busy="true"');
    expect(html.match(/class="card"/g)?.length).toBe(2);
  });

  it("load failed: the reason and Try again", () => {
    const html = markup(h(StoresFailed, { text: S.loadFailed, onRetry: vi.fn() }));
    expect(html).toContain('role="alert"');
    expect(html).toContain("ShelfSync didn't answer, so the stores can't be shown.");
    expect(html).toContain(">Try again</button>");
  });

  it("no store yet: 13 ERR-07, the mockup's line, and Add a store", () => {
    const html = markup(h(StoresEmpty, { onAdd: vi.fn() }));
    expect(html).toContain("Add your first store to start.");
    expect(html).toContain("You need its address and a Shop Manager key.");
    expect(html).toContain(">Add a store</button>");
  });
});

describe("a store card, in each state", () => {
  it("the head: identifier (shape, colour key, code), name, Active, Pause store and Remove", () => {
    const html = card(SAMPLE);
    expect(html).toContain('class="store-dot is-square"');
    expect(html).toContain('<h3 class="card__title is-sm store-card__title" id="store-7-title" tabindex="-1">');
    expect(html).toContain('SA<span class="sr-only"> (Sample store)</span>');
    expect(html).toContain(">Active</span>");
    expect(html).toContain(">Pause store</button>");
    expect(html).toContain(">Remove</button>");
  });

  it("the fields: name, address, main button, the spacing in seconds, the identifier summary", () => {
    const html = card(SAMPLE);
    for (const label of [S.name, S.address, S.mainButton, S.spacing]) expect(html).toContain(`>${label}</label>`);
    expect(html).toContain('value="0.25"');
    expect(html).toContain(">seconds</span>");
    expect(html).toContain("Square, teal, code SA");
    expect(html).toContain('aria-expanded="false"');
  });

  it("keys saved: the two masks in mono and Replace keys; no secret, no input", () => {
    const html = card(SAMPLE);
    expect(html).toContain('<span class="mono">ck_••••a1b2</span>');
    expect(html).toContain('<span class="mono">cs_••••c3d4</span>');
    expect(html).toContain(">Replace keys</button>");
    expect(html).not.toContain('type="password"');
    expect(html).toContain(S.keysHint);
  });

  it("no keys: Not set, and the two password inputs open at once", () => {
    const html = card({ ...SAMPLE, keys: { consumer_key: null, consumer_secret: null } });
    expect(html).toContain(">Not set</span>");
    expect(html.match(/type="password"/g)?.length).toBe(2);
    expect(html).toMatch(/autocomplete="off"/i);
  });

  it("keys unreadable: Couldn't be read, never Not set", () => {
    const html = card({ ...SAMPLE, keys: { consumer_key: null, consumer_secret: null }, keys_readable: false });
    expect(html.match(/Couldn't be read/g)?.length).toBe(2);
    expect(html).not.toContain("Not set");
    expect(html).toContain(">Replace keys</button>");
  });

  it("never tested: Not tested yet", () => {
    const html = card(SAMPLE);
    expect(html).toContain("Not tested yet.");
    expect(html).not.toContain('role="alert"');
  });

  it("tested OK: the 13 line and when, in local time with the zone", () => {
    const html = card({ ...SAMPLE, health: CONNECTED });
    expect(html).toContain("Connected in 312 ms. WooCommerce 9.4.2, 2,398 downloadable products.");
    expect(html).toContain("Tested 29 October 2026 at 09:30 India Standard Time.");
    expect(html).toContain('class="test-result is-success"');
  });

  it("test failed: ERR-01 at the top of the card, and the reason in the test row", () => {
    const html = card({ ...SAMPLE, health: REFUSED });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Sample store can't be reached.");
    expect(html).toContain("HTTP 401: the Shop Manager key was refused. Updates for it are waiting.");
    expect(html).toContain('class="test-result is-danger"');
  });

  it("paused: Paused and Resume store, an information line, never the failure alert", () => {
    const html = card({ ...SAMPLE, state: "paused", health: REFUSED });
    expect(html).toContain(">Paused</span>");
    expect(html).toContain(">Resume store</button>");
    expect(html).toContain("Sample store is paused. Its updates wait until you resume it.");
    expect(html).not.toContain("can't be reached");
    expect(html).toContain('class="card store-card is-paused"');
  });

  it("a test running: the button shows progress and says so, and a second click is refused by aria-disabled", () => {
    const html = card(SAMPLE, { test: { running: true, result: null, error: null } });
    expect(html).toMatch(
      /aria-disabled="true" aria-busy="true"><svg[^>]*is-spinning[^>]*>.*Test connection<\/button>/s,
    );
    expect(html).toContain(S.testing);
  });

  it("a test refused as busy uses its 13 text", () => {
    const html = card(SAMPLE, { test: { running: false, result: null, error: { text: S.errors.busy, tone: "info" } } });
    expect(html).toContain("A test of this store is already running.");
  });

  it("this tab's last answer wins over the saved health (it has the redirect host)", () => {
    const result = {
      ok: false,
      ...REFUSED,
      reason: "redirected",
      http_status: 301,
      tested_at: "2026-10-29T05:00:00Z",
      detail: "www.sample.example",
      warning: null,
      state: "unreachable" as const,
    };
    const html = card({ ...SAMPLE, health: REFUSED }, { test: { running: false, result, error: null } });
    expect(html).toContain("The store sent the request to another address (www.sample.example).");
  });

  it("a field error is at its field, named by aria-describedby and aria-invalid", () => {
    const html = card(SAMPLE, { errors: { url: S.errors.store_exists } });
    expect(html).toMatch(/id="store-7-url"[^>]*aria-invalid="true"[^>]*aria-describedby="store-7-url-error"/);
    expect(html).toContain('id="store-7-url-error"');
    expect(html).toContain("A store with this address is already added.");
  });

  it("the address-change rule: keys_required at the key pair, with the inputs open", () => {
    const html = markup(
      h(StoreCardView, {
        store: SAMPLE,
        form: { ...formFrom(SAMPLE), url: "https://other.example" },
        errors: { keys: S.errors.keys_required },
        identOpen: false,
        pair: pair({ open: true }),
        dirty: true,
        saving: false,
        pausing: false,
        message: null,
        saved: null,
        test: IDLE,
        when,
        handlers,
      }),
    );
    expect(html).toContain(S.errors.keys_required);
    expect(html.match(/type="password"/g)?.length).toBe(2);
    expect(html).toMatch(/id="store-7-keys-first"[^>]*aria-invalid="true"/);
  });

  it("a code another store uses is shown at the code field, with the picker open", () => {
    const html = card(SAMPLE, { identOpen: true, errors: { code: S.errors.code_taken } });
    expect(html).toContain("Another store already uses this two-letter code.");
    expect(html).toMatch(/id="store-7-ident-code"[^>]*aria-invalid="true"/);
    expect(html).toContain('aria-controls="store-7-ident-panel"');
    for (const shape of ["Circle", "Square", "Triangle", "Diamond"]) expect(html).toContain(`<span>${shape}</span>`);
    for (const colour of ["Indigo", "Teal"]) expect(html).toContain(`<span>${colour}</span>`);
  });

  it("Save store is off (aria-disabled, still focusable) until something changed, and says when it saved", () => {
    expect(card(SAMPLE)).toMatch(/id="store-7-save" type="submit" class="btn is-primary" aria-disabled="true"/);
    const html = card(SAMPLE, { dirty: true, saved: S.saved });
    expect(html).not.toMatch(/id="store-7-save"[^>]*aria-disabled/);
    expect(html).toContain("Store saved.");
  });

  it("a card-level refusal (too many stores, no answer) is an alert at the top of the card", () => {
    const html = card(SAMPLE, { message: { tone: "danger", text: S.noAnswer } });
    expect(html).toContain('class="card-alert"');
    expect(html).toContain(S.noAnswer);
  });
});

describe("the Add card", () => {
  const add = (errors = {}, message: { tone: "danger"; text: string } | null = null) =>
    markup(
      h(AddStoreView, {
        form: newForm([SAMPLE]),
        errors,
        pair: pair({ masks: null, open: true, closable: false }),
        saving: false,
        message,
        handlers: { onChange: vi.fn(), onSave: vi.fn(), onCancel: vi.fn(), onGuide: vi.fn() },
      }),
    );

  it("empty fields, the key inputs and the identifier picker open, Cancel and Add store", () => {
    const html = add();
    expect(html).toContain(">Add a store</h3>");
    expect(html.match(/type="password"/g)?.length).toBe(2);
    expect(html).not.toContain('>Cancel</button><button type="submit"'); // the pair has no Cancel of its own
    expect(html).toContain(">Add store</button>");
    expect(html).toContain('value="Download"');
    expect(html).toContain('value="0.15"');
    expect(html).toContain("Shop Manager key guide");
    expect(html).not.toContain(">Change</button>");
  });

  it("the next free shape is chosen (circle is taken by none here, square by the sample)", () => {
    expect(add()).toMatch(/checked="" value="circle"/);
  });

  it("too many stores: 13's line at the top of the card", () => {
    const html = add({}, { tone: "danger", text: S.errors.too_many_stores });
    expect(html).toContain("ShelfSync keeps up to 50 stores. Remove one before adding another.");
  });

  it("field errors at their fields", () => {
    const html = add({ name: S.nameLimit, code: S.codeLimit, keys: S.pairNeeded });
    expect(html).toContain(S.nameLimit);
    expect(html).toContain(S.codeLimit);
    expect(html).toContain(S.pairNeeded);
  });
});

describe("the Remove dialog", () => {
  it("destructive: the danger button, Cancel, and the line that the keys go at once", () => {
    const html = markup(
      h(
        ConfirmDialog as FunctionComponent<Omit<ComponentProps<typeof ConfirmDialog>, "children">>,
        {
          open: false,
          title: S.removeTitle("Sample store"),
          confirmLabel: S.removeConfirm,
          danger: true,
          onConfirm: vi.fn(),
          onCancel: vi.fn(),
        },
        h("p", null, S.removeLead("Sample store")),
        h("p", null, S.removeKeys),
      ),
    );
    expect(html).toContain("Remove Sample store?");
    expect(html).toContain("ShelfSync stops updating Sample store. Nothing on the store itself changes.");
    expect(html).toContain(
      "Its consumer key and secret are deleted from Windows Credential Manager at once. To add the store again, you need its keys.",
    );
    expect(html).toContain('class="btn is-danger"');
    expect(html).toContain(">Remove store</button>");
  });

  it("keyboard: it starts on Cancel, Esc cancels, and the focus goes back to Remove", () => {
    const listeners = new Map<string, (event: { preventDefault(): void }) => void>();
    const dialog = {
      open: false as boolean,
      showModal: vi.fn(() => {
        dialog.open = true;
      }),
      close: vi.fn(() => {
        dialog.open = false;
        listeners.get("close")?.({ preventDefault: () => undefined });
      }),
      addEventListener: (type: string, listener: (event: { preventDefault(): void }) => void) =>
        listeners.set(type, listener),
      removeEventListener: (type: string) => listeners.delete(type),
    } satisfies DialogElement;
    const log: string[] = [];
    const node = (name: string): Focusable => ({ focus: () => log.push(name), isConnected: true });
    const onCancel = vi.fn();
    const made = dialogBehaviour(dialog, { onCancel, isBusy: () => false });
    made.open(node("Cancel"), node("Remove"));
    expect(log).toEqual(["Cancel"]);
    let prevented = false;
    listeners.get("cancel")?.({ preventDefault: () => (prevented = true) });
    expect(prevented).toBe(true);
    expect(onCancel).toHaveBeenCalledTimes(1);
    made.close();
    expect(log).toEqual(["Cancel", "Remove"]);
  });

  it("while the removal is sent, Esc waits (nothing is half-removed)", () => {
    const listeners = new Map<string, (event: { preventDefault(): void }) => void>();
    const dialog = {
      open: false as boolean,
      showModal: () => {
        dialog.open = true;
      },
      close: () => {
        dialog.open = false;
      },
      addEventListener: (type: string, listener: (event: { preventDefault(): void }) => void) =>
        listeners.set(type, listener),
      removeEventListener: (type: string) => listeners.delete(type),
    } satisfies DialogElement;
    const onCancel = vi.fn();
    const made = dialogBehaviour(dialog, { onCancel, isBusy: () => true });
    made.open(null, null);
    listeners.get("cancel")?.({ preventDefault: () => undefined });
    expect(onCancel).not.toHaveBeenCalled();
  });
});

describe("the HealthArea", () => {
  const area = (stores: Store[] | undefined, extra: Partial<Parameters<typeof HealthArea>[0]> = {}) =>
    markup(h(TipProvider, null, h(HealthArea, { stores, storage: null, when, onTest: vi.fn(), ...extra })));

  it("while the list loads: nothing claimed", () => {
    const html = area(undefined);
    expect(html).toContain('aria-label="Connections"');
    expect(html).not.toContain("health-chip");
  });

  it("the list couldn't be read: it says so, never 'no stores'", () => {
    const html = area(undefined, { failed: true });
    expect(html).toContain("Connections can't be shown");
    expect(html).not.toContain("No stores or storage yet");
  });

  it("no store and no storage: 13 Shell's line", () => {
    expect(area([])).toContain("No stores or storage yet");
  });

  it("a healthy store: a read-out with its badge and latency, not a button", () => {
    const html = area([{ ...SAMPLE, health: CONNECTED }]);
    expect(html).toMatch(/<span class="health-chip" tabindex="0"[^>]*>/);
    expect(html).toContain("312 ms");
    expect(html).toContain(" connected");
    expect(html).not.toContain("<button");
  });

  it("a failed store: a button that opens the reason (ERR-01), named for it", () => {
    const html = area([{ ...SAMPLE, health: REFUSED }]);
    expect(html).toMatch(/<button type="button" class="health-chip is-button is-down"[^>]*aria-haspopup="dialog"/);
    expect(html).toContain(">Refused</span>");
    expect(html).toContain(". Show the reason");
  });

  it("an unreachable store says Can't reach", () => {
    const html = area([{ ...SAMPLE, health: { ...REFUSED, state: "unreachable", reason: "timeout" } }]);
    expect(html).toContain(">Can't reach</span>");
  });

  it("a store never tested says so, and is a button that offers the test", () => {
    const html = area([SAMPLE]);
    expect(html).toMatch(/<button type="button" class="health-chip is-button is-unknown"/);
    expect(html).toContain(">Not tested</span>");
  });

  it("a paused store shows as paused, never as failed", () => {
    const html = area([{ ...SAMPLE, state: "paused", health: REFUSED }]);
    expect(html).toContain(">Paused</span>");
    expect(html).not.toContain("Refused");
    expect(html).not.toContain("<button");
  });

  it("one chip per store, each with its badge", () => {
    const html = area([
      { ...SAMPLE, health: CONNECTED },
      { ...SAMPLE, id: 8, code: "SB", name: "Second sample", shape: "circle", color: "indigo", health: REFUSED },
    ]);
    expect(html).toContain('SA<span class="sr-only"> (Sample store)</span>');
    expect(html).toContain('SB<span class="sr-only"> (Second sample)</span>');
  });
});
