import { CircleAlert, CircleCheck, CircleDashed, LoaderCircle, Plug, TriangleAlert } from "lucide-react";
import type { ResultLine } from "../lib/storeHealth";
import { S } from "../lib/storesWording";

// Test connection's button and its one-line result (SET-01, ERR-01), shared by a store's card on Settings › Stores and
// the health popover in the app bar. The result is never colour alone: each tone has its own icon and the words.

const LINE_ICON: Record<ResultLine["tone"], typeof CircleCheck> = {
  success: CircleCheck,
  warning: CircleAlert,
  danger: TriangleAlert,
  neutral: CircleDashed,
};

/** The result line, or the progress line while a test runs; "Tested <when>." under it when known. */
export function TestResult({ line, at, running }: { line: ResultLine; at: string | null; running: boolean }) {
  if (running) {
    return (
      <p className="test-result is-running">
        <LoaderCircle className="icon is-spinning" aria-hidden="true" />
        <span>{S.testing}</span>
      </p>
    );
  }
  const Icon = LINE_ICON[line.tone];
  return (
    <p className={`test-result is-${line.tone}`}>
      <Icon className="icon" aria-hidden="true" />
      <span>
        <span className="num">{line.text}</span>
        {at ? <span className="test-result__when num">{S.testedAt(at)}</span> : null}
      </span>
    </p>
  );
}

export function TestButton({
  running,
  onTest,
  compact = false,
}: {
  running: boolean;
  onTest: () => void;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      className={`btn${compact ? " is-compact" : ""}`}
      aria-disabled={running || undefined}
      aria-busy={running || undefined}
      onClick={() => {
        if (!running) onTest();
      }}
    >
      {running ? (
        <LoaderCircle className="icon is-spinning" aria-hidden="true" />
      ) : (
        <Plug className="icon" aria-hidden="true" />
      )}
      {S.test}
    </button>
  );
}
