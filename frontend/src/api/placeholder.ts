// PLACEHOLDER (M1a.3). The one module that stands in for data the backend doesn't serve yet: the nav counts, the
// store and S3 health, and the status strip. Nothing here is invented: every value is either the state of a fresh
// install with nothing connected, or a default written in docs/03-prd.md (named next to it). M1b to M5 replace
// `fetchShellStatus` with real endpoints (live counts and health come over SSE in M5); the types stay.

/** Store identifier (05 section 2.3): shape + dot colour + two-letter code. Dot colours are store data, not app styling. */
export interface StoreIdentifier {
  code: string;
  name: string;
  shape: "circle" | "square" | "triangle" | "diamond";
  dot: { light: string; dark: string };
}

export type ConnectionState = "connected" | "unreachable" | "refused";

export interface StoreHealth extends StoreIdentifier {
  state: ConnectionState;
  latencyMs: number | null;
}

export interface StorageHealth {
  state: ConnectionState;
  latencyMs: number | null;
}

export type AutoApply =
  | { kind: "off_trust_ramp" } // before the trust ramp reaches its target (D-6, APL-13)
  | { kind: "on" }
  | { kind: "paused_brake"; reason: string }; // the brake tripped; the reason is its tooltip (13 section 6)

export interface ShellStatus {
  /** Review and Cleanup nav badges; 0 shows no badge (as in the approved mockup). Live in M5. */
  counts: { review: number; cleanup: number };
  /** Connected stores and the S3 storage; empty and null until M2 adds them. */
  stores: StoreHealth[];
  storage: StorageHealth | null;
  autoApply: AutoApply;
  trustRamp: { count: number; target: number };
  /** UTC ISO 8601, or null before the first sync. */
  lastSyncAt: string | null;
  /** Minutes between incremental syncs (Cleanup's empty state names it). */
  syncIntervalMinutes: number;
  /** Local time of day "HH:MM" of the nightly snapshot. */
  nextSnapshot: string | null;
}

export const SHELL_STATUS_PLACEHOLDER: ShellStatus = {
  counts: { review: 0, cleanup: 0 }, // nothing has been uploaded or synced
  stores: [], // no store is added until M2's setup
  storage: null, // no bucket is added until M2's setup
  autoApply: { kind: "off_trust_ramp" }, // off until the trust ramp is done (03 D-6)
  trustRamp: { count: 0, target: 50 }, // a fresh install starts at 0; 50 is the ramp in 03 D-6
  lastSyncAt: null, // no store, so no sync yet
  syncIntervalMinutes: 15, // the default interval, 03 SYNC-01 (a setting from M1b)
  nextSnapshot: "02:00", // the default snapshot time, 03 SYNC-03 (a setting from M1b)
};

export const SHELL_STATUS_QUERY_KEY = ["shell-status", "placeholder"] as const;

/** Stand-in for the M5 status endpoint. Same shape, so the screens don't change when it's replaced. */
export async function fetchShellStatus(): Promise<ShellStatus> {
  return SHELL_STATUS_PLACEHOLDER;
}
