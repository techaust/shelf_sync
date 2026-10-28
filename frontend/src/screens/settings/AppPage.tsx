import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { type FormEvent, useState } from "react";
import { ApiError } from "../../api/client";
import { APP_SETTINGS_QUERY_KEY, type AppSettings, getAppSettings } from "../../api/settings";
import { settingsWriter } from "../../api/settingsWriter";
import { useServices } from "../../app/services";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { cacheSaved, useSavedTheme } from "../../theme/useSavedTheme";
import { AppFailed, AppLoading, type AppResult, AppView } from "./AppView";
import { resetAccess, saveApp } from "./actions";
import { type AppForm, type AppFormErrors, checkAppForm, formFrom } from "./forms";
import { useSwitchPhase } from "./switchStore";
import { A } from "./wording";

/** The form, started from the stored settings; a save puts what was saved back into it. */
function AppSettingsForm({ stored, stale }: { stored: AppSettings; stale: boolean }) {
  const { api, session } = useServices();
  const queryClient = useQueryClient();
  const { preference, choose } = useSavedTheme();
  const [form, setForm] = useState<AppForm>(() => formFrom(stored));
  const [errors, setErrors] = useState<AppFormErrors>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<AppResult | null>(null);
  const [themeFailed, setThemeFailed] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const checked = checkAppForm(form, preference, stored);
    if (checked.errors) {
      setErrors(checked.errors);
      setResult(null);
      const first = checked.errors.port ? "app-port" : "app-logs";
      document.getElementById(first)?.focus();
      return;
    }
    setErrors({});
    setSaving(true);
    setResult(null);
    const { saved, result: line } = await saveApp(settingsWriter(api), checked.values);
    if (saved) {
      queryClient.setQueryData<AppSettings>(APP_SETTINGS_QUERY_KEY, (old) => cacheSaved(old, saved));
      setForm(formFrom(saved));
    }
    setResult(line);
    setSaving(false);
  }

  async function reset() {
    setResetting(true);
    setResetError(null);
    // On 204 the old sign-in is gone (every session ended, the cookie removed): the tab shows the signed-out state.
    const failed = await resetAccess(api, session);
    if (failed) {
      setResetError(failed);
      setResetting(false);
    }
  }

  return (
    <>
      <AppView
        form={form}
        errors={errors}
        theme={preference}
        installed={stored.installed}
        saving={saving}
        result={result}
        themeFailed={themeFailed}
        stale={stale}
        handlers={{
          onTheme: (theme) => {
            setThemeFailed(false);
            void choose(theme).then((ok) => setThemeFailed(!ok));
          },
          onChange: (next) => {
            setForm((current) => ({ ...current, ...next }));
            setErrors(({ port, logDays }) => {
              const kept: AppFormErrors = {};
              if (port && !("port" in next)) kept.port = port;
              if (logDays && !("logDays" in next)) kept.logDays = logDays;
              return kept;
            });
            setResult(null);
          },
          onSave: (event) => void save(event),
          onReset: () => {
            setResetError(null);
            setResetOpen(true);
          },
        }}
      />
      <ConfirmDialog
        open={resetOpen}
        title={A.resetDialogTitle}
        confirmLabel={A.resetConfirm}
        ConfirmIcon={KeyRound}
        danger
        busy={resetting}
        error={resetError}
        onCancel={() => setResetOpen(false)}
        onConfirm={() => void reset()}
      >
        <p>{A.resetDialogLead}</p>
        <p className="muted">{A.resetLine}</p>
      </ConfirmDialog>
    </>
  );
}

/** Settings › App (UI-SET; SET-06, LOG-01): theme, Start with Windows, notifications, port, log retention, and the
 *  Reset access token danger zone. */
export function AppPage() {
  const { api } = useServices();
  const restarting = useSwitchPhase().kind === "restarting";
  const query = useQuery({
    queryKey: APP_SETTINGS_QUERY_KEY,
    queryFn: () => getAppSettings(api),
    enabled: !restarting, // paused while ShelfSync restarts (re-review, medium)
  });
  if (query.isPending) return <AppLoading />;
  // The failure card only when there is nothing to show; a failed refresh keeps the form (review item 9)
  if (query.isError && !query.data) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? A.loadRefused(failure.status) : A.loadFailed;
    return <AppFailed text={text} onRetry={() => void query.refetch()} />;
  }
  // Not keyed by the data: a theme chosen in the app bar updates the stored copy, and must not reset the form.
  return <AppSettingsForm stored={query.data} stale={query.isError} />;
}
