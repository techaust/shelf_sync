import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { createStore, deleteStore, putStoreKeys, STORES_QUERY_KEY, type Store, updateStore } from "../../api/stores";
import { useServices } from "../../app/services";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { helpStore } from "../../components/help/helpModel";
import { S } from "../../lib/storesWording";
import { storeTests, useStoreTest } from "../../lib/storeTests";
import {
  AddStoreButton,
  AddStoreView,
  type CardMessage,
  type PairState,
  StoreCardView,
  StoresEmpty,
  StoresFailed,
  StoresLoading,
} from "./StoresView";
import {
  codeInput,
  formFrom,
  isDirty,
  newForm,
  placeError,
  planAdd,
  planSave,
  type StoreErrors,
  type StoreForm,
} from "./storesModel";
import { useRunStoreTest, useStoresQuery } from "./useStores";

const openKeyGuide = () => helpStore.open("shop-manager-key");

/** The order fields are checked in, so the first invalid one takes the focus. */
const FIELD_ORDER: (keyof StoreErrors)[] = [
  "name",
  "url",
  "mainButton",
  "spacing",
  "keys",
  "consumerKey",
  "consumerSecret",
  "code",
];

function focusFirstError(prefix: string, errors: StoreErrors) {
  const first = FIELD_ORDER.find((field) => errors[field]);
  const target: Record<string, string> = {
    name: "name",
    url: "url",
    mainButton: "button",
    spacing: "spacing",
    keys: "keys-first",
    consumerKey: "keys-first",
    consumerSecret: "keys-second",
    code: "ident-code",
  };
  if (first) document.getElementById(`${prefix}-${target[first]}`)?.focus();
}

/** Runs a focus move after the next render, once what it moves to is on the page (an effect, not a frame callback:
 *  a tab that isn't painting never runs those). */
function useAfterRender(): (run: () => void) => void {
  const next = useRef<(() => void) | null>(null);
  useEffect(() => {
    const run = next.current;
    next.current = null;
    run?.();
  });
  return (run) => {
    next.current = run;
  };
}

/** Applies a change typed into the form (the code is upper-cased and kept to two letters). */
function typed(next: Partial<StoreForm>): Partial<StoreForm> {
  return next.code === undefined ? next : { ...next, code: codeInput(next.code) };
}

function useCachedStore() {
  const queryClient = useQueryClient();
  return (saved: Store) =>
    queryClient.setQueryData<Store[]>(STORES_QUERY_KEY, (list) =>
      list ? list.map((store) => (store.id === saved.id ? saved : store)) : list,
    );
}

