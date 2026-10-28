import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { Outlet, useLocation } from "react-router";
import { fetchShellStatus, SHELL_STATUS_PLACEHOLDER, SHELL_STATUS_QUERY_KEY } from "../api/placeholder";
import { AppBar } from "../components/AppBar";
import { HealthArea } from "../components/HealthArea";
import { HelpButton, HelpPanel } from "../components/help/HelpPanel";
import { PauseButton } from "../components/PauseButton";
import { SideNav } from "../components/SideNav";
import { StatusStrip } from "../components/StatusStrip";
import { ThemeMenu } from "../components/ThemeMenu";
import { useCollapsedNav } from "../components/useCollapsedNav";
import { storeTests } from "../lib/storeTests";
import { RestartScreen, shellTakesOver } from "../screens/settings/RestartScreen";
import { useSwitchPhase } from "../screens/settings/switchStore";
import { useThemeFromServer } from "../theme/useSavedTheme";
import { useRunStoreTest, useStoresQuery } from "./useStores";

/**
 * The AppShell (UI-SHELL, 05 section 5): app bar, side nav, status strip and the routed screen. Status comes from
 * the placeholder module through TanStack Query, so M5 swaps the query function and nothing here changes; the store
 * chips come from GET /api/stores (M2.5a). The Help panel lives here once, opened from the app bar's Help button or a
 * page's guide button.
 */
export function AppShell() {
  const { data } = useQuery({ queryKey: SHELL_STATUS_QUERY_KEY, queryFn: fetchShellStatus });
  const status = data ?? SHELL_STATUS_PLACEHOLDER;
  const { collapsed, toggle } = useCollapsedNav();
  const main = useRef<HTMLElement>(null);
  const location = useLocation();
  const first = useRef(true);
  useThemeFromServer();
  const phase = useSwitchPhase();
  const stores = useStoresQuery();
  const runTest = useRunStoreTest();
  const tests = useSyncExternalStore(storeTests.subscribe, storeTests.get, storeTests.get);

  // Every navigation moves focus to the new screen's title, so keyboard and screen-reader users land on it
  // (not on the first load: focus starts at the top of the page). A screen with its own pages (Settings) marks the
  // heading to land on with data-nav-focus: there it is the sub-page's title, as in the approved mockup.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs on each change of location, by design
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const heading =
      main.current?.querySelector<HTMLElement>("[data-nav-focus]") ?? main.current?.querySelector<HTMLElement>("h1");
    (heading ?? main.current)?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="app-shell" data-collapsed={collapsed}>
      {/* A button, not an <a href="#main">: the hash router would read #main as a screen address. */}
      <button type="button" className="skip-link" onClick={skipToMain}>
        Skip to content
      </button>
      <AppBar>
        <HealthArea
          stores={stores.data}
          failed={stores.isError}
          storage={status.storage}
          tests={tests}
          onTest={runTest}
        />
        <div className="app-bar__end">
          <HelpButton />
          <ThemeMenu />
          <PauseButton />
        </div>
      </AppBar>
      <SideNav counts={status.counts} collapsed={collapsed} onToggle={toggle} />
      <div className="app-main">
        <StatusStrip status={status} />
        <main id="main" ref={main} tabIndex={-1}>
          {phase.kind === "restarting" && shellTakesOver(phase, location.pathname) ? (
            <RestartScreen phase={phase} />
          ) : (
            <Outlet />
          )}
        </main>
      </div>
      <HelpPanel />
    </div>
  );
}

function skipToMain() {
  document.getElementById("main")?.focus();
}
