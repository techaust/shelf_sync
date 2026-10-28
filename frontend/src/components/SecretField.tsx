import { CircleCheck, CircleDashed, KeyRound, LoaderCircle, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { FieldError } from "./FieldError";

export interface SecretFieldText {
  label: string;
  newLabel: string;
  hint: string;
  placeholder: string;
  saved: string;
  notSet: string;
  replace: string;
  save: string;
  remove: string;
  cancel: string;
  savedDone: string;
  removedDone: string;
}

/** Where the typed value lives: the input element itself (uncontrolled), never React state or a value attribute. */
export interface SecretInput {
  value: string;
}

/**
 * One Save (review item 10): the value is read from the input, checked and sent; the input is emptied only once the
 * save is accepted, and kept (to correct it) after a refusal or no answer. Resolves with the line to show, or null.
 */
export async function submitSecret(
  field: SecretInput,
  check: (value: string) => string | null,
  onSave: (value: string) => Promise<void>,
): Promise<{ saved: boolean; error: string | null }> {
  const typed = field.value;
  const refused = check(typed);
  if (refused) return { saved: false, error: refused };
  try {
    await onSave(typed);
  } catch (failure) {
    return { saved: false, error: failure instanceof Error ? failure.message : String(failure) };
  }
  field.value = "";
  return { saved: true, error: null };
}

/**
 * SecretField (05 section 5; 06 section 3): a secret that is stored, never shown. The page never holds a stored
 * value, masked or not: it shows only "saved" or "not set" (and the expiry, when known) from the API. A new value is
 * typed into a password input, sent once, and the input is emptied after the save. Save and Remove. The input is
 * uncontrolled (review item 11): what is typed is never in React state or in the input's value attribute.
 *
 * `check` refuses a value of the wrong shape before it is sent; `onSave` and `onRemove` resolve once the API has
 * answered and the status above is current, and reject with the line to show.
 */
export function SecretField({
  id,
  text,
  set,
  expires = null,
  maxLength,
  check,
  locked = false,
  onSave,
  onRemove,
}: {
  id: string;
  text: SecretFieldText;
  set: boolean;
  expires?: string | null;
  maxLength: number;
  check: (value: string) => string | null;
  locked?: boolean;
  onSave: (value: string) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState<"save" | "remove" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const replace = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"input" | "replace" | null>(null);
  const showInput = !set || editing;

  // After a save, a remove, Replace or Cancel, the focus goes to what is there now (never lost to the page).
  useEffect(() => {
    const target = focusNext.current;
    if (!target) return;
    focusNext.current = null;
    (target === "input" ? input.current : replace.current)?.focus();
  });

  async function save(event: FormEvent) {
    event.preventDefault();
    const field = input.current;
    if (pending || locked || !field) return;
    // the shape first: a refused value never shows the busy Save, even for a moment (re-review low 7)
    const refused = check(field.value);
    if (refused) {
      setError(refused);
      setDone("");
      field.focus();
      return;
    }
    setPending("save");
    setError(null);
    setDone("");
    const result = await submitSecret(field, check, onSave);
    setPending(null);
    if (result.saved) {
      setEditing(false);
      setDone(text.savedDone);
      focusNext.current = "replace";
    } else {
      setError(result.error);
      field.focus();
    }
  }

  async function remove() {
    if (pending || locked) return;
    setPending("remove");
    setError(null);
    setDone("");
    try {
      await onRemove();
      setEditing(false);
      if (input.current) input.current.value = "";
      setDone(text.removedDone);
      focusNext.current = "input";
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(null);
    }
  }

  const described = [error ? `${id}-error` : "", `${id}-hint`].filter(Boolean).join(" ");
  return (
    <fieldset className="field secret-field">
      <legend className="field__label">{text.label}</legend>
      <div className="secret-field__row">
        {set ? (
          <span className="band-pill is-success">
            <CircleCheck className="icon" aria-hidden="true" />
            {text.saved}
          </span>
        ) : (
          <span className="band-pill is-neutral">
            <CircleDashed className="icon" aria-hidden="true" />
            {text.notSet}
          </span>
        )}
        {set && expires ? <span className="secret-field__meta num">{expires}</span> : null}
        {set && !editing ? (
          <span className="secret-field__acts">
            <button
              ref={replace}
              type="button"
              className="btn is-compact"
              aria-disabled={locked || pending !== null || undefined}
              onClick={() => {
                if (locked || pending) return;
                setEditing(true);
                setDone("");
                focusNext.current = "input";
              }}
            >
              <KeyRound className="icon" aria-hidden="true" />
              {text.replace}
            </button>
            <button
              type="button"
              className="btn is-compact is-ghost"
              aria-disabled={locked || pending !== null || undefined}
              aria-busy={pending === "remove" || undefined}
              onClick={remove}
            >
              {pending === "remove" ? (
                <LoaderCircle className="icon is-spinning" aria-hidden="true" />
              ) : (
                <Trash2 className="icon" aria-hidden="true" />
              )}
              {text.remove}
            </button>
          </span>
        ) : null}
      </div>
      {showInput ? (
        <form className="secret-field__edit" onSubmit={save} noValidate>
          <label className="sr-only" htmlFor={id}>
            {text.newLabel}
          </label>
          <input
            ref={input}
            id={id}
            className="input mono"
            type="password"
            autoComplete="off"
            spellCheck={false}
            maxLength={maxLength}
            placeholder={text.placeholder}
            aria-invalid={error ? true : undefined}
            aria-describedby={described}
            disabled={locked}
            onChange={() => {
              if (error) setError(null);
            }}
          />
          <button
            type="submit"
            className="btn is-compact is-primary"
            aria-disabled={locked || pending !== null || undefined}
            aria-busy={pending === "save" || undefined}
          >
            {pending === "save" ? <LoaderCircle className="icon is-spinning" aria-hidden="true" /> : null}
            {text.save}
          </button>
          {set ? (
            <button
              type="button"
              className="btn is-compact"
              onClick={() => {
                if (pending) return;
                setEditing(false);
                setError(null);
                focusNext.current = "replace";
              }}
            >
              {text.cancel}
            </button>
          ) : null}
        </form>
      ) : null}
      {error ? <FieldError id={`${id}-error`} text={error} /> : null}
      <p className="field__hint" id={`${id}-hint`}>
        {text.hint}
      </p>
      <p className="sr-only" role="status">
        {done}
      </p>
      {done ? (
        <p className="secret-field__done" aria-hidden="true">
          <CircleCheck className="icon" aria-hidden="true" />
          {done}
        </p>
      ) : null}
    </fieldset>
  );
}
