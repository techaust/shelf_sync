import type { LucideIcon } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { Link } from "react-router";

/** A screen: its title (the page's h1, focused on navigation) and an optional line under it. */
export function Page({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }) {
  useEffect(() => {
    document.title = `${title}, ShelfSync`;
  }, [title]);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title" tabIndex={-1}>
            {title}
          </h1>
          {sub ? <p className="page-sub">{sub}</p> : null}
        </div>
      </div>
      {children}
    </div>
  );
}

/**
 * The empty state (05 section 6): one line on what will appear here, an optional second line, and the next
 * action when there is one that works today. Wording from the approved mockup and 13 section 3 (ERR-07).
 */
export function EmptyState({
  Icon,
  text,
  sub,
  action,
}: {
  Icon: LucideIcon;
  text: string;
  sub?: string;
  action?: { to: string; label: string; Icon: LucideIcon };
}) {
  return (
    <section className="card">
      <div className="empty">
        <Icon className="icon-lg empty__icon" />
        <p className="empty__text">{text}</p>
        {sub ? <p className="empty__sub">{sub}</p> : null}
        {action ? (
          <Link className="btn" to={action.to}>
            <action.Icon className="icon" />
            {action.label}
          </Link>
        ) : null}
      </div>
    </section>
  );
}
