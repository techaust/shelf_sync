/**
 * Switch (WAI-ARIA switch pattern): a button with role="switch" and aria-checked, a visible label (its <label>, so
 * clicking the words toggles it too) and a helper line it is described by. Space and Enter toggle it, as any button.
 * A locked switch stays focusable (aria-disabled, not disabled), so its reason, in the helper line, is still read.
 */
export function Switch({
  id,
  label,
  checked,
  hint,
  locked = false,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  hint: string;
  locked?: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="switch-row">
      <div className="switch-row__text">
        <label className="switch-row__label" htmlFor={id}>
          {label}
        </label>
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        id={id}
        className="toggle"
        aria-checked={checked}
        aria-describedby={`${id}-hint`}
        aria-disabled={locked || undefined}
        onClick={() => {
          if (!locked) onChange(!checked);
        }}
      >
        <span className="toggle__thumb" aria-hidden="true" />
      </button>
    </div>
  );
}
