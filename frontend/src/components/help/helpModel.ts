// The Help panel without React (UI-HELP): which guide is shown, the two IAM policies with the bucket filled in
// (docs/runs/m2.0-plan.md section 2), and Copy with its fallback. Pure, so each rule is tested in Node
// (help.test.ts). The guides' words are in guides.tsx; they are proposed in docs/runs/m2.5a-stores-screens.md
// section 3 for 13.

export type GuideId = "shop-manager-key" | "s3-policy" | "github-token";

export const GUIDE_IDS: readonly GuideId[] = ["shop-manager-key", "s3-policy", "github-token"];

export interface HelpState {
  open: boolean;
  /** The guide shown, or null for the panel's start (the list of guides). */
  guide: GuideId | null;
}

export interface HelpStore {
  subscribe(listener: () => void): () => void;
  get(): HelpState;
  /** Opens the panel, at a guide or at its start. Called from a click, so the focused element is the opener. */
  open(guide?: GuideId | null): void;
  /** Moves inside the open panel. */
  show(guide: GuideId | null): void;
  close(): void;
}

export function createHelpStore(): HelpStore {
  let state: HelpState = { open: false, guide: null };
  const listeners = new Set<() => void>();
  const set = (next: HelpState) => {
    if (next.open === state.open && next.guide === state.guide) return;
    state = next;
    for (const listener of [...listeners]) listener();
  };
  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    get: () => state,
    open: (guide = null) => set({ open: true, guide }),
    show: (guide) => set({ open: state.open, guide }),
    close: () => set({ open: false, guide: state.guide }),
  };
}

/** The tab's one Help panel. */
export const helpStore = createHelpStore();

/** Where the focus goes when the panel opens: the guide's title when it opens at a guide, otherwise Close (as the
 *  approved mockup does). */
export function firstFocus(guide: GuideId | null): "guide-title" | "close" {
  return guide ? "guide-title" : "close";
}

// ---------- the two IAM policies (m2.0 section 2; 06 section 5) ----------

/** The placeholder shown, and copied, until Settings › Storage has a bucket. */
export const BUCKET_PLACEHOLDER = "BUCKET";

/** The bucket name to write into the policies: the saved one (the API has already checked its shape), or BUCKET. */
export function bucketFor(saved: string | null | undefined): string {
  const name = (saved ?? "").trim();
  return /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(name) ? name : BUCKET_PLACEHOLDER;
}

export function policies(bucket: string): { readWrite: string; readOnly: string } {
  const objects = `arn:aws:s3:::${bucket}/*`;
  const list = { Sid: "ShelfSyncList", Effect: "Allow", Action: "s3:ListBucket", Resource: `arn:aws:s3:::${bucket}` };
  const readWrite = {
    Version: "2012-10-17",
    Statement: [
      {
        Sid: "ShelfSyncObjects",
        Effect: "Allow",
        Action: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        Resource: objects,
      },
      list,
    ],
  };
  const readOnly = {
    Version: "2012-10-17",
    Statement: [{ Sid: "ShelfSyncRead", Effect: "Allow", Action: "s3:GetObject", Resource: objects }, list],
  };
  return { readWrite: JSON.stringify(readWrite, null, 2), readOnly: JSON.stringify(readOnly, null, 2) };
}

// ---------- Copy ----------

export interface ClipboardLike {
  writeText(text: string): Promise<void>;
}

/** "copied" when the clipboard took it; "select" when there is no clipboard here or it refused, so the page selects
 *  the text and says "Press Ctrl+C to copy." instead. */
export async function copyText(
  text: string,
  clipboard: ClipboardLike | undefined | null,
): Promise<"copied" | "select"> {
  if (!clipboard || typeof clipboard.writeText !== "function") return "select";
  try {
    await clipboard.writeText(text);
    return "copied";
  } catch {
    return "select";
  }
}
