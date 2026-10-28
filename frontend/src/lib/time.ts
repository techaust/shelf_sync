// Times are stored in UTC and shown in Windows local time with the zone's name (CLAUDE.md conventions, 13 section 6:
// "Times in India Standard Time"). Formatters are made once; Intl is slow to build them.

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = JSON.stringify(options);
  let made = formatters.get(key);
  if (!made) {
    made = new Intl.DateTimeFormat("en-GB", options);
    formatters.set(key, made);
  }
  return made;
}

/** The local zone's long name, e.g. "India Standard Time", or "" if the browser can't say. */
export function timeZoneName(at: Date = new Date()): string {
  try {
    return (
      formatter({ timeZoneName: "long" })
        .formatToParts(at)
        .find((part) => part.type === "timeZoneName")?.value ?? ""
    );
  } catch {
    return "";
  }
}

/** "09:30": local time, 24-hour. */
export function formatTime(at: Date): string {
  return formatter({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(at);
}

/** "Tuesday 27 October 2026" */
export function formatLongDate(at: Date): string {
  return formatter({ weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(at);
}

/** The Dashboard's greeting, by local time of day (as in the approved mockup). */
export function greeting(at: Date): string {
  const hour = Number(formatter({ hour: "numeric", hourCycle: "h23" }).format(at));
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** "28 October 2026" */
export function formatDate(at: Date): string {
  return formatter({ day: "numeric", month: "long", year: "numeric" }).format(at);
}

/**
 * "28 October 2026 at 09:30 India Standard Time": a stored UTC time as Windows local time with the zone's name
 * (CLAUDE.md conventions; the {date} of 13 section 3's Updates rows).
 */
export function formatDateTime(at: Date): string {
  const zone = timeZoneName(at);
  return `${formatDate(at)} at ${formatTime(at)}${zone ? ` ${zone}` : ""}`;
}

/** A stored UTC ISO 8601 time, or null when it is missing or isn't one. */
export function parseUtc(value: string | null | undefined): Date | null {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? null : at;
}

/** A stored UTC time as Windows local time with the zone's name, or null (the views take it as a prop, so tests can
 *  pass a fixed one). */
export type WhenFormat = (iso: string | null | undefined) => string | null;
export const localWhen: WhenFormat = (iso) => {
  const at = parseUtc(iso);
  return at ? formatDateTime(at) : null;
};
