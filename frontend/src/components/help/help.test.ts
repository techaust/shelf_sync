// UI-HELP: the Help panel's focus handling (opened like ConfirmDialog on the native <dialog>: Esc closes it and the
// focus goes back to the opener; the first focus is Close, or the guide's title when it opens at a guide), the two IAM
// policies with the bucket filled in, and Copy with its "Press Ctrl+C to copy." fallback. The unit tests run in Node,
// so the dialog is a fake (as in dialog.test.ts) and the panel's markup is rendered to static HTML.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { type DialogElement, dialogBehaviour, type Focusable } from "../dialog";
import { S3PolicyGuideBody } from "./guides";
import { BUCKET_PLACEHOLDER, bucketFor, copyText, createHelpStore, firstFocus, GUIDE_IDS, policies } from "./helpModel";
import { H } from "./helpWording";

type Listener = (event: { preventDefault(): void }) => void;
function fakeDialog() {
  const listeners: Record<"cancel" | "close", Set<Listener>> = { cancel: new Set(), close: new Set() };
  const fire = (type: "cancel" | "close") => {
    const event = { defaultPrevented: false, preventDefault: () => (event.defaultPrevented = true) };
    for (const listener of [...listeners[type]]) listener(event);
    return event;
  };
  const dialog = {
    open: false,
    showModal: vi.fn(() => {
      dialog.open = true;
    }),
    close: vi.fn(() => {
      if (!dialog.open) return;
      dialog.open = false;
      fire("close");
    }),
    addEventListener: (type: "cancel" | "close", listener: Listener) => listeners[type].add(listener),
    removeEventListener: (type: "cancel" | "close", listener: Listener) => listeners[type].delete(listener),
    pressEscape() {
      const event = fire("cancel");
      if (!event.defaultPrevented) dialog.close();
    },
  };
  return dialog satisfies DialogElement;
}
const focusable = (name: string, log: string[]): Focusable => ({ focus: () => log.push(name), isConnected: true });

describe("the Help panel's state", () => {
  it("opens at its start or at a guide, moves between guides, and closes", () => {
    const help = createHelpStore();
    const heard = vi.fn();
    help.subscribe(heard);
    help.open();
    expect(help.get()).toEqual({ open: true, guide: null });
    help.show("s3-policy");
    expect(help.get()).toEqual({ open: true, guide: "s3-policy" });
    help.close();
    expect(help.get().open).toBe(false);
    help.open("github-token");
    expect(help.get()).toEqual({ open: true, guide: "github-token" });
    expect(heard).toHaveBeenCalledTimes(4);
  });

  it("the mockup's three guides in its order and words, then the restore guide (m2.5b)", () => {
    expect(GUIDE_IDS.map((id) => H.guideTitles[id])).toEqual([
      "Make a Shop Manager key",
      "Set up the S3 access policy (IAM)",
      "Make a GitHub token for updates",
      "Restore the database from a backup",
    ]);
  });
});

describe("the Help panel's focus handling", () => {
  it("the first focus: Close at the start, the guide's title when it opens at a guide", () => {
    expect(firstFocus(null)).toBe("close");
    expect(firstFocus("shop-manager-key")).toBe("guide-title");
  });

  it("Esc closes it (the store is told) and the focus goes back to the button that opened it", () => {
    const dialog = fakeDialog();
    const help = createHelpStore();
    const log: string[] = [];
    const panel = dialogBehaviour(dialog, { onCancel: () => help.close(), isBusy: () => false });
    help.open("shop-manager-key");
    panel.open(focusable(firstFocus(help.get().guide), log), focusable("Shop Manager key guide button", log));
    expect(dialog.showModal).toHaveBeenCalled();
    expect(log).toEqual(["guide-title"]);
    dialog.pressEscape();
    expect(help.get().open).toBe(false);
    panel.close(); // what HelpPanel does when the store says closed
    expect(dialog.open).toBe(false);
    expect(log).toEqual(["guide-title", "Shop Manager key guide button"]);
  });

  it("the app bar's Help button gets the focus back the same way", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const panel = dialogBehaviour(dialog, { onCancel: vi.fn(), isBusy: () => false });
    panel.open(focusable("close", log), focusable("Help", log));
    panel.close();
    expect(log).toEqual(["close", "Help"]);
  });
});

