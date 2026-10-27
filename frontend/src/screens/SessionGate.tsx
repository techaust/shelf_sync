import { Lock, RefreshCw, Unplug } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import type { SessionState } from "../api/session";
import { AppBar } from "../components/AppBar";

/** 13 section 3, "Signed out", split into a heading and its line (the same words). */
export const SIGNED_OUT_TITLE = "This tab isn't signed in.";
export const OPEN_FROM_TRAY = "Open ShelfSync from the tray icon or the Start menu.";
/** Proposed wording (section 4 of the run file): ShelfSync gave no answer at all. */
export const UNREACHABLE_TITLE = "ShelfSync didn't answer, so this tab can't sign in.";
/** Proposed wording (section 4 of the run file): ShelfSync answered, but not with a sign-in or a sign-out. */
export const refusedTitle = (status: number) =>
  status > 0 ? `ShelfSync refused to sign this tab in (HTTP ${status}).` : "ShelfSync refused to sign this tab in.";

function Bare({ children, busy = false }: { children?: ReactNode; busy?: boolean }) {
  return (
    <div className="app-shell is-bare">
      <AppBar home={false} />
      <main id="main" className="gate" aria-busy={busy}>
        {children}
      </main>
    </div>
  );
}

function Panel({ Icon, title, text, action }: { Icon: typeof Lock; title: string; text: string; action?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = "ShelfSync";
    heading.current?.focus();
  }, []);
  return (
    <section className="card gate__panel" aria-labelledby="gate-title">
      <span className="gate__icon">
        <Icon className="icon-lg" />
      </span>
      <h1 className="gate__title" id="gate-title" ref={heading} tabIndex={-1}>
        {title}
      </h1>
      <p className="gate__text">{text}</p>
      {action}
    </section>
  );
}

/**
 * Everything the tab shows before (or instead of) the shell: nothing while it checks (a request to 127.0.0.1
 * takes milliseconds; no spinner), the signed-out state (13 section 3; no retry loop, no token prompt), and the two
 * cases where ShelfSync gives no usable answer.
 */
export function SessionGate({ state, onRetry }: { state: SessionState; onRetry: () => void }) {
  switch (state.kind) {
    case "checking":
      return <Bare busy />;
    case "signed_out":
      return (
        <Bare>
          <Panel Icon={Lock} title={SIGNED_OUT_TITLE} text={OPEN_FROM_TRAY} />
        </Bare>
      );
    case "unreachable":
      return (
        <Bare>
          <Panel
            Icon={Unplug}
            title={UNREACHABLE_TITLE}
            text={OPEN_FROM_TRAY}
            action={
              state.canRetry ? (
                <button type="button" className="btn" onClick={onRetry}>
                  <RefreshCw className="icon" />
                  Try again
                </button>
              ) : undefined
            }
          />
        </Bare>
      );
    case "refused":
      return (
        <Bare>
          <Panel Icon={Unplug} title={refusedTitle(state.status)} text={OPEN_FROM_TRAY} />
        </Bare>
      );
    case "signed_in":
      return <Bare busy />; // the router is being made (one render)
  }
}
