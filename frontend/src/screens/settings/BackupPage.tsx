import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  BACKUP_SETTINGS_QUERY_KEY,
  type BackupSettings,
  type BackupSettingsValues,
  exportBackup,
  getBackupSettings,
  importBackup,
  saveBackupSettings,
  saveBlob,
} from "../../api/backup";
import { ApiError } from "../../api/client";
import { useServices } from "../../app/services";
import { useStoresQuery } from "../../app/useStores";
import { helpStore } from "../../components/help/helpModel";
import { localWhen } from "../../lib/time";
import {
  BackupFailed,
  BackupLoading,
  type ChosenFile,
  DailyCard,
  ExportSection,
  ImportSection,
  KEEP_FIELD_IDS,
  TransferCard,
} from "./BackupView";
import { attemptExport, attemptImport } from "./backupActions";
import {
  checkKeepForm,
  dailyFacts,
  followStored,
  type ImportFailure,
  type KeepErrors,
  type KeepForm,
  keepDirty,
  keepFormFrom,
  type Line,
  preCheckFile,
  sniffEncrypted,
} from "./backupModel";
import { B } from "./backupWording";
import { useSwitchPhase } from "./switchStore";

/** Runs a focus move after the next render, once what it moves to is on the page. */
function useAfterRender(): (run: () => void) => void {
  const next = useRef<(() => void) | null>(null);
  useEffect(() => {
    const run = next.current;
    next.current = null;
    run?.();
  });
  return (run) => {
    next.current = run;
  };
}

