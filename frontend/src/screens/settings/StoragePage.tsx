import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  getStorage,
  removeS3Keys,
  type S3Slot,
  STORAGE_QUERY_KEY,
  type StorageSettings,
  saveS3Keys,
  saveStorage,
} from "../../api/storage";
import { useServices } from "../../app/services";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { helpStore } from "../../components/help/helpModel";
import {
  KeyPairPanel,
  KeysCard,
  type Line,
  STORAGE_FIELD_IDS,
  StorageEmpty,
  StorageFailed,
  StorageLoading,
  StorageSettingsCard,
  StorageTestNote,
} from "./StorageView";
import {
  checkKeyPair,
  checkStorageForm,
  firstError,
  type KeyPairErrors,
  pairState,
  type StorageErrors,
  type StorageForm,
  storageDirty,
  storageEmpty,
  storageError,
  storageFormFrom,
  testLines,
} from "./storageModel";
import { ST } from "./storageWording";
import { useSwitchPhase } from "./switchStore";

const openGuide = () => helpStore.open("s3-policy");

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

/** One S3 key pair: what it shows, and its Save. The typed values stay in the two inputs (uncontrolled), are trimmed
 *  and sent as one pair, and are cleared once the save is accepted. Remove is confirmed by the page's dialog. */
function KeyPair({
  slot,
  storage,
  onRemove,
  removing,
  done,
  setDone,
}: {
  slot: S3Slot;
  storage: StorageSettings;
  onRemove: (slot: S3Slot) => void;
  removing: boolean;
  done: string | null;
  setDone: (slot: S3Slot, text: string | null) => void;
}) {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<KeyPairErrors>({});
  const firstRef = useRef<HTMLInputElement>(null);
  const secondRef = useRef<HTMLInputElement>(null);
  const afterRender = useAfterRender();
  const id = `storage-${slot}`;
  const { set, masks } = pairState(storage, slot);
  const readable = storage.keys_readable;
  const showInputs = open || (readable && !set);

  function clear() {
    if (firstRef.current) firstRef.current.value = "";
    if (secondRef.current) secondRef.current.value = "";
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || removing) return;
    const checked = checkKeyPair(firstRef.current?.value ?? "", secondRef.current?.value ?? "");
    setDone(slot, null);
    if (checked.errors) {
      setErrors(checked.errors);
      const target = checked.errors.second && !checked.errors.first ? "second" : "first";
      document.getElementById(`${id}-${target}`)?.focus();
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      await saveS3Keys(api, slot, checked.pair.accessKeyId, checked.pair.secretAccessKey);
      clear();
      // the masks come only from a fresh read
      await queryClient.invalidateQueries({ queryKey: STORAGE_QUERY_KEY });
      setOpen(false);
      setDone(slot, ST.keysSaved);
      // the inputs it was typed in are gone: the focus goes to the pair's Replace keys
      afterRender(() => document.getElementById(`${id}-replace`)?.focus());
    } catch (failure) {
      setErrors({ pair: storageError(failure, "keys") });
      firstRef.current?.focus();
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyPairPanel
      slot={slot}
      pair={{
        masks,
        readable,
        set,
        open: showInputs,
        saving,
        removing,
        errors,
        done,
        firstRef,
        secondRef,
      }}
      handlers={{
        onOpen: () => {
          setOpen(true);
          setDone(slot, null);
          afterRender(() => firstRef.current?.focus());
        },
        onCancel: () => {
          clear();
          setOpen(false);
          setErrors({});
          afterRender(() => document.getElementById(`${id}-replace`)?.focus());
        },
        onTyped: () => {
          if (errors.pair || errors.first || errors.second) setErrors({});
          if (done) setDone(slot, null);
        },
        onSave: (event) => void save(event),
        onRemove: () => onRemove(slot),
      }}
    />
  );
}