/** One saved store: its form (only what was edited is held), its key pair, Save, Pause or Resume, Test, Remove. */
function StoreCard({
  store,
  takenCodes,
  onRemove,
  announce,
}: {
  store: Store;
  takenCodes: string[];
  onRemove: (store: Store) => void;
  announce: (text: string) => void;
}) {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const cache = useCachedStore();
  const runTest = useRunStoreTest();
  const test = useStoreTest(store.id);
  const [edits, setEdits] = useState<Partial<StoreForm>>({});
  const [errors, setErrors] = useState<StoreErrors>({});
  const [identOpen, setIdentOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  const [keysTyped, setKeysTyped] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [message, setMessage] = useState<CardMessage | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const secretRef = useRef<HTMLInputElement>(null);
  const afterRender = useAfterRender();
  const prefix = `store-${store.id}`;

  const stored = formFrom(store);
  // A field edited back to its saved value is no longer an edit, so a refresh shows the saved value again.
  const form: StoreForm = { ...stored, ...edits };
  const dirty = isDirty(store, edits, keysTyped);
  const keysSet = store.keys.consumer_key !== null && store.keys.consumer_secret !== null;
  const showKeys = keysOpen || (store.keys_readable && !keysSet);

  function clearKeys() {
    if (keyRef.current) keyRef.current.value = "";
    if (secretRef.current) secretRef.current.value = "";
    setKeysTyped(false);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    // what to send, decided without React (planSave, storesModel.test.ts)
    const plan = planSave({
      store,
      edits,
      keysOpen: showKeys,
      typedKey: keyRef.current?.value ?? "",
      typedSecret: secretRef.current?.value ?? "",
      takenCodes,
    });
    setSaved(null);
    setMessage(null);
    if (plan.kind === "errors") {
      setErrors(plan.errors);
      if (plan.openKeys) setKeysOpen(true);
      if (plan.openIdentifier) setIdentOpen(true);
      afterRender(() => focusFirstError(prefix, plan.errors));
      return;
    }
    if (plan.kind === "none") return; // nothing changed: the button says so (aria-disabled)
    setErrors({});
    setSaving(true);
    const keysSent = plan.kind === "keys" || plan.keysSent;
    try {
      if (plan.kind === "keys") {
        await putStoreKeys(api, store.id, plan.keys.consumer_key, plan.keys.consumer_secret);
        await queryClient.invalidateQueries({ queryKey: STORES_QUERY_KEY });
      } else {
        cache(await updateStore(api, store.id, plan.body));
      }
      // the last test was of the old keys or address
      if (keysSent || (plan.kind === "patch" && plan.body.url)) storeTests.forget(store.id);
      clearKeys();
      setKeysOpen(false);
      setEdits({});
      setIdentOpen(false);
      setSaved(plan.kind === "keys" ? S.keysSaved : S.saved);
      // the key inputs it was typed in are gone: the focus stays in the card, on Save
      afterRender(() => document.getElementById(`${prefix}-save`)?.focus());
    } catch (failure) {
      const placed = placeError(failure, keysSent);
      if (placed.field === "card") setMessage({ tone: placed.tone, text: placed.text });
      else setErrors({ [placed.field]: placed.text });
      if (placed.field === "keys") setKeysOpen(true);
      if (placed.field === "code") setIdentOpen(true);
      if (failure instanceof ApiError && failure.code === "not_found") {
        void queryClient.invalidateQueries({ queryKey: STORES_QUERY_KEY });
      }
    } finally {
      setSaving(false);
    }
  }

  async function pauseOrResume() {
    if (pausing) return;
    const next = store.state === "paused" ? "active" : "paused";
    setPausing(true);
    setMessage(null);
    try {
      cache(await updateStore(api, store.id, { state: next }));
      announce(next === "paused" ? S.pausedDone(store.name) : S.resumedDone(store.name));
    } catch (failure) {
      setMessage({ tone: "danger", text: placeError(failure, false).text });
    } finally {
      setPausing(false);
    }
  }

  const pair: PairState = {
    masks: { first: store.keys.consumer_key, second: store.keys.consumer_secret },
    readable: store.keys_readable,
    open: showKeys,
    closable: keysSet || !store.keys_readable,
    keyRef,
    secretRef,
    onOpen: () => {
      setKeysOpen(true);
      afterRender(() => keyRef.current?.focus());
    },
    onCancel: () => {
      clearKeys();
      setKeysOpen(false);
      setErrors(({ keys, consumerKey, consumerSecret, ...rest }) => rest);
    },
    onTyped: () => {
      setKeysTyped(Boolean(keyRef.current?.value || secretRef.current?.value));
      setErrors(({ keys, consumerKey, consumerSecret, ...rest }) => rest);
      setSaved(null);
    },
  };

  return (
    <StoreCardView
      store={store}
      form={form}
      errors={errors}
      identOpen={identOpen}
      pair={pair}
      dirty={dirty}
      saving={saving}
      pausing={pausing}
      message={message}
      saved={saved}
      test={test}
      handlers={{
        onChange: (next) => {
          const change = typed(next);
          setEdits((current) => ({ ...current, ...change }));
          setErrors((current) => {
            const kept = { ...current };
            for (const key of Object.keys(change)) delete kept[key as keyof StoreErrors];
            if ("url" in change) delete kept.keys;
            return kept;
          });
          setSaved(null);
        },
        onIdentToggle: setIdentOpen,
        onSave: (event) => void save(event),
        onTest: () => runTest(store.id),
        onPause: () => void pauseOrResume(),
        onRemove: () => onRemove(store),
        onGuide: openKeyGuide,
      }}
    />
  );
}

/** The Add card: the same fields, empty, with the key pair and the identifier picker open. */
function AddStoreCard({
  stores,
  onAdded,
  onCancel,
}: {
  stores: Store[];
  onAdded: (store: Store) => void;
  onCancel: () => void;
}) {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StoreForm>(() => newForm(stores));
  const [errors, setErrors] = useState<StoreErrors>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<CardMessage | null>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const secretRef = useRef<HTMLInputElement>(null);
  const afterRender = useAfterRender();
  const prefix = "store-new";

  useEffect(() => {
    document.getElementById(`${prefix}-name`)?.focus();
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const plan = planAdd({
      form,
      typedKey: keyRef.current?.value ?? "",
      typedSecret: secretRef.current?.value ?? "",
      takenCodes: stores.map((store) => store.code),
    });
    setMessage(null);
    if (plan.kind === "errors") {
      setErrors(plan.errors);
      afterRender(() => focusFirstError(prefix, plan.errors));
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      const added = await createStore(api, plan.body);
      if (keyRef.current) keyRef.current.value = "";
      if (secretRef.current) secretRef.current.value = "";
      queryClient.setQueryData<Store[]>(STORES_QUERY_KEY, (list) => (list ? [...list, added] : [added]));
      onAdded(added);
    } catch (failure) {
      const placed = placeError(failure, true);
      if (placed.field === "card") setMessage({ tone: placed.tone, text: placed.text });
      else setErrors({ [placed.field]: placed.text });
      if (placed.field !== "card") afterRender(() => focusFirstError(prefix, { [placed.field]: placed.text }));
    } finally {
      setSaving(false);
    }
  }

  const pair: PairState = {
    masks: null,
    readable: true,
    open: true,
    closable: false,
    keyRef,
    secretRef,
    onOpen: () => undefined,
    onCancel: () => undefined,
    onTyped: () => setErrors(({ keys, consumerKey, consumerSecret, ...rest }) => rest),
  };

  return (
    <AddStoreView
      form={form}
      errors={errors}
      pair={pair}
      saving={saving}
      message={message}
      handlers={{
        onChange: (next) => {
          const change = typed(next);
          setForm((current) => ({ ...current, ...change }));
          setErrors((current) => {
            const kept = { ...current };
            for (const key of Object.keys(change)) delete kept[key as keyof StoreErrors];
            return kept;
          });
        },
        onSave: (event) => void save(event),
        onCancel,
        onGuide: openKeyGuide,
      }}
    />
  );
}

/**
 * Settings › Stores (UI-SET; SET-01): one card per store, as the approved mockup has it, then Add a store. Every API
 * error code is shown with its 13 wording at the field it belongs to, or at the top of its card.
 */
export function StoresPage() {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const query = useStoresQuery();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Store | null>(null); // kept while the dialog closes, so its title stays
  const [removeOpen, setRemoveOpen] = useState(false);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [focusStore, setFocusStore] = useState<number | null>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  const afterRender = useAfterRender();
  const stores = query.data;
  const codes = useMemo(() => (stores ?? []).map((store) => ({ id: store.id, code: store.code })), [stores]);

  // After an add, the focus goes to the new card's title.
  useEffect(() => {
    if (focusStore === null) return;
    document.getElementById(`store-${focusStore}-title`)?.focus();
    setFocusStore(null);
  }, [focusStore]);

  if (query.isPending) return <StoresLoading />;
  if (query.isError && !stores) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? S.loadRefused(failure.status) : S.loadFailed;
    return <StoresFailed text={text} onRetry={() => void query.refetch()} />;
  }
  const list = stores ?? [];

  async function remove() {
    if (!removing || !removeOpen || removeBusy) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await deleteStore(api, removing.id);
      const gone = removing;
      queryClient.setQueryData<Store[]>(STORES_QUERY_KEY, (current) =>
        current?.filter((store) => store.id !== gone.id),
      );
      storeTests.forget(gone.id);
      setRemoveOpen(false);
      setAnnouncement(S.removed(gone.name));
    } catch (failure) {
      const placed = placeError(failure, false);
      setRemoveError(placed.text);
      if (failure instanceof ApiError && failure.code === "not_found") {
        void queryClient.invalidateQueries({ queryKey: STORES_QUERY_KEY });
      }
    } finally {
      setRemoveBusy(false);
    }
  }

  const add = () => {
    setAnnouncement("");
    setAdding(true);
  };

  return (
    <div className="stores">
      {query.isError ? (
        <p className="stores__stale field__hint" role="status">
          {S.staleNotice}
        </p>
      ) : null}
      {list.length === 0 && !adding ? <StoresEmpty onAdd={add} /> : null}
      {list.map((store) => (
        <StoreCard
          key={store.id}
          store={store}
          takenCodes={codes.filter((entry) => entry.id !== store.id).map((entry) => entry.code)}
          onRemove={(target) => {
            setRemoveError(null);
            setRemoving(target);
            setRemoveOpen(true);
          }}
          announce={setAnnouncement}
        />
      ))}
      {adding ? (
        <AddStoreCard
          stores={list}
          onAdded={(added) => {
            setAdding(false);
            setAnnouncement(S.added(added.name));
            setFocusStore(added.id);
          }}
          onCancel={() => {
            setAdding(false);
            afterRender(() => addButton.current?.focus());
          }}
        />
      ) : list.length > 0 ? (
        <AddStoreButton onAdd={add} buttonRef={addButton} />
      ) : null}
      <p className="sr-only" role="status">
        {announcement}
      </p>
      <ConfirmDialog
        open={removeOpen}
        title={S.removeTitle(removing?.name ?? "")}
        confirmLabel={S.removeConfirm}
        ConfirmIcon={Trash2}
        danger
        busy={removeBusy}
        error={removeError}
        // the removed card's Remove is gone: the focus goes to the Stores sub-page title, not the page's h1
        fallbackFocus={() => document.querySelector<HTMLElement>(".settings-main [data-nav-focus]")}
        onCancel={() => setRemoveOpen(false)}
        onConfirm={() => void remove()}
      >
        <p>{S.removeLead(removing?.name ?? "")}</p>
        <p className="muted">{S.removeKeys}</p>
      </ConfirmDialog>
    </div>
  );
}
