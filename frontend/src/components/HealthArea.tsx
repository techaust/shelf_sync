import { CircleCheck, HardDrive, Plug, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { ConnectionState, StorageHealth, StoreHealth } from "../api/placeholder";
import { StoreBadge } from "./StoreBadge";
import { Tip } from "./Tip";

const DOWN_TEXT: Record<Exclude<ConnectionState, "connected">, string> = {
  unreachable: "Can't reach",
  refused: "Refused",
};

function Chip({
  badge,
  name,
  state,
  latencyMs,
}: {
  badge: ReactNode;
  name: string;
  state: ConnectionState;
  latencyMs: number | null;
}) {
  const down = state !== "connected";
  const detail = down ? DOWN_TEXT[state] : latencyMs === null ? "" : `${latencyMs} ms`;
  return (
    <Tip
      content={`${name}: ${down ? DOWN_TEXT[state].toLowerCase() : "connected"}${detail && !down ? `, ${detail}` : ""}`}
    >
      {/* biome-ignore lint/a11y/noNoninteractiveTabindex: a read-out that has to take focus to show its tooltip */}
      <span className={`health-chip${down ? " is-down" : ""}`} tabIndex={0}>
        {badge}
        {down ? <TriangleAlert className="icon" /> : <CircleCheck className="icon" />}
        {detail && <span className="health-chip__lat">{detail}</span>}
        <span className="sr-only">{down ? "" : " connected"}</span>
      </span>
    </Tip>
  );
}

/**
 * The store and S3 health area in the app bar (UI-SHELL). One chip per store (identifier + state + latency) and
 * one for S3. Until M2 adds a store or a bucket there is nothing to report, and it says so.
 */
export function HealthArea({ stores, storage }: { stores: StoreHealth[]; storage: StorageHealth | null }) {
  const nothing = stores.length === 0 && storage === null;
  return (
    <section className="app-bar__health" aria-label="Connections">
      {nothing ? (
        <span className="health-chip is-none">
          <Plug className="icon" />
          No stores or storage yet
        </span>
      ) : (
        <>
          {stores.map((store) => (
            <Chip
              key={store.code}
              badge={<StoreBadge store={store} />}
              name={store.name}
              state={store.state}
              latencyMs={store.latencyMs}
            />
          ))}
          {storage && (
            <Chip
              badge={
                <span className="store-badge">
                  <HardDrive className="icon" />
                  S3
                </span>
              }
              name="S3 storage"
              state={storage.state}
              latencyMs={storage.latencyMs}
            />
          )}
        </>
      )}
    </section>
  );
}
