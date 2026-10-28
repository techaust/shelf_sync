import { Check, Pencil } from "lucide-react";
import { STORE_SHAPES, type StoreShape } from "../api/stores";
import { S } from "../screens/settings/storesWording";
import { STORE_PALETTE, type StoreColor } from "../styles/storePalette";
import { FieldError } from "./FieldError";
import { StoreBadge, StoreDot } from "./StoreBadge";

const COLOURS = Object.keys(STORE_PALETTE) as StoreColor[];

export interface IdentifierValue {
  shape: StoreShape;
  color: StoreColor;
  code: string;
}

/**
 * The store identifier picker (05 section 2.3; SET-01): the shapes the API accepts, the colour keys in storePalette.ts
 * and the two-letter code, with a live StoreBadge preview. Each choice is a radio drawn as the shape in the store's
 * colour beside its name, so a choice never rests on colour alone. Closed, it is one line ("Circle, indigo, code GF")
 * and a Change button that opens it (a disclosure: aria-expanded, aria-controls). The Add card keeps it open.
 */
export function IdentifierPicker({
  id,
  name,
  value,
  open,
  closable,
  codeError,
  onToggle,
  onChange,
}: {
  id: string;
  /** The store's name, for the preview's screen-reader text. */
  name: string;
  value: IdentifierValue;
  open: boolean;
  /** false on the Add card: the picker stays open. */
  closable: boolean;
  codeError: string | undefined;
  onToggle: (open: boolean) => void;
  onChange: (next: Partial<IdentifierValue>) => void;
}) {
  const dot = STORE_PALETTE[value.color];
  const preview = { code: value.code, name: name.trim(), shape: value.shape, dot };
  const summary = S.identSummary(S.shapes[value.shape], S.colours[value.color], value.code);
  const panel = `${id}-panel`;
  const codeDescribed = [codeError ? `${id}-code-error` : "", `${id}-hint`].filter(Boolean).join(" ");

  return (
    <div className="field span-2 ident-field">
      <span className="field__label" id={`${id}-label`}>
        {S.identifier}
      </span>
      <div className="ident">
        <span className="ident__swatch" aria-hidden="true">
          <StoreDot shape={value.shape} dot={dot} />
        </span>
        {open ? (
          // the live badge once there is a code to show; until then the tile alone shows the shape and colour
          value.code ? (
            <span className="ident__preview">
              <span className="sr-only">{`${S.preview}: `}</span>
              <StoreBadge store={preview} large />
            </span>
          ) : null
        ) : (
          <span className="ident__summary">{summary}</span>
        )}
        {closable ? (
          <button
            type="button"
            className="btn is-compact"
            aria-expanded={open}
            aria-controls={open ? panel : undefined}
            aria-describedby={`${id}-label`}
            onClick={() => onToggle(!open)}
          >
            {open ? <Check className="icon" aria-hidden="true" /> : <Pencil className="icon" aria-hidden="true" />}
            {open ? S.done : S.change}
          </button>
        ) : null}
      </div>
      {open ? (
        <div className="ident__panel" id={panel}>
          <fieldset className="radio-list is-tiles">
            <legend className="field__label">{S.shape}</legend>
            {STORE_SHAPES.map((shape) => (
              <label key={shape} className="radio-row">
                <input
                  type="radio"
                  name={`${id}-shape`}
                  value={shape}
                  checked={value.shape === shape}
                  onChange={() => onChange({ shape })}
                />
                <StoreDot shape={shape} dot={dot} />
                <span>{S.shapes[shape]}</span>
              </label>
            ))}
          </fieldset>
          <fieldset className="radio-list is-tiles">
            <legend className="field__label">{S.colour}</legend>
            {COLOURS.map((color) => (
              <label key={color} className="radio-row">
                <input
                  type="radio"
                  name={`${id}-colour`}
                  value={color}
                  checked={value.color === color}
                  onChange={() => onChange({ color })}
                />
                <StoreDot shape={value.shape} dot={STORE_PALETTE[color]} />
                <span>{S.colours[color]}</span>
              </label>
            ))}
          </fieldset>
          <div className="field ident__code">
            <label className="field__label" htmlFor={`${id}-code`}>
              {S.code}
            </label>
            <input
              id={`${id}-code`}
              className="input"
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="characters"
              maxLength={2}
              value={value.code}
              aria-invalid={codeError ? true : undefined}
              aria-describedby={codeDescribed}
              onChange={(event) => onChange({ code: event.target.value })}
            />
          </div>
        </div>
      ) : null}
      {codeError ? <FieldError id={`${id}-code-error`} text={codeError} /> : null}
      <p className="field__hint" id={`${id}-hint`}>
        {S.identifierHint}
      </p>
    </div>
  );
}
