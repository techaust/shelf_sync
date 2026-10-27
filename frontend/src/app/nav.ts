import {
  BrushCleaning,
  History,
  Inbox,
  LayoutDashboard,
  Library,
  type LucideIcon,
  Settings,
  Upload,
} from "lucide-react";

export type CountKey = "review" | "cleanup";

export interface NavItem {
  path: string;
  label: string;
  Icon: LucideIcon;
  count?: CountKey;
  /** What the count means, read after the label by screen readers: "Review, 3 waiting". */
  countNoun?: string;
}

/** The side nav (UI-SHELL): seven items, with the icons of the approved mockup (05 section 2.4 names). */
export const NAV_MAIN: NavItem[] = [
  { path: "/", label: "Dashboard", Icon: LayoutDashboard },
  { path: "/upload", label: "Upload", Icon: Upload },
  { path: "/review", label: "Review", Icon: Inbox, count: "review", countNoun: "waiting" },
  { path: "/catalog", label: "Catalog", Icon: Library },
  { path: "/cleanup", label: "Cleanup", Icon: BrushCleaning, count: "cleanup", countNoun: "issues" },
  { path: "/activity", label: "Activity", Icon: History },
];

export const NAV_SETTINGS: NavItem = { path: "/settings", label: "Settings", Icon: Settings };

export const NAV_ALL: NavItem[] = [...NAV_MAIN, NAV_SETTINGS];
