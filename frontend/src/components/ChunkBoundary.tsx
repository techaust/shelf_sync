import { RefreshCw } from "lucide-react";
import { Component, type ReactNode } from "react";
import { Alert } from "./Alert";

/** The words (proposed (m2.5b round 1) for 13): a part of the page whose code couldn't be fetched, most often a tab
 *  left open across an update (its old chunk names are gone from the new install). */
export const CHUNK_FAILED = {
  title: "This part of ShelfSync couldn't be loaded.",
  text: "ShelfSync may have been updated since this tab was opened. Reload the page to get the current version.",
  reload: "Reload page",
};

/** The panel shown in place of the part that failed: one line, one action. The shell around it stays. */
export function ChunkFailed({ onReload }: { onReload: () => void }) {
  return (
    <section className="card chunk-failed">
      <div className="card-alert is-alone">
        <Alert
          tone="danger"
          title={CHUNK_FAILED.title}
          action={
            <button type="button" className="btn is-compact" onClick={onReload}>
              <RefreshCw className="icon" aria-hidden="true" />
              {CHUNK_FAILED.reload}
            </button>
          }
        >
          {CHUNK_FAILED.text}
        </Alert>
      </div>
    </section>
  );
}

interface Props {
  children: ReactNode;
  /** Tests pass a fake; the page reloads itself. */
  reload?: () => void;
}

/**
 * Wraps a Suspense around lazily loaded code (the Settings pages, the Help guides; m2.5b). If the code can't be
 * fetched, or the part throws while it renders, this part shows ChunkFailed and the rest of the app keeps working.
 * Give it a `key` that changes with what it shows (the sub-page, the guide), so moving on tries again.
 */
export class ChunkBoundary extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  // No componentDidCatch: nothing is logged (the page keeps no log, and the error text holds a file address).

  override render(): ReactNode {
    if (this.state.failed) return <ChunkFailed onReload={this.props.reload ?? (() => window.location.reload())} />;
    return this.props.children;
  }
}