describe("the two IAM policies (m2.0 section 2)", () => {
  it("the bucket's name is written in, or BUCKET until Settings › Storage has one", () => {
    expect(bucketFor("sample-downloads")).toBe("sample-downloads");
    expect(bucketFor("")).toBe(BUCKET_PLACEHOLDER);
    expect(bucketFor(null)).toBe(BUCKET_PLACEHOLDER);
    expect(bucketFor("Not A Bucket")).toBe(BUCKET_PLACEHOLDER);
  });

  it("read and write: Get, Put and Delete on the objects, List on the bucket", () => {
    const { readWrite } = policies("sample-downloads");
    expect(JSON.parse(readWrite)).toEqual({
      Version: "2012-10-17",
      Statement: [
        {
          Sid: "ShelfSyncObjects",
          Effect: "Allow",
          Action: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
          Resource: "arn:aws:s3:::sample-downloads/*",
        },
        { Sid: "ShelfSyncList", Effect: "Allow", Action: "s3:ListBucket", Resource: "arn:aws:s3:::sample-downloads" },
      ],
    });
  });

  it("read-only: Get on the objects, List on the bucket, nothing that writes", () => {
    const { readOnly } = policies("BUCKET");
    expect(JSON.parse(readOnly)).toEqual({
      Version: "2012-10-17",
      Statement: [
        { Sid: "ShelfSyncRead", Effect: "Allow", Action: "s3:GetObject", Resource: "arn:aws:s3:::BUCKET/*" },
        { Sid: "ShelfSyncList", Effect: "Allow", Action: "s3:ListBucket", Resource: "arn:aws:s3:::BUCKET" },
      ],
    });
    expect(readOnly).not.toMatch(/Put|Delete/);
  });
});

describe("Copy and its fallback", () => {
  it("copied when the clipboard takes it", async () => {
    const writeText = vi.fn(async () => undefined);
    expect(await copyText("policy", { writeText })).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("policy");
  });

  it("select (then 'Press Ctrl+C to copy.') with no clipboard on this page", async () => {
    expect(await copyText("policy", undefined)).toBe("select");
    expect(await copyText("policy", null)).toBe("select");
  });

  it("select when the clipboard refuses (the built-in pane denies clipboard-write)", async () => {
    const writeText = vi.fn(async () => {
      throw new DOMException("Write permission denied.", "NotAllowedError");
    });
    expect(await copyText("policy", { writeText })).toBe("select");
  });

  it("the two lines", () => {
    expect(H.copied).toBe("Copied.");
    expect(H.pressCtrlC).toBe("Press Ctrl+C to copy.");
  });
});

describe("the S3 guide", () => {
  const render = (bucket: string, state: "loading" | "ready" | "failed") =>
    renderToStaticMarkup(h(MemoryRouter, null, h(S3PolicyGuideBody, { bucket, state, onStorage: vi.fn() })));

  it("without a bucket: BUCKET in both policies, and the line pointing at Settings › Storage", () => {
    const html = render("", "ready");
    expect(html).toContain("Fill in the bucket under Settings › Storage first. Until then the policies say BUCKET.");
    expect(html).toContain('href="/settings/storage"');
    expect(html).toContain("arn:aws:s3:::BUCKET/*");
    expect(html.match(/>Copy</g)?.length).toBe(2);
  });

  it("with a bucket: its name in both policies, and no BUCKET line", () => {
    const html = render("sample-downloads", "ready");
    expect(html).toContain("The policies below are for the bucket");
    expect(html).toContain("arn:aws:s3:::sample-downloads/*");
    expect(html).not.toContain("BUCKET");
  });

  it("if the bucket can't be read, it says so and keeps BUCKET", () => {
    const html = render("", "failed").replaceAll("&#x27;", "'");
    expect(html).toContain(H.bucketUnknown);
    expect(html).toContain("arn:aws:s3:::BUCKET");
  });

  it("the steps are numbered (a sequence), and the policies are named regions with a status line", () => {
    const html = render("", "ready");
    expect(html).toContain('<ol class="guide-steps">');
    expect(html).toContain('aria-label="Read and write policy (ShelfSyncReadWrite), JSON"');
    expect(html).toContain('role="status"');
  });
});
