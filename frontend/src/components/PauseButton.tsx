import { Pause } from "lucide-react";
import { Tip } from "./Tip";

/** Proposed wording (docs/runs/m1a.3-app-shell.md section 4, for 13): why the button can't be used yet. */
export const PAUSE_UNAVAILABLE_TIP = "Nothing runs yet, so there's nothing to pause.";

/**
 * "Pause everything" (UI-SHELL; 05 section 5: always visible in the app bar). Until M5 there is no job queue, so
 * it is shown but not available: aria-disabled rather than disabled, so keyboard users still reach it and hear
 * why. M5 makes it work (Pause, then Resume, which always needs a click).
 */
export function PauseButton() {
  return (
    <Tip content={PAUSE_UNAVAILABLE_TIP}>
      <button type="button" className="btn" aria-disabled="true" onClick={(event) => event.preventDefault()}>
        <Pause className="icon" />
        Pause everything
      </button>
    </Tip>
  );
}