/** "What's kept": the facts and the two keep settings; a save puts what was saved back into the form and cache. */
function Daily({ settings }: { settings: BackupSettings }) {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<KeepForm>(() => keepFormFrom(settings));
  const [errors, setErrors] = useState<KeepErrors>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Line | null>(null);
  // The stored values change under the form after an import (m2.5b round 1): an untouched form follows them, so
  // Save can never write the old numbers back over the imported ones. A form being edited keeps its edits.
  const stored = useRef<BackupSettingsValues>(settings);
  const kept = settings.db_backups_kept;
  const days = settings.snapshot_retention_days;
  useEffect(() => {
    const next = { db_backups_kept: kept, snapshot_retention_days: days };
    const before = stored.current;
    stored.current = next;
    setForm((current) => followStored(current, before, next));
  }, [kept, days]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const checked = checkKeepForm(form);
    if (checked.errors) {
      setErrors(checked.errors);
      setResult(null);
      document.getElementById(checked.errors.kept ? KEEP_FIELD_IDS.kept : KEEP_FIELD_IDS.snapshots)?.focus();
      return;
    }
    if (!keepDirty(form, settings)) return;
    setErrors({});
    setSaving(true);
    setResult(null);
    try {
      const saved = await saveBackupSettings(api, checked.values);
      queryClient.setQueryData<BackupSettings>(BACKUP_SETTINGS_QUERY_KEY, (old) => (old ? { ...old, ...saved } : old));
      setForm(keepFormFrom(saved));
      setResult({ tone: "success", text: B.saved });
      // lowering the count removes the surplus at once: read the facts again
      void queryClient.invalidateQueries({ queryKey: BACKUP_SETTINGS_QUERY_KEY });
    } catch (failure) {
      setResult({
        tone: "danger",
        text: failure instanceof ApiError ? B.saveRefused(failure.status) : B.saveFailed,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <DailyCard
      facts={dailyFacts(settings, localWhen, new Date())}
      form={form}
      errors={errors}
      dirty={keepDirty(form, settings)}
      saving={saving}
      result={result}
      onChange={(next) => {
        setForm((current) => ({ ...current, ...next }));
        setErrors((current) => {
          const kept = { ...current };
          for (const key of Object.keys(next)) delete kept[key as keyof KeepErrors];
          return kept;
        });
        setResult(null);
      }}
      onSave={(event) => void save(event)}
      onRestoreGuide={() => helpStore.open("restore-database")}
    />
  );
}

/** Export and import: one runs at a time (the API's own slot answers `busy` across tabs). */
function Transfer() {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const stores = useStoresQuery();
  const names = useMemo(
    () => new Map((stores.data ?? []).map((store) => [store.code, store.name] as const)),
    [stores.data],
  );
  const afterRender = useAfterRender();
  const [running, setRunning] = useState<"export" | "import" | null>(null);
  // set at once, so two submits in the same tick send one request (state only changes at the next render)
  const busy = useRef(false);
  // export
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const [exportErrors, setExportErrors] = useState<{ first?: string; second?: string }>({});
  const [exportResult, setExportResult] = useState<Line | null>(null);
  const firstRef = useRef<HTMLInputElement>(null);
  const secondRef = useRef<HTMLInputElement>(null);
  // import: the file's text stays in a ref (never rendered), dropped after the import or another choice
  const [chosen, setChosen] = useState<ChosenFile | null>(null);
  const [passphraseError, setPassphraseError] = useState<string | undefined>(undefined);
  const [importResult, setImportResult] = useState<ImportFailure | Line | null>(null);
  const [resultFile, setResultFile] = useState<string | null>(null);
  const passRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const fileText = useRef<string | null>(null);

  async function runExport(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true;
    setExportResult(null);
    setImportResult(null);
    const outcome = await attemptExport({
      includeSecrets,
      first: firstRef.current,
      second: secondRef.current,
      names,
      send: (passphrase) => exportBackup(api, passphrase),
      save: (file) => saveBlob(file),
      onSend: () => {
        setExportErrors({});
        setRunning("export");
      },
    });
    busy.current = false;
    setRunning(null);
    if (outcome.kind === "refused") {
      setExportErrors(outcome.errors);
      firstRef.current?.focus();
    } else setExportResult(outcome.line);
  }

  async function chooseFile(file: File | null) {
    if (!file) return;
    fileText.current = null;
    setChosen(null);
    setPassphraseError(undefined);
    setResultFile(file.name);
    const refused = preCheckFile(file.name, file.size);
    if (refused) {
      setImportResult(refused);
      return;
    }
    let text: string;
    try {
      text = await file.text(); // only after the size check: a big file is never read
    } catch {
      setImportResult({ tone: "danger", text: B.readFailed(file.name) });
      return;
    }
    fileText.current = text;
    const encrypted = sniffEncrypted(text);
    setImportResult(null);
    setChosen({ name: file.name, encrypted });
    afterRender(() => document.getElementById(encrypted ? "backup-import-pass" : "backup-import")?.focus());
  }

  async function runImport(event: FormEvent) {
    event.preventDefault();
    const text = fileText.current;
    if (busy.current || !chosen || text === null) return;
    busy.current = true;
    setImportResult(null);
    setExportResult(null);
    setResultFile(chosen.name);
    const outcome = await attemptImport({
      encrypted: chosen.encrypted,
      input: passRef.current,
      text,
      fileName: chosen.name,
      send: (file, passphrase) => importBackup(api, file, passphrase),
      onSend: () => {
        setPassphraseError(undefined);
        setRunning("import");
      },
    });
    busy.current = false;
    setRunning(null);
    if (outcome.kind === "refused") {
      setPassphraseError(outcome.passphraseError);
      passRef.current?.focus();
    } else if (outcome.kind === "imported") {
      fileText.current = null;
      setChosen(null);
      setImportResult(outcome.line);
      // the stores, the settings and the keys all changed
      void queryClient.invalidateQueries();
      afterRender(() => document.getElementById("backup-pick")?.focus());
    } else {
      const { failure } = outcome;
      setImportResult(failure);
      if (failure.passphrase === "needed" && !chosen.encrypted) setChosen({ ...chosen, encrypted: true });
      if (failure.passphrase) afterRender(() => passRef.current?.focus());
    }
  }

  return (
    <TransferCard>
      <ExportSection
        state={{
          includeSecrets,
          errors: exportErrors,
          running: running === "export",
          blocked: running === "import",
          result: exportResult,
          firstRef,
          secondRef,
        }}
        handlers={{
          onIncludeSecrets: (next) => {
            setIncludeSecrets(next);
            setExportErrors({});
            setExportResult(null);
            if (next) afterRender(() => firstRef.current?.focus());
          },
          onTyped: () => {
            if (exportErrors.first || exportErrors.second) setExportErrors({});
          },
          onExport: (event) => void runExport(event),
        }}
      />
      <ImportSection
        state={{
          chosen,
          passphraseError,
          running: running === "import",
          blocked: running === "export",
          result: importResult,
          resultFile,
          passRef,
          fileRef,
        }}
        handlers={{
          onPick: () => fileRef.current?.click(),
          onFile: (file) => void chooseFile(file),
          onTyped: () => {
            if (passphraseError) setPassphraseError(undefined);
          },
          onImport: (event) => void runImport(event),
          onRetryPassphrase: () => passRef.current?.focus(),
        }}
      />
    </TransferCard>
  );
}

/** Settings › Backup (UI-SET; SET-05, BAK-01): what the daily backups keep, and the settings file's export and
 *  import. Restoring a daily backup is a command (docs/runbooks/restore-database.md), never a button here. */
export function BackupPage() {
  const { api } = useServices();
  const restarting = useSwitchPhase().kind === "restarting";
  const query = useQuery({
    queryKey: BACKUP_SETTINGS_QUERY_KEY,
    queryFn: () => getBackupSettings(api),
    enabled: !restarting,
  });
  let daily: ReactNode;
  if (query.isPending) daily = <BackupLoading />;
  else if (query.isError && !query.data) {
    const failure = query.error;
    const text = failure instanceof ApiError && failure.status !== 401 ? B.loadRefused(failure.status) : B.loadFailed;
    daily = <BackupFailed text={text} onRetry={() => void query.refetch()} />;
  } else {
    daily = (
      <>
        {query.isError ? (
          <p className="stores__stale field__hint" role="status">
            {B.staleNotice}
          </p>
        ) : null}
        <Daily settings={query.data} />
      </>
    );
  }
  return (
    <div className="backup">
      {daily}
      <Transfer />
    </div>
  );
}
