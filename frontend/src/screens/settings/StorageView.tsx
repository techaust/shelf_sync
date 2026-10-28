import { BookOpen, HardDrive, KeyRound, LoaderCircle, Plug, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import type { FormEvent, ReactNode, RefObject } from "react";
import type { S3Slot } from "../../api/storage";
import { Alert, type AlertTone } from "../../components/Alert";
import { FieldError } from "../../components/FieldError";
import { SecretPair, type SecretPairText } from "../../components/SecretPair";
import {
  BUCKET_MAX,
  ENDPOINT_MAX,
  KEY_INPUT_MAX,
  type KeyPairErrors,
  REGION_MAX,
  type StorageErrors,
  type StorageField,
  type StorageForm,
  TEMPLATE_MAX,
} from "./storageModel";
import { ST } from "./storageWording";

export interface Line {
  tone: AlertTone;
  text: string;
}

// ---------- the page's states ----------

export function StorageLoading() {
  return (
    <div className="storage" aria-busy="true">
      {[4, 2].map((fields) => (
        <section className="card" key={fields}>
          <div className="card__head">
            <span className="sk is-title" />
          </div>
          <div className="card__body form-grid">
            {Array.from({ length: fields }, (_, n) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder blocks, never reordered
              <div className="field" key={n}>
                <span className="sk is-line" />
                <span className="sk is-field" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function StorageFailed({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="card">
      <div className="card-alert is-alone">
        <Alert
          tone="danger"
          title={text}
          action={
            <button type="button" className="btn is-compact" onClick={onRetry}>
              <RefreshCw className="icon" aria-hidden="true" />
              {ST.tryAgain}
            </button>
          }
        />
      </div>
    </section>
  );
}

/** Nothing put in yet: the mockup's empty state, and the one action. */
export function StorageEmpty({ onAdd }: { onAdd: () => void }) {
  return (
    <section className="card">
      <div className="empty">
        <HardDrive className="icon-lg empty__icon" aria-hidden="true" />
        <p className="empty__text">{ST.emptyText}</p>
        <p className="empty__sub">{ST.emptySub}</p>
        <button type="button" className="btn is-primary" onClick={onAdd}>
          <Plus className="icon" aria-hidden="true" />
          {ST.add}
        </button>
      </div>
    </section>
  );
}

// ---------- the five settings ----------

function Field({
  id,
  label,
  value,
  error,
  hint,
  unit,
  maxLength,
  mono = false,
  numeric = false,
  span = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  hint?: ReactNode;
  unit?: string;
  maxLength: number;
  mono?: boolean;
  numeric?: boolean;
  span?: boolean;
  onChange: (value: string) => void;
}) {
  const described = [error ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;
  const input = (
    <input
      id={id}
      className={`input${mono ? " mono" : ""}${numeric ? " num" : ""}`}
      inputMode={numeric ? "numeric" : undefined}
      autoComplete="off"
      spellCheck={false}
      maxLength={maxLength}
      value={value}
      aria-invalid={error ? true : undefined}
      aria-describedby={described}
      onChange={(event) => onChange(event.target.value)}
    />
  );
  return (
    <div className={`field${span ? " span-2" : ""}`}>
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {unit ? (
        <div className="unit-input">
          {input}
          <span>{unit}</span>
        </div>
      ) : (
        input
      )}
      {error ? <FieldError id={`${id}-error`} text={error} /> : null}
      {hint ? (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export const STORAGE_FIELD_IDS: Record<StorageField, string> = {
  endpoint: "storage-endpoint",
  region: "storage-region",
  bucket: "storage-bucket",
  keep: "storage-keep",
  template: "storage-template",
};

/** The bucket's card (SET-02): the five settings and one Save, as the approved mockup's storagePage() lays them out. */
export function StorageSettingsCard({
  form,
  errors,
  aws,
  dirty,
  saving,
  result,
  onChange,
  onSave,
}: {
  form: StorageForm;
  errors: StorageErrors;
  /** The saved endpoint is empty: the card is titled "Amazon S3". */
  aws: boolean;
  dirty: boolean;
  saving: boolean;
  result: Line | null;
  onChange: (next: Partial<StorageForm>) => void;
  onSave: (event: FormEvent) => void;
}) {
  const [before, key, after] = ST.templateHint;
  return (
    <section className="card" aria-labelledby="storage-title">
      <div className="card__head">
        <h3 className="card__title is-sm storage__title" id="storage-title">
          <HardDrive className="icon" aria-hidden="true" />
          {aws ? ST.titleAws : ST.titleOther}
        </h3>
      </div>
      <form onSubmit={onSave} noValidate aria-labelledby="storage-title">
        <div className="card__body form-grid">
          <Field
            id={STORAGE_FIELD_IDS.endpoint}
            label={ST.endpoint}
            value={form.endpoint}
            error={errors.endpoint}
            hint={ST.endpointHint}
            maxLength={ENDPOINT_MAX + 20}
            mono
            onChange={(endpoint) => onChange({ endpoint })}
          />
          <Field
            id={STORAGE_FIELD_IDS.region}
            label={ST.region}
            value={form.region}
            error={errors.region}
            hint={ST.regionHint}
            maxLength={REGION_MAX + 20}
            mono
            onChange={(region) => onChange({ region })}
          />
          <Field
            id={STORAGE_FIELD_IDS.bucket}
            label={ST.bucket}
            value={form.bucket}
            error={errors.bucket}
            hint={ST.bucketHint}
            maxLength={BUCKET_MAX + 20}
            mono
            onChange={(bucket) => onChange({ bucket })}
          />
          <Field
            id={STORAGE_FIELD_IDS.keep}
            label={ST.keep}
            value={form.keep}
            error={errors.keep}
            hint={ST.keepHint}
            unit={ST.keepUnit}
            maxLength={6}
            numeric
            onChange={(keep) => onChange({ keep })}
          />
          <Field
            id={STORAGE_FIELD_IDS.template}
            label={ST.template}
            value={form.template}
            error={errors.template}
            hint={
              <>
                {before}
                <span className="mono">{key}</span>
                {after}
              </>
            }
            maxLength={TEMPLATE_MAX + 20}
            mono
            span
            onChange={(template) => onChange({ template })}
          />
        </div>
        <div className="form-foot">
          <div className="form-foot__result">{result ? <Alert tone={result.tone} title={result.text} /> : null}</div>
          <button
            id="storage-save"
            type="submit"
            className="btn is-primary"
            aria-disabled={saving || !dirty || undefined}
            aria-busy={saving || undefined}
          >
            {saving ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : (
              <Save className="icon" aria-hidden="true" />
            )}
            {ST.save}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------- the two key pairs ----------

const pairText = (slot: S3Slot): SecretPairText => ({
  legend: ST.legend[slot],
  first: ST.keyId,
  second: ST.secret,
  placeholder: ST.placeholder,
  hint: ST.keysHint,
  notSet: ST.notSet,
  unreadable: ST.unreadable,
  replace: ST.replace,
  cancel: ST.cancel,
});

export interface KeyPairState {
  masks: { first: string | null; second: string | null };
  readable: boolean;
  /** Both halves are saved (and could be read). */
  set: boolean;
  open: boolean;
  saving: boolean;
  removing: boolean;
  errors: KeyPairErrors;
  /** "Keys saved." / "Keys removed." */
  done: string | null;
  firstRef: RefObject<HTMLInputElement | null>;
  secondRef: RefObject<HTMLInputElement | null>;
}

export interface KeyPairHandlers {
  onOpen: () => void;
  onCancel: () => void;
  onTyped: () => void;
  onSave: (event: FormEvent) => void;
  onRemove: () => void;
}

/** One S3 key pair: its masks (or "Not set", or "Couldn't be read"), Replace keys and Remove keys, and when open the
 *  two password inputs with Save keys. Its own form, so Enter saves this pair and nothing else. */
export function KeyPairPanel({
  slot,
  pair,
  handlers,
}: {
  slot: S3Slot;
  pair: KeyPairState;
  handlers: KeyPairHandlers;
}) {
  const id = `storage-${slot}`;
  const busy = pair.saving || pair.removing;
  const removable = pair.set || !pair.readable;
  return (
    <form className="key-pair" onSubmit={handlers.onSave} noValidate aria-label={ST.legend[slot]}>
      <SecretPair
        id={id}
        text={pairText(slot)}
        masks={pair.masks}
        readable={pair.readable}
        open={pair.open}
        closable={removable}
        locked={busy}
        maxLength={KEY_INPUT_MAX}
        errors={pair.errors}
        firstRef={pair.firstRef}
        secondRef={pair.secondRef}
        onOpen={handlers.onOpen}
        onCancel={handlers.onCancel}
        onTyped={handlers.onTyped}
        description={ST.purpose[slot]}
        rowActions={
          removable ? (
            <button
              id={`${id}-remove`}
              type="button"
              className="btn is-compact is-ghost"
              aria-disabled={busy || undefined}
              aria-busy={pair.removing || undefined}
              onClick={() => {
                if (!busy) handlers.onRemove();
              }}
            >
              {pair.removing ? (
                <LoaderCircle className="icon is-spinning" aria-hidden="true" />
              ) : (
                <Trash2 className="icon" aria-hidden="true" />
              )}
              {ST.removeKeys}
            </button>
          ) : null
        }
        editActions={
          <button
            id={`${id}-save`}
            type="submit"
            className="btn is-compact is-primary"
            aria-disabled={busy || undefined}
            aria-busy={pair.saving || undefined}
          >
            {pair.saving ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : (
              <KeyRound className="icon" aria-hidden="true" />
            )}
            {ST.saveKeys}
          </button>
        }
      />
      <p className="sr-only" role="status">
        {pair.done ?? ""}
      </p>
      {pair.done ? (
        <p className="secret-field__done" aria-hidden="true">
          {pair.done}
        </p>
      ) : null}
    </form>
  );
}

export function KeysCard({ children }: { children: ReactNode }) {
  return (
    <section className="card" aria-labelledby="storage-keys-title">
      <div className="card__head">
        <h3 className="card__title is-sm" id="storage-keys-title">
          {ST.keysTitle}
        </h3>
      </div>
      <div className="card__body key-pairs">{children}</div>
    </section>
  );
}

/** Where the Test button will be (m2.7): what is and isn't checked yet, and the S3 access policy guide. */
export function StorageTestNote({ lines, onGuide }: { lines: string[]; onGuide: () => void }) {
  return (
    <div className="storage-note">
      <Plug className="icon storage-note__icon" aria-hidden="true" />
      <div className="storage-note__text">
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      <button type="button" className="btn is-ghost" onClick={onGuide}>
        <BookOpen className="icon" aria-hidden="true" />
        {ST.guide}
      </button>
    </div>
  );
}
