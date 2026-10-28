import {
  BookOpen,
  Download,
  FileArchive,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Save,
  Terminal,
  Upload,
} from "lucide-react";
import type { FormEvent, ReactNode, RefObject } from "react";
import { Alert } from "../../components/Alert";
import { FieldError } from "../../components/FieldError";
import type { DailyFacts, ImportFailure, KeepErrors, KeepForm, Line } from "./backupModel";
import { PASSPHRASE_INPUT_MAX } from "./backupModel";
import { B } from "./backupWording";

/** A line that names a file: the file's name is shown in IBM Plex Mono (CLAUDE.md conventions), the rest as text. */
export function FileText({ text, name }: { text: string; name: string | null }) {
  if (!name || !text.includes(name)) return <>{text}</>;
  // 13's lines name the file once; the text before it and after it are plain
  const at = text.indexOf(name);
  return (
    <>
      {text.slice(0, at)}
      <span className="mono file-name">{name}</span>
      {text.slice(at + name.length)}
    </>
  );
}

// ---------- the page's states ----------

/** The daily card while its facts load (the export and import card needs nothing to load). */
export function BackupLoading() {
  return (
    <section className="card" aria-busy="true">
      <div className="card__head">
        <span className="sk is-title" />
      </div>
      <div className="card__body form-stack">
        <span className="sk is-block" />
        <span className="sk is-field" />
      </div>
    </section>
  );
}

export function BackupFailed({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="card">
      <div className="card-alert is-alone">
        <Alert
          tone="danger"
          title={text}
          action={
            <button type="button" className="btn is-compact" onClick={onRetry}>
              <RefreshCw className="icon" aria-hidden="true" />
              {B.tryAgain}
            </button>
          }
        />
      </div>
    </section>
  );
}

// ---------- the daily backups ----------

