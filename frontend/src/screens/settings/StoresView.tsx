import {
  BookOpen,
  CircleCheck,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Store as StoreIcon,
  Trash2,
} from "lucide-react";
import type { FormEvent, ReactNode, RefObject } from "react";
import { identifierOf, type Store } from "../../api/stores";
import { Alert, type AlertTone } from "../../components/Alert";
import { FieldError } from "../../components/FieldError";
import { IdentifierPicker, type IdentifierValue } from "../../components/IdentifierPicker";
import { SecretPair, type SecretPairText } from "../../components/SecretPair";
import { StoreBadge } from "../../components/StoreBadge";
import { TestButton, TestResult } from "../../components/StoreTest";
import { healthKind, healthLine, outcomeLine, type ResultLine } from "../../lib/storeHealth";
import { S } from "../../lib/storesWording";
import type { TestEntry } from "../../lib/storeTests";
import { localWhen, type WhenFormat } from "../../lib/time";
import { KEY_MAX_LENGTH, type StoreErrors, type StoreForm } from "./storesModel";

export const PAIR_TEXT: SecretPairText = {
  legend: S.keysLegend,
  first: S.consumerKey,
  second: S.consumerSecret,
  placeholder: S.placeholder,
  hint: S.keysHint,
  notSet: S.notSet,
  unreadable: S.unreadable,
  replace: S.replaceKeys,
  cancel: S.cancel,
};

export interface CardMessage {
  tone: AlertTone;
  text: string;
}

// ---------- the page's states ----------

