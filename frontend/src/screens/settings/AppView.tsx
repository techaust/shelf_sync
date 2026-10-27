import { KeyRound, LoaderCircle, type LucideIcon, Monitor, Moon, RefreshCw, Save, Sun } from "lucide-react";
import type { FormEvent } from "react";
import { Alert, type AlertTone } from "../../components/Alert";
import { FieldError } from "../../components/FieldError";
import { Switch } from "../../components/Switch";
import type { ThemePreference } from "../../theme/theme";
import type { AppForm, AppFormErrors } from "./forms";
import { A, U } from "./wording";

const THEMES: { value: ThemePreference; Icon: LucideIcon }[] = [
  { value: "system", Icon: Monitor },
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
];

export interface AppResult {
  tone: AlertTone;
  text: string;
  note: string | null;
}

export interface AppHandlers {
  onTheme: (theme: ThemePreference) => void;
  onChange: (next: Partial<AppForm>) => void;
  onSave: (event: FormEvent) => void;
  onReset: () => void;
}

export function AppLoading() {
  return (
    <section className="card" aria-busy="true">
      <div className="card__head">
        <span className="sk is-title" />
      </div>
      <div className="card__body form-stack">
        <span className="sk is-block" />
        <span className="sk is-line" />
        <span className="sk is-line" />
        <span className="sk is-field" />
      </div>
    </section>
  );
}

export function AppFailed({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="card">
      <div className="card-alert">
        <Alert
          tone="danger"
          title={text}
          action={
            <button type="button" className="btn is-compact" onClick={onRetry}>
              <RefreshCw className="icon" aria-hidden="true" />
              {U.tryAgain}
            </button>
          }
        />
      </div>
    </section>
  );
}

function NumberField({
  id,
  label,
  value,
  error,
  hint,
  unit,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  hint?: string;
  unit?: string;
  onChange: (value: string) => void;
}) {
  const described = [error ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;
  const input = (
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
  );
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="unit-input">
        {input}
        {unit ? <span>{unit}</span> : null}
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

/** Settings › App (SET-06, LOG-01) for one form state. The form's limits are the API's (forms.ts). */
export function AppView({
  form,
  errors,
  theme,
  installed,
  saving,
  result,
  themeFailed,
  handlers,
}: {
  form: AppForm;
  errors: AppFormErrors;
  theme: ThemePreference;
  installed: boolean;
  saving: boolean;
  result: AppResult | null;
  themeFailed: boolean;
  handlers: AppHandlers;
}) {
  return (
    <section className="card" aria-labelledby="app-title">
      <div className="card__head">
        <h3 className="card__title is-sm" id="app-title">
          {A.cardTitle}
        </h3>
      </div>
      <form className="app-form" onSubmit={handlers.onSave} noValidate aria-labelledby="app-title">
        <div className="card__body form-stack">
          <fieldset className="radio-list is-inline">
            <legend className="field__label">{A.theme}</legend>
            {THEMES.map(({ value, Icon }) => (
              <label key={value} className="radio-row">
                <input
                  type="radio"
                  name="app-theme"
                  value={value}
                  checked={theme === value}
                  onChange={() => handlers.onTheme(value)}
                />
                <Icon className="icon" aria-hidden="true" />
                <span>{A.themeOptions[value]}</span>
              </label>
            ))}
            {themeFailed ? <FieldError text={A.themeFailed} wide /> : null}
          </fieldset>
          <Switch
            id="app-start"
            label={A.startWithWindows}
            checked={installed ? form.startWithWindows : false}
            hint={installed ? A.startHint : A.startDevelopment}
            locked={!installed}
            onChange={(next) => handlers.onChange({ startWithWindows: next })}
          />
          <Switch
            id="app-notify"
            label={A.notifications}
            checked={form.notifications}
            hint={A.notificationsHint}
            onChange={(next) => handlers.onChange({ notifications: next })}
          />
          <div className="form-grid">
            <NumberField
              id="app-port"
              label={A.port}
              value={form.port}
              error={errors.port}
              hint={A.portHint}
              onChange={(port) => handlers.onChange({ port })}
            />
            <NumberField
              id="app-logs"
              label={A.logs}
              value={form.logDays}
              error={errors.logDays}
              unit={A.days}
              onChange={(logDays) => handlers.onChange({ logDays })}
            />
          </div>
          <div className="danger-zone">
            <div>
              <p className="danger-zone__title">{A.resetTitle}</p>
              <p className="muted">{`${A.resetText} ${A.resetLine}`}</p>
            </div>
            <button type="button" className="btn is-danger" onClick={handlers.onReset}>
              <KeyRound className="icon" aria-hidden="true" />
              {A.resetConfirm}
            </button>
          </div>
        </div>
        <div className="form-foot">
          <div className="form-foot__result">
            {result ? (
              <Alert tone={result.tone} title={result.text}>
                {result.note}
              </Alert>
            ) : null}
          </div>
          <button
            type="submit"
            className="btn is-primary"
            aria-disabled={saving || undefined}
            aria-busy={saving || undefined}
          >
            {saving ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : (
              <Save className="icon" aria-hidden="true" />
            )}
            {A.save}
          </button>
        </div>
      </form>
    </section>
  );
}