/** The settings form, started from what is stored; a save puts what was saved back into it and into the cache. */
function StorageForms({ storage, stale }: { storage: StorageSettings; stale: boolean }) {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StorageForm>(() => storageFormFrom(storage));
  const [errors, setErrors] = useState<StorageErrors>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Line | null>(null);
  const [done, setDoneState] = useState<Record<S3Slot, string | null>>({ rw: null, ro: null });
  const [removeSlot, setRemoveSlot] = useState<S3Slot>("rw"); // kept while the dialog closes, so its title stays
  const [removeOpen, setRemoveOpen] = useState(false);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const setDone = (slot: S3Slot, text: string | null) => setDoneState((current) => ({ ...current, [slot]: text }));

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const checked = checkStorageForm(form);
    if (checked.errors) {
      setErrors(checked.errors);
      setResult(null);
      const first = firstError(checked.errors);
      if (first) document.getElementById(STORAGE_FIELD_IDS[first])?.focus();
      return;
    }
    if (!storageDirty(form, storage)) return; // nothing changed: the button says so (aria-disabled)
    setErrors({});
    setSaving(true);
    setResult(null);
    try {
      const saved = await saveStorage(api, checked.values);
      queryClient.setQueryData<StorageSettings>(STORAGE_QUERY_KEY, (old) => (old ? { ...old, ...saved } : old));
      setForm(storageFormFrom(saved));
      setResult({ tone: "success", text: ST.saved });
    } catch (failure) {
      setResult({ tone: "danger", text: storageError(failure, "settings") });
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!removeOpen || removeBusy) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await removeS3Keys(api, removeSlot);
      await queryClient.invalidateQueries({ queryKey: STORAGE_QUERY_KEY });
      setRemoveOpen(false);
      setDone(removeSlot, ST.keysRemoved);
    } catch (failure) {
      setRemoveError(storageError(failure, "remove"));
    } finally {
      setRemoveBusy(false);
    }
  }

  return (
    <div className="storage">
      {stale ? (
        <p className="stores__stale field__hint" role="status">
          {ST.staleNotice}
        </p>
      ) : null}
      <StorageSettingsCard
        form={form}
        errors={errors}
        aws={storage.s3_endpoint === ""}
        dirty={storageDirty(form, storage)}
        saving={saving}
        result={result}
        onChange={(next) => {
          setForm((current) => ({ ...current, ...next }));
          setErrors((current) => {
            const kept = { ...current };
            for (const key of Object.keys(next)) delete kept[key as keyof StorageErrors];
            return kept;
          });
          setResult(null);
        }}
        onSave={(event) => void save(event)}
      />
      <KeysCard>
        {(["rw", "ro"] as const).map((slot) => (
          <KeyPair
            key={slot}
            slot={slot}
            storage={storage}
            removing={removeBusy && removeSlot === slot}
            done={done[slot]}
            setDone={setDone}
            onRemove={(target) => {
              setRemoveError(null);
              setRemoveSlot(target);
              setRemoveOpen(true);
            }}
          />
        ))}
      </KeysCard>
      <StorageTestNote lines={testLines(storage)} onGuide={openGuide} />
      <ConfirmDialog
        open={removeOpen}
        title={ST.removeTitle[removeSlot]}
        confirmLabel={ST.removeKeys}
        ConfirmIcon={Trash2}
        danger
        busy={removeBusy}
        error={removeError}
        // the pair's Remove is gone once its keys are: the focus goes to the pair's first input, now open
        fallbackFocus={() => document.getElementById(`storage-${removeSlot}-first`)}
        onCancel={() => setRemoveOpen(false)}
        onConfirm={() => void remove()}
      >
        <p>{ST.removeLead}</p>
        <p className="muted">{ST.removeNote[removeSlot]}</p>
      </ConfirmDialog>
    </div>
  );
}

/** Settings › Storage (UI-SET; SET-02): the bucket's five settings and the two S3 key pairs, with no Test button
 *  until the S3 update (m2.7). */
export function StoragePage() {
  const { api } = useServices();
  const restarting = useSwitchPhase().kind === "restarting";
  const query = useQuery({
    queryKey: STORAGE_QUERY_KEY,
    queryFn: () => getStorage(api),
    enabled: !restarting,
  });
  const [started, setStarted] = useState(false);
  const afterRender = useAfterRender();

  if (query.isPending) return <StorageLoading />;
  if (query.isError && !query.data) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? ST.loadRefused(failure.status) : ST.loadFailed;
    return <StorageFailed text={text} onRetry={() => void query.refetch()} />;
  }
  if (!started && storageEmpty(query.data)) {
    return (
      <StorageEmpty
        onAdd={() => {
          setStarted(true);
          afterRender(() => document.getElementById(STORAGE_FIELD_IDS.endpoint)?.focus());
        }}
      />
    );
  }
  return <StorageForms storage={query.data} stale={query.isError} />;
}
