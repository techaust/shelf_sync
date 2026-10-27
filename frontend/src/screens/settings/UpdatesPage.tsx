import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, ApiUnreachableError } from "../../api/client";
import {
  checkForUpdates,
  getHealth,
  getUpdates,
  installUpdate,
  removeGithubToken,
  rollBack,
  saveGithubToken,
  UPDATES_QUERY_KEY,
} from "../../api/settings";
import { useServices } from "../../app/services";
import { Alert } from "../../components/Alert";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { pollForRestart } from "../../lib/restartPoll";
import { Restarting, UpdatesFailed, UpdatesLoading, UpdatesView } from "./UpdatesView";
import { describeUpdates, type Phase } from "./updatesModel";
import { T, U, updatesActionError } from "./wording";

/** While a check or a switch runs, the status is asked for again every two seconds. */
const BUSY_REFRESH_MS = 2000;

function actionError(error: unknown): string {
  if (error instanceof ApiError) return updatesActionError(error.code, error.status);
  return updatesActionError(null, null);
}

/**
 * Settings › Updates (UI-SET; SYS-06, SYS-07, SET-04): the state of updates from GET /api/updates, Check now,
 * Install (a ConfirmDialog, a "preparing" state while the server checks the files, then the restart panel, which
 * waits for the new version to answer and reloads), Roll back (a ConfirmDialog with the files-only or the database
 * wording), and the optional GitHub token.
 */
export function UpdatesPage() {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [installOpen, setInstallOpen] = useState(false);
  const [rollBackOpen, setRollBackOpen] = useState(false);
  const restarting = phase.kind === "restarting";

  const query = useQuery({
    queryKey: UPDATES_QUERY_KEY,
    queryFn: () => getUpdates(api),
    enabled: !restarting,
    refetchInterval: (current) => (current.state.data?.checking || current.state.data?.busy ? BUSY_REFRESH_MS : false),
  });
  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: UPDATES_QUERY_KEY }), [queryClient]);

  // The restart: ask /api/health until the new version (or, after a refused switch, ShelfSync again) answers.
  const target = restarting ? phase.version : null;
  useEffect(() => {
    if (target === null) return;
    return pollForRestart({
      target,
      health: () => getHealth(api),
      onBack: () => window.location.reload(),
      onLate: () => setPhase({ kind: "restarting", version: target, late: true }),
    });
  }, [api, target]);

  if (phase.kind === "restarting") return <Restarting version={phase.version} late={phase.late} />;
  if (query.isPending) return <UpdatesLoading />;
  if (query.isError) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? U.loadRefused(failure.status) : U.loadFailed;
    return <UpdatesFailed text={text} onRetry={() => void query.refetch()} />;
  }

  const updates = query.data;
  const model = describeUpdates(updates, phase);
  const version = model.install.version;
  const previous = model.rollBack.previous;

  async function check() {
    setError(null);
    try {
      await checkForUpdates(api);
    } catch (failure) {
      setError(actionError(failure));
    }
    await refresh();
  }

  /** Install or Roll back after the dialog: 202 means ShelfSync is closing; no answer at all is taken the same way
   *  (it may have closed before the answer arrived), and the health poll finds out which version comes back. */
  async function switchTo(kind: "preparing" | "rolling_back", to: string, send: () => Promise<unknown>) {
    setError(null);
    setPhase({ kind, version: to });
    try {
      await send();
      setPhase({ kind: "restarting", version: to, late: false });
    } catch (failure) {
      if (failure instanceof ApiUnreachableError) {
        setPhase({ kind: "restarting", version: to, late: false });
        return;
      }
      setPhase({ kind: "idle" });
      await refresh();
      if (failure instanceof ApiError && failure.code === "confirm_required") {
        setRollBackOpen(true); // the database changed since this page was loaded: ask again, with the database wording
        return;
      }
      setError(actionError(failure));
    }
  }

  async function saveToken(value: string) {
    try {
      await saveGithubToken(api, value);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "invalid_request") throw new Error(T.refused);
      if (failure instanceof ApiError) throw new Error(actionError(failure));
      throw new Error(T.saveFailed);
    }
    await refresh();
  }

  async function removeToken() {
    try {
      await removeGithubToken(api);
    } catch (failure) {
      throw new Error(failure instanceof ApiError ? actionError(failure) : T.removeFailed);
    }
    await refresh();
  }

  return (
    <>
      <UpdatesView
        model={model}
        phase={phase}
        actionError={error}
        actions={{
          onCheck: () => void check(),
          onInstall: () => setInstallOpen(true),
          onRollBack: () => setRollBackOpen(true),
          onSaveToken: saveToken,
          onRemoveToken: removeToken,
        }}
      />
      {version ? (
        <ConfirmDialog
          open={installOpen}
          title={U.installTitle(version)}
          confirmLabel={U.install(version)}
          ConfirmIcon={Download}
          cancelLabel={U.cancel}
          onCancel={() => setInstallOpen(false)}
          onConfirm={() => {
            setInstallOpen(false);
            void switchTo("preparing", version, () => installUpdate(api));
          }}
        >
          <p>{U.installText}</p>
        </ConfirmDialog>
      ) : null}
      {previous ? (
        <ConfirmDialog
          open={rollBackOpen}
          title={U.rollBackTitle(previous)}
          confirmLabel={U.rollBackConfirm}
          ConfirmIcon={RotateCcw}
          cancelLabel={U.cancel}
          danger={model.rollBack.databaseChanged}
          onCancel={() => setRollBackOpen(false)}
          onConfirm={() => {
            setRollBackOpen(false);
            const confirm = model.rollBack.databaseChanged;
            void switchTo("rolling_back", previous, () => rollBack(api, confirm));
          }}
        >
          {model.rollBack.databaseChanged && model.rollBack.backupDate ? (
            <Alert tone="warning" title={U.rollBackDatabase(model.rollBack.backupDate)} />
          ) : (
            <p>{U.rollBackFiles}</p>
          )}
        </ConfirmDialog>
      ) : null}
    </>
  );
}
