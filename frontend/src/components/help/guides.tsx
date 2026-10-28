// The Help panel's three guides (UI-HELP), in 13's plain style, from docs/runbooks/keys-and-policies.md sections A and
// B, docs/runbooks/key-rotation.md (the GitHub token) and docs/runs/m2.0-plan.md section 2 (the two policies). All of it
// is proposed (m2.5a) for 13; the screen labels are the app's own (Settings › Stores, Settings › Storage, Settings ›
// Updates). Steps are numbered because they are a sequence.

import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { type ReactNode, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { getStorage, STORAGE_QUERY_KEY } from "../../api/storage";
import { useServices } from "../../app/services";
import { BUCKET_PLACEHOLDER, bucketFor, copyText, type GuideId, policies } from "./helpModel";

export const H = {
  title: "Help",
  close: "Close help",
  guides: "Guides",
  allGuides: "All guides",
  open: "Help",
  copy: "Copy",
  copied: "Copied.",
  pressCtrlC: "Press Ctrl+C to copy.",
  guideTitles: {
    "shop-manager-key": "Make a Shop Manager key", // mockup
    "s3-policy": "Set up the S3 access policy (IAM)", // mockup
    "github-token": "Make a GitHub token for updates", // mockup
  } satisfies Record<GuideId, string>,
  never: "Never paste a key into chat, a document or a screenshot. A key shown anywhere else has to be replaced.",
  // the S3 guide
  noBucket: "Fill in the bucket under Settings › Storage first. Until then the policies say BUCKET.",
  noBucketLink: "Open Storage settings",
  bucketUnknown: "ShelfSync didn't answer, so the bucket's name couldn't be filled in. Replace BUCKET with it.",
  bucketLead: "The policies below are for the bucket",
  readWriteTitle: "Read and write policy (ShelfSyncReadWrite)",
  readOnlyTitle: "Read-only policy (ShelfSyncReadOnly)",
  policyLabel: (title: string) => `${title}, JSON`,
};

/** A small mono name inside a sentence: a user name, a policy name, a key prefix. */
const M = ({ children }: { children: ReactNode }) => <code className="mono">{children}</code>;

function ShopManagerGuide() {
  return (
    <>
      <p>One key for each store. Do this signed in to that store's WordPress admin.</p>
      <ol className="guide-steps">
        <li>
          Go to <strong>Users › Add New User</strong>. Username <M>shelfsync</M>, an email address you control, role{" "}
          <strong>Shop manager</strong>. Click <strong>Add New User</strong>.
        </li>
        <li>
          Go to <strong>WooCommerce › Settings › Advanced › REST API › Add key</strong>. Description <M>ShelfSync</M>,
          user <M>shelfsync</M>, permissions <strong>Read/Write</strong>. Click <strong>Generate API key</strong>.
        </li>
        <li>
          WooCommerce shows the consumer key (<M>ck_…</M>) and the consumer secret (<M>cs_…</M>) once. Leave that page
          open.
        </li>
        <li>
          In ShelfSync, go to <strong>Settings › Stores</strong>. Open the store, or <strong>Add a store</strong>, and
          paste both. Save, then click <strong>Test connection</strong>. It says "Connected in … ms" when the key works.
        </li>
        <li>Close the WooCommerce page. You don't need to keep the key anywhere else: if it's lost, make a new one.</li>
      </ol>
      <p className="muted">
        A Read/Write key can also change orders, coupons and customers (WooCommerce can't limit it to products), so
        guard it like a password.
      </p>
      <p className="muted">{H.never}</p>
    </>
  );
}

function PolicyBlock({ title, text }: { title: string; text: string }) {
  const id = useId();
  const pre = useRef<HTMLPreElement>(null);
  const region = useRef<HTMLElement>(null);
  const [said, setSaid] = useState<"" | "copied" | "select">("");
  async function copy() {
    const result = await copyText(text, typeof navigator === "undefined" ? null : navigator.clipboard);
    // No clipboard here (or it refused): the policy is selected, ready for Ctrl+C, and the focus is on it.
    if (result === "select" && pre.current) {
      region.current?.focus();
      window.getSelection()?.selectAllChildren(pre.current);
    }
    setSaid(result);
  }
  return (
    <div className="policy">
      <div className="policy__head">
        <h4 className="policy__title" id={`${id}-title`}>
          {title}
        </h4>
        <button type="button" className="btn is-compact" onClick={() => void copy()} aria-describedby={`${id}-said`}>
          {said === "copied" ? (
            <Check className="icon" aria-hidden="true" />
          ) : (
            <Copy className="icon" aria-hidden="true" />
          )}
          {H.copy}
        </button>
      </div>
      {/* Right under Copy, so the answer is seen whatever the policy's length. */}
      <p className={`policy__said${said ? " is-said" : ""}`} id={`${id}-said`} role="status">
        {said === "copied" ? H.copied : said === "select" ? H.pressCtrlC : ""}
      </p>
      {/* Shown whole (it wraps; nothing to scroll), so no tab stop; Copy's fallback focuses and selects it. */}
      <section className="policy__code" tabIndex={-1} aria-label={H.policyLabel(title)} ref={region}>
        <pre ref={pre}>{text}</pre>
      </section>
    </div>
  );
}

export function S3PolicyGuideBody({
  bucket,
  state,
  onStorage,
}: {
  /** The saved bucket's name, or "" when none is saved yet. */
  bucket: string;
  state: "loading" | "ready" | "failed";
  onStorage: () => void;
}) {
  const name = bucketFor(bucket);
  const filled = name !== BUCKET_PLACEHOLDER;
  const { readWrite, readOnly } = policies(name);
  return (
    <>
      <p>
        ShelfSync uses two AWS keys, each from its own IAM user, so each key has only its own policy. Do this in the AWS
        console, signed in as your admin user.
      </p>
      {state === "ready" && !filled ? (
        <p className="guide-note">
          {H.noBucket}{" "}
          <Link to="/settings/storage" onClick={onStorage}>
            {H.noBucketLink}
          </Link>
        </p>
      ) : null}
      {state === "failed" ? <p className="guide-note">{H.bucketUnknown}</p> : null}
      {filled ? (
        <p>
          {H.bucketLead} <code className="mono is-long">{name}</code>.
        </p>
      ) : null}
      <ol className="guide-steps">
        <li>
          Go to <strong>IAM › Users › Create user</strong>. Name <M>shelfsync-rw</M>, no console access. Click{" "}
          <strong>Next</strong>.
        </li>
        <li>
          Choose <strong>Attach policies directly › Create policy › JSON</strong> and paste the read and write policy
          below. Click <strong>Next</strong>, name it <M>ShelfSyncReadWrite</M>, then <strong>Create policy</strong>.
        </li>
        <li>
          Back on the user, refresh the list, tick <M>ShelfSyncReadWrite</M>, then click <strong>Next</strong> and{" "}
          <strong>Create user</strong>.
        </li>
        <li>
          Open the user, then{" "}
          <strong>Security credentials › Create access key › Application running outside AWS</strong>. AWS shows the
          access key and the secret access key once.
        </li>
        <li>
          In ShelfSync, go to <strong>Settings › Storage</strong>, paste both into the read and write key, and save.
        </li>
        <li>
          Do steps 1 to 5 again with the name <M>shelfsync-ro</M>, the read-only policy named <M>ShelfSyncReadOnly</M>,
          and the read-only key.
        </li>
      </ol>
      <PolicyBlock title={H.readWriteTitle} text={readWrite} />
      <PolicyBlock title={H.readOnlyTitle} text={readOnly} />
      <p className="muted">{H.never}</p>
    </>
  );
}

function S3PolicyGuide({ onLeave }: { onLeave: () => void }) {
  const { api } = useServices();
  const query = useQuery({ queryKey: STORAGE_QUERY_KEY, queryFn: () => getStorage(api) });
  const state = query.data ? "ready" : query.isError ? "failed" : "loading";
  return <S3PolicyGuideBody bucket={query.data?.s3_bucket ?? ""} state={state} onStorage={onLeave} />;
}

function GithubTokenGuide() {
  return (
    <>
      <p>
        A token is optional. ShelfSync checks for updates by itself; add one only if GitHub refuses the check or the
        project is private.
      </p>
      <ol className="guide-steps">
        <li>
          On GitHub, go to <strong>Settings › Developer settings › Fine-grained tokens › Generate new token</strong>.
        </li>
        <li>
          Give it the name <M>ShelfSync</M> and an expiry date.
        </li>
        <li>
          Give it access to only the <M>techaust/shelf_sync</M> repository, with <strong>Contents: Read-only</strong>.
          It needs nothing else.
        </li>
        <li>
          Click <strong>Generate token</strong>. GitHub shows the token (it starts with <M>github_pat_</M>) once.
        </li>
        <li>
          In ShelfSync, go to <strong>Settings › Updates</strong>, paste the token, save, then click{" "}
          <strong>Check now</strong>.
        </li>
      </ol>
      <p className="muted">
        ShelfSync warns you 14 days before the token expires. Make a new one then, or remove it to check without one.
      </p>
    </>
  );
}

/** The body of one guide. `onLeave`: a link inside it moves to another screen, so the panel closes. */
export function GuideBody({ guide, onLeave }: { guide: GuideId; onLeave: () => void }) {
  switch (guide) {
    case "shop-manager-key":
      return <ShopManagerGuide />;
    case "s3-policy":
      return <S3PolicyGuide onLeave={onLeave} />;
    case "github-token":
      return <GithubTokenGuide />;
  }
}
