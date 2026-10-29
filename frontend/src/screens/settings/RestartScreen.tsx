import { CircleCheck, RefreshCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Phase } from "./updatesModel";
import { U } from "./wording";

// The restart panel after an accepted Install or Roll back (SYS-06, SYS-07). Its own module, so the shell can show it
// on any screen while Settings › Updates itself loads only when it is opened (the React.lazy split, m2.5b).

/** After an accepted Install or Roll back: ShelfSync closes and opens again; the page waits, then reloads. */
export function Restarting({
  version,
  late,
  back,
}: {
  version: string;
  late: boolean;
  back: null | "new_tab" | "running";
}) {
  // The button that started it is gone: the focus moves to this panel's title, so it is read and not lost.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus(), []);
  const text = back === "running" ? U.backRunning(version) : back === "new_tab" ? U.backText : U.restartingText;
  return (
    <section className="card restart-panel" aria-labelledby="restart-title">
      <div className="restart-panel__body" role="status">
        <span className="restart-panel__icon">
          {back ? (
            <CircleCheck className="icon-lg" aria-hidden="true" />
          ) : (
            <RefreshCcw className="icon-lg" aria-hidden="true" />
          )}
        </span>
        <div className="restart-panel__text">
          <h3 className="restart-panel__title" id="restart-title" ref={title} tabIndex={-1}>
            {back ? U.backTitle : U.restartingTitle}
          </h3>
          <p className="muted num">{text}</p>
          {late && !back ? <p className="restart-panel__late">{U.restartingLate}</p> : null}
        </div>
      </div>
      {back ? null : (
        <div className="progress is-indeterminate" aria-hidden="true">
          <span />
        </div>
      )}
    </section>
  );
}

/**
 * The restart panel in the shell, wherever the owner is (re-review, medium): while ShelfSync restarts, every screen
 * but Settings › Updates (which shows it itself) shows the panel, so a 401 there never lands on the lock panel.
 * Not when the new version already knows this tab ("running"): the screens work again.
 */
export function shellTakesOver(phase: Phase, pathname: string): boolean {
  return phase.kind === "restarting" && phase.back !== "running" && pathname !== "/settings/updates";
}

export function RestartScreen({ phase }: { phase: Extract<Phase, { kind: "restarting" }> }) {
  return (
    <div className="page">
      <Restarting version={phase.version} late={phase.late} back={phase.back} />
    </div>
  );
}
