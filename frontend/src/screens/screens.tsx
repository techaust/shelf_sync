// The seven screens as M1a.3 ships them: each one's title and its empty state (05 section 6). The screens
// themselves come in later milestones (Dashboard M3-M5, Upload and Review M4-M5, Catalog M3, Cleanup M3,
// Activity M5; Settings is in settings/, from M1b). Wording is the approved mockup's (13 section 6), with ERR-07 from 13 section 3.
// An action is shown only where it works today; the mockup's "Add a store", "Sync now" and the drop zone's
// "Drop ZIPs above" come with the screens that make them work.

import { useQuery } from "@tanstack/react-query";
import { BrushCleaning, FileArchive, History, Inbox, LayoutDashboard, Store, Upload as UploadIcon } from "lucide-react";
import { fetchShellStatus, SHELL_STATUS_PLACEHOLDER, SHELL_STATUS_QUERY_KEY } from "../api/placeholder";
import { EmptyState, Page } from "../components/Page";
import { formatLongDate, greeting } from "../lib/time";

const OPEN_UPLOAD = { to: "/upload", label: "Open Upload", Icon: UploadIcon };

export function Dashboard() {
  const now = new Date();
  return (
    <Page title={greeting(now)} sub={formatLongDate(now)}>
      <EmptyState
        Icon={History}
        text="No updates yet. Every update ShelfSync applies to a store appears here."
        action={OPEN_UPLOAD}
      />
    </Page>
  );
}

export function Upload() {
  return (
    <Page
      title="Upload"
      sub="Each ZIP is inspected, scanned with Windows Defender and matched before anything changes on a store."
    >
      <EmptyState
        Icon={FileArchive}
        text="No ZIPs in this batch. Each ZIP you add gets a row here, with its steps and result."
      />
    </Page>
  );
}

export function Review() {
  return (
    <Page title="Review">
      <EmptyState Icon={Inbox} text="Nothing waiting. ZIPs that need a decision appear here." action={OPEN_UPLOAD} />
    </Page>
  );
}

export function Catalog() {
  return (
    <Page title="Catalog">
      <EmptyState
        Icon={Store}
        text="Add your first store to start."
        sub="The catalog fills in from your stores' downloadable products."
      />
    </Page>
  );
}

export function Cleanup() {
  const { data } = useQuery({ queryKey: SHELL_STATUS_QUERY_KEY, queryFn: fetchShellStatus });
  const minutes = (data ?? SHELL_STATUS_PLACEHOLDER).syncIntervalMinutes;
  return (
    <Page title="Cleanup">
      <EmptyState Icon={BrushCleaning} text={`No issues. ShelfSync checks your stores every ${minutes} minutes.`} />
    </Page>
  );
}

export function Activity() {
  return (
    <Page title="Activity">
      <EmptyState
        Icon={History}
        text="Nothing changed yet. Every change ShelfSync makes to a store or S3 appears here."
        action={{ to: "/upload", label: "Upload a ZIP", Icon: UploadIcon }}
      />
    </Page>
  );
}

/** An address inside the app that isn't a screen (proposed wording, section 4 of the run file). */
export function NotFound() {
  return (
    <Page title="Not found">
      <EmptyState
        Icon={LayoutDashboard}
        text="There's no screen at this address."
        action={{ to: "/", label: "Open Dashboard", Icon: LayoutDashboard }}
      />
    </Page>
  );
}
