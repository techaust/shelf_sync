import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router";
import type { ShellStatus } from "../api/placeholder";
import { NAV_MAIN, NAV_SETTINGS, type NavItem } from "../app/nav";
import { Tip } from "./Tip";

function Item({ item, count, collapsed }: { item: NavItem; count: number | null; collapsed: boolean }) {
  const { Icon } = item;
  return (
    <li>
      <Tip content={item.label} side="right" disabled={!collapsed}>
        <NavLink to={item.path} end={item.path === "/"} className="nav-item">
          <Icon className="icon" />
          <span className="nav-item__label">
            {item.label}
            {count ? <span className="sr-only">{`, ${count} ${item.countNoun ?? ""}`}</span> : null}
          </span>
          {count ? (
            <span className="nav-count" aria-hidden="true">
              {count}
            </span>
          ) : null}
        </NavLink>
      </Tip>
    </li>
  );
}

/**
 * The side nav (UI-SHELL): Dashboard, Upload, Review + count, Catalog, Cleanup + count, Activity, then Settings.
 * 248 px, collapsing to 64 px of icons (05 section 5); below 1280 px it collapses by itself, and the button at the
 * foot overrides that until the window crosses 1280 px again. A count of 0 shows no badge (approved mockup).
 */
export function SideNav({
  counts,
  collapsed,
  onToggle,
}: {
  counts: ShellStatus["counts"];
  collapsed: boolean;
  onToggle: () => void;
}) {
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const toggleLabel = collapsed ? "Expand menu" : "Collapse menu";
  return (
    <nav className="side-nav" aria-label="Main">
      <ul>
        {NAV_MAIN.map((item) => (
          <Item key={item.path} item={item} count={item.count ? counts[item.count] : null} collapsed={collapsed} />
        ))}
        <li aria-hidden="true">
          <div className="side-nav__sep" />
        </li>
        <Item item={NAV_SETTINGS} count={null} collapsed={collapsed} />
      </ul>
      <div className="side-nav__foot">
        <Tip content={toggleLabel} side="right" disabled={!collapsed}>
          <button type="button" className="btn is-ghost collapse-btn" aria-expanded={!collapsed} onClick={onToggle}>
            <ToggleIcon className="icon" />
            <span className="nav-item__label">{toggleLabel}</span>
          </button>
        </Tip>
      </div>
    </nav>
  );
}
