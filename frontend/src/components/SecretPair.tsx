import { CircleAlert, CircleDashed, KeyRound } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import { FieldError } from "./FieldError";

export interface SecretPairText {
  legend: string;
  first: string;
  second: string;
  placeholder: string;
  hint: string;
  notSet: string;
  unreadable: string;
  replace: string;
  cancel: string;
}

/**
 * Two secrets that only make sense together (a WooCommerce consumer key and secret), as one SecretField (05 section 5;
 * 06 section 3). The page never holds a stored value: it shows the API's masks (`ck_••••abcd`), "Not set", or, when
 * Credential Manager couldn't be read (`readable` false), "Couldn't be read", never "Not set" then (11, 2026-10-28).
 * "Replace keys" opens two password inputs; they are uncontrolled (what is typed is never in React state or a value
 * attribute) and the card that owns them reads, sends and clears them as one pair.
 *
 * A pair that saves on its own (Settings › Storage's two S3 pairs, m2.5b) adds its buttons: `rowActions` beside
 * "Replace keys" (Remove), `editActions` beside the open inputs (Save); `description` is one line on what the pair
 * is for, under the legend.
 */
export function SecretPair({
  id,
  text,
  masks,
  readable,
  open,
  closable,
  locked = false,
  maxLength,
  errors,
  firstRef,
  secondRef,
  onOpen,
  onCancel,
  onTyped,
  description,
  rowActions,
  editActions,
}: {
  id: string;
  text: SecretPairText;
  /** null: the pair is new (the Add card), so there is nothing saved to show. */
  masks: { first: string | null; second: string | null } | null;
  readable: boolean;
  open: boolean;
  /** Whether Cancel is offered (there is a saved pair to go back to). */
  closable: boolean;
  locked?: boolean;
  maxLength: number;
  errors: { pair?: string | undefined; first?: string | undefined; second?: string | undefined };
  firstRef: RefObject<HTMLInputElement | null>;
  secondRef: RefObject<HTMLInputElement | null>;
  onOpen: () => void;
  onCancel: () => void;
  onTyped: () => void;
  description?: string;
  rowActions?: ReactNode;
  editActions?: ReactNode;
}) {
  const rows: [string, string | null][] = masks
    ? [
        [text.first, masks.first],
        [text.second, masks.second],
      ]
    : [];
  const input = (which: "first" | "second") => {
    const inputId = `${id}-${which}`;
    const error = errors[which];
    const described = [
      error ? `${inputId}-error` : "",
      errors.pair ? `${id}-error` : "",
      description ? `${id}-description` : "",
      `${id}-hint`,
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <div className="field">
        <label className="field__label is-quiet" htmlFor={inputId}>
          {which === "first" ? text.first : text.second}
        </label>
        <input
          ref={which === "first" ? firstRef : secondRef}
          id={inputId}
          className="input mono"
          type="password"
          autoComplete="off"
          spellCheck={false}
          maxLength={maxLength}
          placeholder={text.placeholder}
          aria-invalid={error || errors.pair ? true : undefined}
          aria-describedby={described}
          disabled={locked}
          onChange={onTyped}
        />
        {error ? <FieldError id={`${inputId}-error`} text={error} /> : null}
      </div>
    );
  };

  return (
    <fieldset className="field span-2 secret-pair">
      <legend className="field__label">{text.legend}</legend>
      {description ? (
        <p className="secret-pair__description" id={`${id}-description`}>
          {description}
        </p>
      ) : null}
      {rows.length ? (
        <div className="secret-pair__row">
          <dl className="secret-pair__masks">
            {rows.map(([label, mask]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {!readable ? (
                    <span className="band-pill is-warning">
                      <CircleAlert className="icon" aria-hidden="true" />
                      {text.unreadable}
                    </span>
                  ) : mask ? (
                    <span className="mono secret-pair__mask">{mask}</span>
                  ) : (
                    <span className="band-pill is-neutral">
                      <CircleDashed className="icon" aria-hidden="true" />
                      {text.notSet}
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {!open ? (
            <button
              id={`${id}-replace`}
              type="button"
              className="btn is-compact"
              aria-disabled={locked || undefined}
              onClick={() => {
                if (!locked) onOpen();
              }}
            >
              <KeyRound className="icon" aria-hidden="true" />
              {text.replace}
            </button>
          ) : null}
          {rowActions && !open ? rowActions : null}
        </div>
      ) : null}
      {open ? (
        <div className="secret-pair__edit">
          {input("first")}
          {input("second")}
          {editActions ? (
            <div className="secret-pair__acts">
              {editActions}
              {closable ? (
                <button type="button" className="btn is-compact" onClick={onCancel}>
                  {text.cancel}
                </button>
              ) : null}
            </div>
          ) : closable ? (
            <button type="button" className="btn is-compact secret-pair__cancel" onClick={onCancel}>
              {text.cancel}
            </button>
          ) : null}
        </div>
      ) : null}
      {errors.pair ? <FieldError id={`${id}-error`} text={errors.pair} /> : null}
      <p className="field__hint" id={`${id}-hint`}>
        {text.hint}
      </p>
    </fieldset>
  );
}
