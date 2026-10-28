import { AppWindow, Archive, HardDrive, type LucideIcon, RefreshCcw, SlidersHorizontal, Store } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useParams } from "react-router";
import { EmptyState, Page } from "../../components/Page";
import { NotFound } from "../screens";
import { AppPage } from "./AppPage";
import { UpdatesPage } from "./UpdatesPage";
import { LATER, SETTINGS_TITLE } from "./wording";

export type SettingsSub = "stores" | "storage" | "rules" | "updates" | "backup" | "app";

/** The sub-nav (UI-SET): all six pages, with the approved mockup's names and icons. */
export const SETTINGS_PAGES: { sub: SettingsSub; label: string; Icon: LucideIcon }[] = [
  { sub: "stores", label: "Stores", Icon: Store },
  { sub: "storage", label: "Storage", Icon: HardDrive },
  { sub: "rules", label: "Rules", Icon: SlidersHorizontal },
  { sub: "updates", label: "Updates", Icon: RefreshCcw },
  { sub: "backup", label: "Backup", Icon: Archive },
  { sub: "app", label: "App", Icon: AppWindow },
];

export const DEFAULT_SETTINGS_SUB: SettingsSub = "stores";

function isSub(value: string | undefined): value is SettingsSub {
  return SETTINGS_PAGES.some((page) => page.sub === value);
}

/** Stores, Storage, Rules and Backup until their milestones (M2, M5): one plain line on what will be here. */
function Later({ sub, Icon }: { sub: keyof typeof LATER; Icon: LucideIcon }) {
  return <EmptyState Icon={Icon} text={LATER[sub].text} sub={LATER[sub].sub} />;
}

/** The sub-page's content, by its address. */
function content(sub: SettingsSub, Icon: LucideIcon): ReactNode {
  switch (sub) {
    case "updates":
      return <UpdatesPage />;
    case "app":
      return <AppPage />;
    default:
      return <Later sub={sub} Icon={Icon} />;
  }
}

/**
 * Settings (UI-SET) at #/settings/<page>: the page title, the sub-nav on the left and the sub-page on the right. The
 * sub-page's own title (h2) is where the focus lands after a navigation (data-nav-focus; AppShell moves it), as in
 * the approved mockup.
 */
export function Settings() {
  const { sub } = useParams();
  if (!isSub(sub)) return <NotFound />;
  const page = SETTINGS_PAGES.find((entry) => entry.sub === sub) ?? SETTINGS_PAGES[0];
  if (!page) return <NotFound />;
  return (
    <Page title={SETTINGS_TITLE}>
      <div className="settings-grid">
        <nav className="sub-nav" aria-label={SETTINGS_TITLE}>
          <ul>
            {SETTINGS_PAGES.map(({ sub: key, label, Icon }) => (
              <li key={key}>
                <NavLink className="sub-nav__item" to={`/settings/${key}`}>
                  <Icon className="icon" aria-hidden="true" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="settings-main">
          <h2 className="settings-title" tabIndex={-1} data-nav-focus="">
            {page.label}
          </h2>
          {content(page.sub, page.Icon)}
        </div>
      </div>
    </Page>
  );
}
