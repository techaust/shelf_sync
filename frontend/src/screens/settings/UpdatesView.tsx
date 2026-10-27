import { CircleCheck, CircleDot, Download, Info, LoaderCircle, RefreshCcw, RefreshCw, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { Alert } from "../../components/Alert";
import { SecretField } from "../../components/SecretField";
import { checkGithubToken, TOKEN_MAX_LENGTH } from "./forms";
import type { Phase, UpdatesModel } from "./updatesModel";
import { T, U } from "./wording";

export interface UpdatesActions {
  onCheck: () => void;
  onInstall: () => void;
  onRollBack: () => void;
  onSaveToken: (value: string) => Promise<void>;
  onRemoveToken: () => Promise<void>;
}

/** The loading state: the card's real layout in quiet blocks (05 section 6), no spinner. */
export function UpdatesLoading() {
  return (
    <section className="card" aria-busy="true">
      <div className="card__head">
        <span className="sk is-title" />
        <span className="sk is-line" />
      </div>
      <div className="card__body form-stack">
        <span className="sk is-block" />
        <span className="sk is-line" />
        <span className="sk is-field" />
      </div>
    </section>
  );
}

/** GET /api/updates failed: the reason and one action (05 section 6). */
export function UpdatesFailed({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="card">
      <div className="card-alert">
        <Alert
          tone="danger"
          title={text}
          action={
            <button type="button" className="btn is-compact" onClick={onRetry}>
              <RefreshCw className="icon" aria-hidden="true" />
              {U.tryAgain}
            </button>
          }
        />
      </div>
    </section>
  );
}

/** After an accepted Install or Roll back: ShelfSync closes and opens again; the page waits, then reloads. */
export function Restarting({ version, late }: { version: string; late: boolean }) {
  // The button that started it is gone: the focus moves to this panel's title, so it is read and not lost.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus(), []);
  return (
    <section className="card restart-panel" aria-labelledby="restart-title">
      <div className="restart-panel__body" role="status">
        <span className="restart-panel__icon">
          <RefreshCcw className="icon-lg" aria-hidden="true" />
        </span>
        <div className="restart-panel__text">
          <h3 className="restart-panel__title" id="restart-title" ref={title} tabIndex={-1}>
            {U.restartingTitle}
          </h3>
          <p className="muted">{U.restartingText(version)}</p>
          {late ? <p className="restart-panel__late">{U.restartingLate}</p> : null}
        </div>
      </div>
      <div className="progress is-indeterminate" aria-hidden="true">
        <span />
      </div>
    </section>
  );
}

function StatusLine({ model }: { model: UpdatesModel }) {
  const { status } = model;
  if (status.kind === "none" || status.kind === "ready" || !status.text) return null;
  const Icon = status.kind === "up_to_date" ? CircleCheck : status.kind === "downloading" ? CircleDot : Info;
  return (
    <p className={`status-line is-${status.kind}`}>
      <Icon className="icon" aria-hidden="true" />
      <span className="num">{status.text}</span>
    </p>
  );
}

/** Settings › Updates for one GET /api/updates answer (described by updatesModel.ts) and the page's phase. */
export function UpdatesView({
  model,
  phase,
  actionError,
  actions,
}: {
  model: UpdatesModel;
  phase: Phase;
  actionError: string | null;
  actions: UpdatesActions;
}) {
  const preparing = phase.kind === "preparing";
  const busy = phase.kind !== "idle";
  const ready = model.install.shown && model.install.version;
  return (
    <section className="card" aria-labelledby="up-title" aria-busy={busy || undefined}>
      <div className="card__head">
        <h3 className="card__title is-sm num" id="up-title">
          {model.heading}
        </h3>
        {model.checked ? <span className="muted num card__meta">{model.checked}</span> : null}
      </div>
      {actionError || model.notices.length ? (
        <div className="card-alert stack-alert">
          {actionError ? <Alert tone="danger" title={actionError} /> : null}
          {model.notices.map((notice) => (
            <Alert key={notice.key} tone={notice.tone} title={notice.title}>
              {notice.body}
            </Alert>
          ))}
        </div>
      ) : null}
      <div className="card__body form-stack">
        {ready ? (
          <div className="update-card">
            <div className="update-card__text" role="status">
              <p className="update-card__title num">{U.ready(ready)}</p>
              {preparing ? <p className="muted num">{U.preparing(ready)}</p> : null}
            </div>
            <button
              type="button"
              className="btn is-primary"
              aria-disabled={!model.install.enabled || undefined}
              aria-busy={preparing || undefined}
              onClick={() => {
                if (model.install.enabled) actions.onInstall();
              }}
            >
              {preparing ? (
                <LoaderCircle className="icon is-spinning" aria-hidden="true" />
              ) : (
                <Download className="icon" aria-hidden="true" />
              )}
              {U.install(ready)}
            </button>
          </div>
        ) : null}
        <StatusLine model={model} />
        {model.lastChange ? (
          <p className="status-line is-done">
            <CircleCheck className="icon" aria-hidden="true" />
            <span className="num">{model.lastChange}</span>
          </p>
        ) : null}
        <div className="action-row">
          <button
            type="button"
            className="btn"
            aria-disabled={!model.check.enabled || undefined}
            aria-busy={model.check.running || undefined}
            onClick={() => {
              if (model.check.enabled) actions.onCheck();
            }}
          >
            {model.check.running ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : (
              <RefreshCw className="icon" aria-hidden="true" />
            )}
            {U.checkNow}
          </button>
          {model.rollBack.shown ? (
            <button
              type="button"
              className="btn"
              aria-disabled={!model.rollBack.enabled || undefined}
              aria-describedby={model.rollBack.reason ? "up-rollback-why" : undefined}
              aria-busy={phase.kind === "rolling_back" || undefined}
              onClick={() => {
                if (model.rollBack.enabled) actions.onRollBack();
              }}
            >
              {phase.kind === "rolling_back" ? (
                <LoaderCircle className="icon is-spinning" aria-hidden="true" />
              ) : (
                <RotateCcw className="icon" aria-hidden="true" />
              )}
              {U.rollBack}
            </button>
          ) : null}
          {model.rollBack.reason ? (
            <p className="field__hint action-row__why" id="up-rollback-why">
              {model.rollBack.reason}
            </p>
          ) : null}
        </div>
        <div className="card__section">
          {model.token.set ? null : <p className="token-empty">{U.empty}</p>}
          <SecretField
            id="up-token"
            text={T}
            set={model.token.set}
            expires={model.token.expires ? T.expiresOn(model.token.expires) : null}
            maxLength={TOKEN_MAX_LENGTH}
            check={checkGithubToken}
            locked={busy}
            onSave={actions.onSaveToken}
            onRemove={actions.onRemoveToken}
          />
        </div>
      </div>
    </section>
  );
}