export function StoresLoading() {
  return (
    <div className="stores" aria-busy="true">
      {[1, 2].map((n) => (
        <section className="card" key={n}>
          <div className="card__head">
            <span className="sk is-title" />
          </div>
          <div className="card__body form-grid">
            {[1, 2, 3, 4].map((m) => (
              <div className="field" key={m}>
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

export function StoresFailed({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="card">
      <div className="card-alert is-alone">
        <Alert
          tone="danger"
          title={text}
          action={
            <button type="button" className="btn is-compact" onClick={onRetry}>
              <RefreshCw className="icon" aria-hidden="true" />
              {S.tryAgain}
            </button>
          }
        />
      </div>
    </section>
  );
}

/** No store yet (13 ERR-07 and the mockup's empty state): what will appear, and the one action. */
export function StoresEmpty({ onAdd }: { onAdd: () => void }) {
  return (
    <section className="card">
      <div className="empty">
        <StoreIcon className="icon-lg empty__icon" aria-hidden="true" />
        <p className="empty__text">{S.emptyText}</p>
        <p className="empty__sub">{S.emptySub}</p>
        <button type="button" className="btn is-primary" onClick={onAdd}>
          <Plus className="icon" aria-hidden="true" />
          {S.addStore}
        </button>
      </div>
    </section>
  );
}

// ---------- the fields a store card and the Add card share ----------

function TextField({
  id,
  label,
  value,
  error,
  hint,
  unit,
  maxLength,
  inputMode,
  type = "text",
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  hint?: string;
  unit?: string;
  maxLength: number;
  inputMode?: "decimal" | "url";
  type?: "text" | "url";
  onChange: (value: string) => void;
}) {
  const described = [error ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;
  const input = (
    <input
      id={id}
      className={`input${unit ? " num" : ""}`}
      type={type}
      inputMode={inputMode}
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
    <div className="field">
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

export interface PairState {
  masks: { first: string | null; second: string | null } | null;
  readable: boolean;
  open: boolean;
  closable: boolean;
  keyRef: RefObject<HTMLInputElement | null>;
  secretRef: RefObject<HTMLInputElement | null>;
  onOpen: () => void;
  onCancel: () => void;
  onTyped: () => void;
}

export function StoreFields({
  id,
  form,
  errors,
  identOpen,
  identClosable,
  pair,
  locked,
  onIdentToggle,
  onChange,
}: {
  id: string;
  form: StoreForm;
  errors: StoreErrors;
  identOpen: boolean;
  identClosable: boolean;
  pair: PairState;
  locked: boolean;
  onIdentToggle: (open: boolean) => void;
  onChange: (next: Partial<StoreForm>) => void;
}) {
  const ident: IdentifierValue = { shape: form.shape, color: form.color, code: form.code };
  return (
    <div className="card__body form-grid">
      <TextField
        id={`${id}-name`}
        label={S.name}
        value={form.name}
        error={errors.name}
        maxLength={80}
        onChange={(name) => onChange({ name })}
      />
      <TextField
        id={`${id}-url`}
        label={S.address}
        value={form.url}
        error={errors.url}
        type="url"
        inputMode="url"
        maxLength={220}
        onChange={(url) => onChange({ url })}
      />
      <TextField
        id={`${id}-button`}
        label={S.mainButton}
        value={form.mainButton}
        error={errors.mainButton}
        maxLength={60}
        onChange={(mainButton) => onChange({ mainButton })}
      />
      <TextField
        id={`${id}-spacing`}
        label={S.spacing}
        value={form.spacing}
        error={errors.spacing}
        hint={S.spacingHint}
        unit={S.seconds}
        inputMode="decimal"
        maxLength={6}
        onChange={(spacing) => onChange({ spacing })}
      />
      <SecretPair
        id={`${id}-keys`}
        text={PAIR_TEXT}
        masks={pair.masks}
        readable={pair.readable}
        open={pair.open}
        closable={pair.closable}
        locked={locked}
        maxLength={KEY_MAX_LENGTH}
        errors={{ pair: errors.keys, first: errors.consumerKey, second: errors.consumerSecret }}
        firstRef={pair.keyRef}
        secondRef={pair.secretRef}
        onOpen={pair.onOpen}
        onCancel={pair.onCancel}
        onTyped={pair.onTyped}
      />
      <IdentifierPicker
        id={`${id}-ident`}
        name={form.name}
        value={ident}
        open={identOpen}
        closable={identClosable}
        codeError={errors.code}
        onToggle={onIdentToggle}
        onChange={onChange}
      />
    </div>
  );
}

function SaveButton({
  id,
  label,
  busy,
  idle,
  Icon,
}: {
  id: string;
  label: string;
  busy: boolean;
  idle: boolean;
  Icon: typeof Save;
}) {
  return (
    <button
      id={id}
      type="submit"
      className="btn is-primary"
      aria-disabled={busy || idle || undefined}
      aria-busy={busy || undefined}
    >
      {busy ? (
        <LoaderCircle className="icon is-spinning" aria-hidden="true" />
      ) : (
        <Icon className="icon" aria-hidden="true" />
      )}
      {label}
    </button>
  );
}

// ---------- Test connection ----------

/** What the test row says: a running test, a refused one, this tab's last answer, or the saved health. */
export function testLineOf(store: Store, entry: TestEntry, when: WhenFormat): { line: ResultLine; at: string | null } {
  if (entry.error)
    return { line: { tone: entry.error.tone === "info" ? "neutral" : "danger", text: entry.error.text }, at: null };
  if (entry.result) return { line: outcomeLine(entry.result), at: when(entry.result.tested_at) };
  return { line: healthLine(store.health), at: when(store.health.tested_at) };
}

function GuideButton({ onGuide }: { onGuide: () => void }) {
  return (
    <button type="button" className="btn is-ghost" onClick={onGuide}>
      <BookOpen className="icon" aria-hidden="true" />
      {S.keyGuide}
    </button>
  );
}

// ---------- a saved store ----------

export interface StoreCardHandlers {
  onChange: (next: Partial<StoreForm>) => void;
  onIdentToggle: (open: boolean) => void;
  onSave: (event: FormEvent) => void;
  onTest: () => void;
  onPause: () => void;
  onRemove: () => void;
  onGuide: () => void;
}

/** One store's card (SET-01), as the approved mockup's storesPage() draws it, for one state of the card. */
export function StoreCardView({
  store,
  form,
  errors,
  identOpen,
  pair,
  dirty,
  saving,
  pausing,
  message,
  saved,
  test,
  when = localWhen,
  handlers,
}: {
  store: Store;
  form: StoreForm;
  errors: StoreErrors;
  identOpen: boolean;
  pair: PairState;
  dirty: boolean;
  saving: boolean;
  pausing: boolean;
  /** A refused or unanswered write that belongs to no field. */
  message: CardMessage | null;
  /** The save's line ("Store saved."). */
  saved: string | null;
  test: TestEntry;
  when?: WhenFormat;
  handlers: StoreCardHandlers;
}) {
  const id = `store-${store.id}`;
  const kind = healthKind(store);
  const paused = store.state === "paused";
  const { line, at } = testLineOf(store, test, when);
  let alert: ReactNode = null;
  if (paused) alert = <Alert tone="info" title={S.pausedLine(store.name)} />;
  else if (kind === "failed" && !test.running && !test.result?.ok) {
    alert = (
      <Alert tone="danger" title={S.cantReach(store.name)}>
        {`${healthLine(store.health).text} ${S.waiting}`}
      </Alert>
    );
  }
  return (
    <section className={`card store-card${paused ? " is-paused" : ""}`} aria-labelledby={`${id}-title`}>
      <div className="card__head store-card__head">
        <h3 className="card__title is-sm store-card__title" id={`${id}-title`} tabIndex={-1}>
          <StoreBadge store={identifierOf(store)} />
          <span className="store-card__name">{store.name}</span>
          {paused ? (
            <span className="band-pill is-neutral">
              <Pause className="icon" aria-hidden="true" />
              {S.paused}
            </span>
          ) : (
            <span className="band-pill is-success">
              <CircleCheck className="icon" aria-hidden="true" />
              {S.active}
            </span>
          )}
        </h3>
        <div className="store-card__acts">
          <button
            type="button"
            className="btn is-compact"
            aria-disabled={pausing || undefined}
            aria-busy={pausing || undefined}
            onClick={handlers.onPause}
          >
            {pausing ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : paused ? (
              <Play className="icon" aria-hidden="true" />
            ) : (
              <Pause className="icon" aria-hidden="true" />
            )}
            {paused ? S.resume : S.pause}
          </button>
          <button type="button" className="btn is-compact is-ghost" onClick={handlers.onRemove}>
            <Trash2 className="icon" aria-hidden="true" />
            {S.remove}
          </button>
        </div>
      </div>
      {alert || message ? (
        <div className="card-alert">
          {alert}
          {message ? <Alert tone={message.tone} title={message.text} /> : null}
        </div>
      ) : null}
      <form onSubmit={handlers.onSave} noValidate aria-labelledby={`${id}-title`}>
        <StoreFields
          id={id}
          form={form}
          errors={errors}
          identOpen={identOpen}
          identClosable
          pair={pair}
          locked={saving}
          onIdentToggle={handlers.onIdentToggle}
          onChange={handlers.onChange}
        />
        <div className="form-foot">
          <div className="form-foot__result">{saved ? <Alert tone="success" title={saved} /> : null}</div>
          <SaveButton id={`${id}-save`} label={S.save} busy={saving} idle={!dirty} Icon={Save} />
        </div>
      </form>
      <div className="test-row">
        <TestButton running={test.running} onTest={handlers.onTest} />
        <div className="test-row__result" role="status">
          <TestResult line={line} at={at} running={test.running} />
        </div>
        <GuideButton onGuide={handlers.onGuide} />
      </div>
    </section>
  );
}

// ---------- the Add card ----------

export interface AddCardHandlers {
  onChange: (next: Partial<StoreForm>) => void;
  onSave: (event: FormEvent) => void;
  onCancel: () => void;
  onGuide: () => void;
}

/** "Add a store": an empty card with the same fields, the key pair open, and the identifier picker open. */
export function AddStoreView({
  form,
  errors,
  pair,
  saving,
  message,
  handlers,
}: {
  form: StoreForm;
  errors: StoreErrors;
  pair: PairState;
  saving: boolean;
  message: CardMessage | null;
  handlers: AddCardHandlers;
}) {
  const id = "store-new";
  return (
    <section className="card store-card is-new" aria-labelledby={`${id}-title`}>
      <div className="card__head store-card__head">
        <h3 className="card__title is-sm" id={`${id}-title`}>
          {S.addTitle}
        </h3>
      </div>
      {message ? (
        <div className="card-alert">
          <Alert tone={message.tone} title={message.text} />
        </div>
      ) : null}
      <form onSubmit={handlers.onSave} noValidate aria-labelledby={`${id}-title`}>
        <StoreFields
          id={id}
          form={form}
          errors={errors}
          identOpen
          identClosable={false}
          pair={pair}
          locked={saving}
          onIdentToggle={() => undefined}
          onChange={handlers.onChange}
        />
        <div className="form-foot">
          <GuideButton onGuide={handlers.onGuide} />
          <span className="form-foot__spacer" />
          <button type="button" className="btn" onClick={handlers.onCancel}>
            {S.cancel}
          </button>
          <SaveButton id={`${id}-save`} label={S.add} busy={saving} idle={false} Icon={Plus} />
        </div>
      </form>
    </section>
  );
}

/** The button under the cards. */
export function AddStoreButton({
  onAdd,
  buttonRef,
}: {
  onAdd: () => void;
  buttonRef?: RefObject<HTMLButtonElement | null>;
}) {
  return (
    // full width under the cards, as the approved mockup draws it
    <button ref={buttonRef} type="button" className="btn stores__add" onClick={onAdd}>
      <Plus className="icon" aria-hidden="true" />
      {S.addStore}
    </button>
  );
}
