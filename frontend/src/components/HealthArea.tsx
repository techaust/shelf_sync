import * as Dialog from "@radix-ui/react-dialog";
import { CircleCheck, CircleDashed, HardDrive, Pause, Plug, TriangleAlert } from "lucide-react";
import {
  type CSSProperties,
  type ReactNode,
  type Ref,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { ConnectionState, StorageHealth } from "../api/placeholder";
import { identifierOf, type Store } from "../api/stores";
import { chipFocusAfterClose, healthKind, healthLine, isProblem, outcomeLine, popoverTitle } from "../lib/storeHealth";
import { S } from "../lib/storesWording";
import type { TestEntry } from "../lib/storeTests";
import { localWhen, type WhenFormat } from "../lib/time";
import { StoreBadge } from "./StoreBadge";
import { TestButton, TestResult } from "./StoreTest";
import { Tip } from "./Tip";

const IDLE: TestEntry = { running: false, result: null, error: null };

/** A healthy or paused store: a read-out, focusable only so its tooltip can be reached from the keyboard. */
function ReadOut({ tip, children, ref }: { tip: string; children: ReactNode; ref?: Ref<HTMLSpanElement> }) {
  return (
    <Tip content={tip}>
      {/* biome-ignore lint/a11y/noNoninteractiveTabindex: a read-out that has to take focus to show its tooltip */}
      <span ref={ref} className="health-chip" tabIndex={0}>
        {children}
      </span>
    </Tip>
  );
}

/**
 * A store that needs you (its last test failed, or it was never tested): a button that opens the reason, when it was
 * tested, and one "Test connection" (ERR-01), as the approved mockup's healthPopover(). The popover is a non-modal
 * Radix dialog drawn in a portal on the page's own surfaces (not the ink app bar's), fixed under its chip; it takes the
 * focus when it opens and closes on Esc (the focus goes back to the chip), on a click outside, or when the focus
 * leaves it. A test from inside it can make the store healthy while it is open: it then says so (a check, the latency,
 * "<Store> is connected."), and on close the read-out chip that replaces the button takes the focus (StoreChip).
 */
function StoreProblem({
  store,
  test,
  when,
  onTest,
  onOpenChange,
}: {
  store: Store;
  test: TestEntry;
  when: WhenFormat;
  onTest: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<{ left: number; top: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const kind = healthKind(store);
  const failed = kind === "failed";
  const connected = kind === "connected";
  const change = (next: boolean) => {
    setOpen(next);
    if (!next) setPlace(null);
    onOpenChange(next);
  };

  // The portal mounts the popover a moment after `open` turns true, so it is placed once its box exists.
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const contentRef = useCallback((element: HTMLDivElement | null) => {
    content.current = element;
    setBox(element);
  }, []);

  // Placed under the chip, kept inside the window (8 px from its edges). The app bar is sticky, so a scroll doesn't
  // move the chip; a resize places the popover again.
  useLayoutEffect(() => {
    if (!open || !box) return;
    const measure = () => {
      if (!trigger.current) return;
      const r = trigger.current.getBoundingClientRect();
      const w = box.offsetWidth;
      const h = box.offsetHeight;
      const m = 8;
      let top = r.bottom + m;
      if (top + h > window.innerHeight - m && r.top - h - m > m) top = r.top - h - m;
      setPlace({ left: Math.max(m, Math.min(r.left, window.innerWidth - w - m)), top });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [open, box]);

  const title = popoverTitle(kind, store.name);
  const tested = when(store.health.tested_at);
  // Off screen until it is placed (not visibility: hidden, which would refuse the focus it takes when it opens).
  const style: CSSProperties = place ? { left: place.left, top: place.top } : { left: -10000, top: 0 };
  let body: ReactNode;
  if (test.running || test.error || test.result) {
    const line = test.error
      ? { tone: test.error.tone === "info" ? ("neutral" as const) : ("danger" as const), text: test.error.text }
      : test.result
        ? outcomeLine(test.result)
        : healthLine(store.health);
    body = <TestResult line={line} at={test.result ? when(test.result.tested_at) : null} running={test.running} />;
  } else if (connected) {
    body = <TestResult line={healthLine(store.health)} at={tested} running={false} />;
  } else if (failed) {
    body = (
      <>
        <p>{`${healthLine(store.health).text} ${S.waiting}`}</p>
        {tested ? <p className="muted num">{S.testedAt(tested)}</p> : null}
      </>
    );
  } else body = <p>{S.neverTestedSub}</p>;

  return (
    <Dialog.Root open={open} onOpenChange={change} modal={false}>
      <Dialog.Trigger asChild>
        <button
          ref={trigger}
          type="button"
          className={`health-chip is-button${failed ? " is-down" : connected ? "" : " is-unknown"}`}
        >
          <StoreBadge store={identifierOf(store)} />
          {failed ? (
            <TriangleAlert className="icon" aria-hidden="true" />
          ) : connected ? (
            <CircleCheck className="icon" aria-hidden="true" />
          ) : (
            <CircleDashed className="icon" aria-hidden="true" />
          )}
          {connected ? (
            store.health.latency_ms !== null ? (
              <span className="health-chip__lat num">{`${store.health.latency_ms} ms`}</span>
            ) : null
          ) : (
            <span className="health-chip__state">
              {failed ? S.chip[store.health.state === "refused" ? "refused" : "unreachable"] : S.chip.unknown}
            </span>
          )}
          {failed ? <span className="sr-only">{`. ${S.showReason}`}</span> : null}
          {connected ? <span className="sr-only"> connected</span> : null}
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Content
          ref={contentRef}
          className="popover"
          style={style}
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            content.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            // the button is about to be replaced by a read-out chip: StoreChip moves the focus there
            if (!isProblem(kind)) event.preventDefault();
          }}
        >
          <Dialog.Title className="popover__title">{title}</Dialog.Title>
          <div className="popover__body">
            <div className="popover__text" role="status">
              {body}
            </div>
            <TestButton compact running={test.running} onTest={onTest} />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** One store's chip: paused wins (never shown as failed), then the saved health. A chip whose popover is open stays a
 *  button until it closes, even when a test from inside it turns the store healthy. */
function StoreChip({
  store,
  test,
  when,
  onTest,
}: {
  store: Store;
  test: TestEntry;
  when: WhenFormat;
  onTest: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const kind = healthKind(store);
  const readOut = useRef<HTMLSpanElement>(null);
  const wasOpen = useRef(false);

  // The popover closed and the button became a read-out (a test inside it fixed the store): the focus, left on the
  // page's body by the removed popover, goes to the chip that replaced the button. A click that put the focus
  // somewhere else keeps it there.
  useEffect(() => {
    const closed = wasOpen.current && !open;
    wasOpen.current = open;
    if (!closed) return;
    if (chipFocusAfterClose(isProblem(kind), document.activeElement, document.body) === "chip")
      readOut.current?.focus();
  }, [open, kind]);

  const badge = <StoreBadge store={identifierOf(store)} />;
  if (kind === "paused" && !open) {
    return (
      <ReadOut ref={readOut} tip={S.chipPaused(store.name)}>
        {badge}
        <Pause className="icon is-muted" aria-hidden="true" />
        <span className="health-chip__state">{S.chip.paused}</span>
      </ReadOut>
    );
  }
  if (kind === "connected" && !open) {
    const ms = store.health.latency_ms;
    const tested = when(store.health.tested_at);
    return (
      <ReadOut ref={readOut} tip={`${S.chipConnected(store.name, ms)}. ${tested ? S.testedAt(tested) : ""}`.trim()}>
        {badge}
        <CircleCheck className="icon" aria-hidden="true" />
        {ms !== null ? <span className="health-chip__lat num">{`${ms} ms`}</span> : null}
        <span className="sr-only"> connected</span>
      </ReadOut>
    );
  }
  return <StoreProblem store={store} test={test} when={when} onTest={() => onTest(store.id)} onOpenChange={setOpen} />;
}

const DOWN_TEXT: Record<Exclude<ConnectionState, "connected">, string> = {
  unreachable: "Can't reach",
  refused: "Refused",
};

/** The S3 chip: placeholder data until the storage test (m2.7) reports a health. */
function StorageChip({ storage }: { storage: StorageHealth }) {
  const down = storage.state !== "connected";
  const detail = down
    ? DOWN_TEXT[storage.state as Exclude<ConnectionState, "connected">]
    : storage.latencyMs === null
      ? ""
      : `${storage.latencyMs} ms`;
  return (
    <ReadOut tip={`S3 storage: ${down ? detail.toLowerCase() : "connected"}`}>
      <span className="store-badge">
        <HardDrive className="icon" aria-hidden="true" />
        S3
      </span>
      {down ? (
        <TriangleAlert className="icon" aria-hidden="true" />
      ) : (
        <CircleCheck className="icon" aria-hidden="true" />
      )}
      {detail ? <span className="health-chip__lat">{detail}</span> : null}
    </ReadOut>
  );
}

/**
 * The store and S3 health area in the app bar (UI-SHELL, ERR-01): one chip per store from GET /api/stores (removed
 * stores aren't listed; paused ones show as paused), and the S3 chip once storage reports a health. Before any store
 * or bucket it says so; while the list loads it shows nothing, and if it can't be read it says that, never "no stores".
 */
export function HealthArea({
  stores,
  failed = false,
  storage,
  tests = new Map(),
  when = localWhen,
  onTest,
}: {
  /** undefined while the first answer is awaited. */
  stores: Store[] | undefined;
  failed?: boolean;
  storage: StorageHealth | null;
  tests?: ReadonlyMap<number, TestEntry>;
  when?: WhenFormat;
  onTest: (id: number) => void;
}) {
  let content: ReactNode;
  if (stores === undefined) {
    content = failed ? (
      <span className="health-chip is-none">
        <Plug className="icon" aria-hidden="true" />
        {S.connectionsUnknown}
      </span>
    ) : null;
  } else if (stores.length === 0 && storage === null) {
    content = (
      <span className="health-chip is-none">
        <Plug className="icon" aria-hidden="true" />
        No stores or storage yet
      </span>
    );
  } else {
    content = (
      <>
        {stores.map((store) => (
          <StoreChip key={store.id} store={store} test={tests.get(store.id) ?? IDLE} when={when} onTest={onTest} />
        ))}
        {storage ? <StorageChip storage={storage} /> : null}
      </>
    );
  }
  return (
    <section className="app-bar__health" aria-label="Connections">
      {content}
    </section>
  );
}
