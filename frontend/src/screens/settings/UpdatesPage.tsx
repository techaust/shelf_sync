import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RotateCcw } from "lucide-react";
import { useCallback, useState, useSyncExternalStore } from "react";
import { ApiError } from "../../api/client";
import { getUpdates, installUpdate, rollBack, UPDATES_QUERY_KEY } from "../../api/settings";
import { useServices } from "../../app/services";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { checkNow, pollAnswers, removeToken, saveToken } from "./actions";
import { Restarting } from "./RestartScreen";
import { type SwitchLine, switchStore } from "./switchStore";
import { RollBackBody, UpdatesFailed, UpdatesLoading, UpdatesView } from "./UpdatesView";
import { describeUpdates } from "./updatesModel";
import { U } from "./wording";

/** While a check or a switch runs, the status is asked for again every two seconds. */
const BUSY_REFRESH_MS = 2000;

/**
 * Settings › Updates (UI-SET; SYS-06, SYS-07, SET-04): the state of updates from GET /api/updates, Check now,
 * Install (a ConfirmDialog, a "preparing" state while the server checks the files, then the restart panel), Roll back
 * (a ConfirmDialog with 13 §6's files-only or database wording), and the optional GitHub token. The switch and its
 * restart poll live in switchStore, so leaving this page never stops them.
 */
export function UpdatesPage() {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const { phase, error: switchError } = useSyncExternalStore(switchStore.subscribe, switchStore.get, switchStore.get);
  const [checkError, setCheckError] = useState<SwitchLine | null>(null);
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

  if (phase.kind === "restarting") return <Restarting version={phase.version} late={phase.late} back={phase.back} />;
  if (query.isPending) return <UpdatesLoading />;
  // The failure card only when there is nothing to show; a failed refresh keeps the last answer (review item 9)
  if (query.isError && !query.data) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? U.loadRefused(failure.status) : U.loadFailed;
    return <UpdatesFailed text={text} onRetry={() => void query.refetch()} />;
  }

  const model = describeUpdates(query.data, phase);
  const version = model.install.version;
  const previous = model.rollBack.previous;

  async function check() {
    setCheckError(null);
    switchStore.clearError();
    setCheckError(await checkNow(api));
    await refresh();
  }

  async function switchTo(kind: "preparing" | "rolling_back", to: string, send: () => Promise<unknown>) {
    setCheckError(null);
    const outcome = await switchStore.run(kind, to, send, pollAnswers(api));
    if (outcome === "restarting") return;
    await refresh();
    if (outcome === "confirm_required") setRollBackOpen(true); // the database changed since this page loaded: ask again
  }

  return (
    <>
      <UpdatesView
        model={model}
        phase={phase}
        actionError={checkError ?? switchError}
        stale={query.isError}
        actions={{
          onCheck: () => void check(),
          onInstall: () => setInstallOpen(true),
          onRollBack: () => setRollBackOpen(true),
          onSaveToken: async (value) => {
            await saveToken(api, value);
            await refresh();
          },
          onRemoveToken: async () => {
            await removeToken(api);
            await refresh();
          },
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
            const confirm = model.rollBack.databaseChanged; // the same flag chooses the words (rollBackWords)
            void switchTo("rolling_back", previous, () => rollBack(api, confirm));
          }}
        >
          <RollBackBody rollBack={model.rollBack} />
        </ConfirmDialog>
      ) : null}
    </>
  );
}