function NumberField({
  id,
  label,
  value,
  error,
  unit,
  hint,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  unit: string;
  hint?: string;
  onChange: (value: string) => void;
}) {
  const described = [error ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="unit-input">
        <input
          id={id}
          className="input num"
          inputMode="numeric"
          autoComplete="off"
          spellCheck={false}
          maxLength={6}
          value={value}
          aria-invalid={error ? true : undefined}
          aria-describedby={described}
          onChange={(event) => onChange(event.target.value)}
        />
        <span>{unit}</span>
      </div>
      {error ? <FieldError id={`${id}-error`} text={error} /> : null}
      {hint ? (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export const KEEP_FIELD_IDS: Record<keyof KeepForm, string> = { kept: "backup-kept", snapshots: "backup-snapshots" };

/** "What's kept" (BAK-01, SET-05): the last and next daily backup, how many are kept, the two keep settings, and how
 *  a backup is restored (a command, not a button). */
export function DailyCard({
  facts,
  form,
  errors,
  dirty,
  saving,
  result,
  onChange,
  onSave,
  onRestoreGuide,
}: {
  facts: DailyFacts;
  form: KeepForm;
  errors: KeepErrors;
  dirty: boolean;
  saving: boolean;
  result: Line | null;
  onChange: (next: Partial<KeepForm>) => void;
  onSave: (event: FormEvent) => void;
  onRestoreGuide: () => void;
}) {
  return (
    <section className="card" aria-labelledby="backup-daily-title">
      <div className="card__head">
        <h3 className="card__title is-sm" id="backup-daily-title">
          {B.dailyTitle}
        </h3>
      </div>
      <form onSubmit={onSave} noValidate aria-labelledby="backup-daily-title">
        <div className="card__body form-stack">
          <dl className="backup-facts">
            <div>
              <dt>{B.lastLabel}</dt>
              <dd className="num">
                {facts.last ?? <span className="muted">{B.none}</span>}
                {facts.size ? <span className="backup-facts__size">{facts.size}</span> : null}
              </dd>
            </div>
            {facts.next ? (
              <div>
                <dt>{B.nextLabel}</dt>
                <dd className="num">{facts.next}</dd>
              </div>
            ) : null}
            <div>
              <dt>{B.countLabel}</dt>
              <dd className="num">{B.copies(facts.count)}</dd>
            </div>
          </dl>
          <div className="form-grid">
            <NumberField
              id={KEEP_FIELD_IDS.kept}
              label={B.kept}
              value={form.kept}
              error={errors.kept}
              unit={B.keptUnit}
              onChange={(kept) => onChange({ kept })}
            />
            <NumberField
              id={KEEP_FIELD_IDS.snapshots}
              label={B.snapshots}
              value={form.snapshots}
              error={errors.snapshots}
              unit={B.snapshotsUnit}
              hint={B.snapshotsHint}
              onChange={(snapshots) => onChange({ snapshots })}
            />
          </div>
        </div>
        <div className="form-foot">
          <div className="form-foot__result">{result ? <Alert tone={result.tone} title={result.text} /> : null}</div>
          <button
            id="backup-save"
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
            {B.save}
          </button>
        </div>
      </form>
      {/* restoring is a command, not a button (brief): the summary, and the guide in the Help panel */}
      <div className="restore-note">
        <Terminal className="icon restore-note__icon" aria-hidden="true" />
        <p>{facts.last || facts.count > 0 ? B.restoreLine : B.restoreNone}</p>
        {facts.last || facts.count > 0 ? (
          <button type="button" className="btn is-ghost" onClick={onRestoreGuide}>
            <BookOpen className="icon" aria-hidden="true" />
            {B.restoreLink}
          </button>
        ) : null}
      </div>
    </section>
  );
}

// ---------- export and import ----------

function Passphrase({
  id,
  label,
  inputRef,
  error,
  hint,
  autoComplete,
  locked,
  onTyped,
}: {
  id: string;
  label: ReactNode;
  inputRef: RefObject<HTMLInputElement | null>;
  error: string | undefined;
  hint?: string;
  autoComplete: "new-password" | "off";
  locked: boolean;
  onTyped: () => void;
}) {
  const described = [error ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {/* uncontrolled: what is typed is never in React state or a value attribute, and is cleared after each try */}
      <input
        ref={inputRef}
        id={id}
        className="input"
        type="password"
        autoComplete={autoComplete}
        spellCheck={false}
        maxLength={PASSPHRASE_INPUT_MAX}
        aria-invalid={error ? true : undefined}
        aria-describedby={described}
        disabled={locked}
        onChange={onTyped}
      />
      {error ? <FieldError id={`${id}-error`} text={error} /> : null}
      {hint ? (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function RunButton({
  id,
  label,
  Icon,
  running,
  blocked,
  primary = true,
  type = "submit",
  onClick,
}: {
  id: string;
  label: string;
  Icon: typeof Download;
  running: boolean;
  blocked: boolean;
  primary?: boolean;
  type?: "submit" | "button";
  onClick?: () => void;
}) {
  return (
    <button
      id={id}
      type={type}
      className={`btn${primary ? " is-primary" : ""}`}
      aria-disabled={running || blocked || undefined}
      aria-busy={running || undefined}
      onClick={onClick}
    >
      {running ? (
        <LoaderCircle className="icon is-spinning" aria-hidden="true" />
      ) : (
        <Icon className="icon" aria-hidden="true" />
      )}
      {label}
    </button>
  );
}

export interface ExportState {
  includeSecrets: boolean;
  errors: { first?: string; second?: string };
  running: boolean;
  /** Another export or import runs: this one waits. */
  blocked: boolean;
  result: Line | null;
  firstRef: RefObject<HTMLInputElement | null>;
  secondRef: RefObject<HTMLInputElement | null>;
}

export interface ExportHandlers {
  onIncludeSecrets: (next: boolean) => void;
  onTyped: () => void;
  onExport: (event: FormEvent) => void;
}

/** Export settings (SET-05): with or without secrets; with them, a passphrase typed twice. */
export function ExportSection({ state, handlers }: { state: ExportState; handlers: ExportHandlers }) {
  return (
    <form className="transfer__part" onSubmit={handlers.onExport} noValidate aria-labelledby="backup-export-title">
      <h4 className="transfer__title" id="backup-export-title">
        <Download className="icon" aria-hidden="true" />
        {B.exportTitle}
      </h4>
      <p className="muted">{state.includeSecrets ? B.exportSecrets : B.exportPlain}</p>
      <label className="check-row">
        <input
          type="checkbox"
          id="backup-secrets"
          checked={state.includeSecrets}
          disabled={state.running}
          onChange={(event) => handlers.onIncludeSecrets(event.target.checked)}
        />
        <span>{B.includeSecrets}</span>
      </label>
      {state.includeSecrets ? (
        <div className="form-grid">
          <Passphrase
            id="backup-pass"
            label={B.passphrase}
            inputRef={state.firstRef}
            error={state.errors.first}
            hint={B.passphraseHint}
            autoComplete="new-password"
            locked={state.running}
            onTyped={handlers.onTyped}
          />
          <Passphrase
            id="backup-pass-again"
            label={B.passphraseAgain}
            inputRef={state.secondRef}
            error={state.errors.second}
            autoComplete="new-password"
            locked={state.running}
            onTyped={handlers.onTyped}
          />
        </div>
      ) : null}
      <div className="transfer__acts">
        <RunButton
          id="backup-export"
          label={B.exportButton}
          Icon={Download}
          running={state.running}
          blocked={state.blocked}
        />
      </div>
      {state.result ? (
        <Alert
          tone={state.result.tone}
          title={<FileText text={state.result.text} name={fileIn(state.result.text)} />}
        />
      ) : null}
    </form>
  );
}

/** The exported file's name inside a result line ("Exported shelfsync-export-2026-10-29.ssbak."), for the mono. */
function fileIn(text: string): string | null {
  return /[A-Za-z0-9][A-Za-z0-9._-]*\.ssbak/.exec(text)?.[0] ?? null;
}

export interface ChosenFile {
  name: string;
  /** From the file's own header; null when the page can't tell (the server decides). */
  encrypted: boolean | null;
}

export interface ImportState {
  chosen: ChosenFile | null;
  passphraseError: string | undefined;
  running: boolean;
  blocked: boolean;
  result: ImportFailure | Line | null;
  /** The name the result line is about (the file chosen when it was given). */
  resultFile: string | null;
  passRef: RefObject<HTMLInputElement | null>;
  fileRef: RefObject<HTMLInputElement | null>;
}

export interface ImportHandlers {
  onPick: () => void;
  onFile: (file: File | null) => void;
  onTyped: () => void;
  onImport: (event: FormEvent) => void;
  onRetryPassphrase: () => void;
}

/** Import from file… (SET-05): for a new install or a new PC. The file is read here only after its size is checked;
 *  an encrypted one asks for its passphrase. */
export function ImportSection({ state, handlers }: { state: ImportState; handlers: ImportHandlers }) {
  const { chosen, result } = state;
  const wrong = result && "passphrase" in result && result.passphrase === "wrong";
  return (
    <form className="transfer__part" onSubmit={handlers.onImport} noValidate aria-labelledby="backup-import-title">
      <h4 className="transfer__title" id="backup-import-title">
        <Upload className="icon" aria-hidden="true" />
        {B.importTitle}
      </h4>
      <p className="muted">{B.importText}</p>
      {/* the Windows file picker, opened by the button below; never focused itself */}
      <input
        ref={state.fileRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        accept=".ssbak,application/json"
        onChange={(event) => {
          const file = event.target.files?.[0] ?? null;
          event.target.value = ""; // the same file can be chosen again
          handlers.onFile(file);
        }}
      />
      {chosen ? (
        <div className="chosen-file">
          <FileArchive className="icon chosen-file__icon" aria-hidden="true" />
          <span className="mono file-name">{chosen.name}</span>
          {chosen.encrypted === true ? (
            <span className="band-pill is-neutral">
              <LockKeyhole className="icon" aria-hidden="true" />
              {B.chosenEncrypted}
            </span>
          ) : chosen.encrypted === false ? (
            <span className="band-pill is-neutral">{B.chosenPlain}</span>
          ) : null}
        </div>
      ) : null}
      {chosen?.encrypted ? (
        <div className="transfer__field">
          <Passphrase
            id="backup-import-pass"
            label={<FileText text={B.importPassphrase(chosen.name)} name={chosen.name} />}
            inputRef={state.passRef}
            error={state.passphraseError}
            autoComplete="off"
            locked={state.running}
            onTyped={handlers.onTyped}
          />
        </div>
      ) : null}
      <div className="transfer__acts">
        {chosen ? (
          <RunButton
            id="backup-import"
            label={B.importGo}
            Icon={Upload}
            running={state.running}
            blocked={state.blocked}
          />
        ) : null}
        <RunButton
          id="backup-pick"
          label={chosen ? B.importAnother : B.importButton}
          Icon={FileArchive}
          running={false}
          blocked={state.running || state.blocked}
          primary={false}
          type="button"
          onClick={() => {
            if (!state.running && !state.blocked) handlers.onPick();
          }}
        />
      </div>
      {result ? (
        <Alert
          tone={result.tone}
          title={<FileText text={result.text} name={state.resultFile} />}
          action={
            wrong && chosen?.encrypted ? (
              <button type="button" className="btn is-compact" onClick={handlers.onRetryPassphrase}>
                <KeyRound className="icon" aria-hidden="true" />
                {B.tryAnother}
              </button>
            ) : undefined
          }
        />
      ) : null}
    </form>
  );
}

export function TransferCard({ children }: { children: ReactNode }) {
  return (
    <section className="card" aria-labelledby="backup-transfer-title">
      <div className="card__head">
        <h3 className="card__title is-sm" id="backup-transfer-title">
          {B.transferTitle}
        </h3>
      </div>
      <div className="transfer">{children}</div>
    </section>
  );
}
