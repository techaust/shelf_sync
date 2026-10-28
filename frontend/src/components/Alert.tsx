import { CircleAlert, CircleCheck, Info, type LucideIcon, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export type AlertTone = "info" | "success" | "warning" | "danger";

const ICONS: Record<AlertTone, LucideIcon> = {
  info: Info,
  success: CircleCheck,
  warning: CircleAlert,
  danger: TriangleAlert,
};

/**
 * The inline alert (05 section 6): at the top of the affected card, the reason and at most one action. The tone is
 * never the only sign: each has its own icon, and the text says what happened. Danger is announced at once
 * (role="alert"); the others politely (role="status").
 */
export function Alert({
  id,
  tone,
  title,
  children,
  when = null,
  action,
}: {
  id?: string;
  tone: AlertTone;
  title: ReactNode;
  children?: ReactNode;
  /** When it happened (a local date and time), for a result that stays on screen. */
  when?: string | null;
  action?: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div id={id} className={`alert is-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon className="icon alert__icon" aria-hidden="true" />
      <div className="alert__text">
        <p className="alert__title">{title}</p>
        {children ? <p>{children}</p> : null}
        {when ? <p className="alert__when num">{when}</p> : null}
      </div>
      {action ? <div className="alert__action">{action}</div> : null}
    </div>
  );
}
