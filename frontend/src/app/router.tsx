import { createHashRouter, Navigate } from "react-router";
import { Activity, Catalog, Cleanup, Dashboard, NotFound, Review, Upload } from "../screens/screens";
import { DEFAULT_SETTINGS_SUB, Settings } from "../screens/settings/Settings";
import { AppShell } from "./AppShell";
import { RouteError } from "./RouteError";

/**
 * Hash routing (#/review), not history routing: the backend serves frontend/dist as plain files with no
 * catch-all, so a refresh on any screen asks for "/" and nothing under /api can ever be answered with the page.
 * The sign-in fragment (#t=…) is taken out of the address by main.tsx before this router is created.
 */
export function createAppRouter() {
  return createHashRouter([
    {
      path: "/",
      Component: AppShell,
      // the last guards (m2.5b round 1): never React Router's own error page, which replaces the whole app
      errorElement: <RouteError bare />,
      children: [
        {
          // a pathless layout route: an error in a screen is shown inside the shell, which stays
          errorElement: <RouteError />,
          children: [
            { index: true, Component: Dashboard },
            { path: "upload", Component: Upload },
            { path: "review", Component: Review },
            { path: "catalog", Component: Catalog },
            { path: "cleanup", Component: Cleanup },
            { path: "activity", Component: Activity },
            // #/settings opens its first page; each page has its own address (#/settings/updates), so it can be linked
            {
              path: "settings",
              children: [
                { index: true, element: <Navigate to={DEFAULT_SETTINGS_SUB} replace /> },
                { path: ":sub", Component: Settings },
              ],
            },
            { path: "*", Component: NotFound },
          ],
        },
      ],
    },
  ]);
}
