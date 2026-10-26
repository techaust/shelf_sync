import AxeBuilder from "@axe-core/playwright";
import { type APIRequestContext, test as base, expect, type Page } from "@playwright/test";

/** The nav routes (UI-SHELL) with each screen's title; the Dashboard's title is the greeting. */
export const ROUTES = [
  { hash: "#/", name: "Dashboard", title: /^Good (morning|afternoon|evening)$/ },
  { hash: "#/upload", name: "Upload", title: /^Upload$/ },
  { hash: "#/review", name: "Review", title: /^Review$/ },
  { hash: "#/catalog", name: "Catalog", title: /^Catalog$/ },
  { hash: "#/cleanup", name: "Cleanup", title: /^Cleanup$/ },
  { hash: "#/activity", name: "Activity", title: /^Activity$/ },
  { hash: "#/settings", name: "Settings", title: /^Settings$/ },
] as const;

export const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

// The sign-in fragment's key. The full fragment is never written out in this folder: the HTML report shows source
// lines around a failure, and the report must hold nothing that looks like a sign-in address (e2e/check-output.mjs).
const TICKET_KEY = "t";

/** A single-use ticket, asked for the way the launcher does: the install token, and no Origin header. */
export async function newTicket(request: APIRequestContext): Promise<string> {
  const token = process.env.SHELFSYNC_E2E_TOKEN;
  if (!token) throw new Error("SHELFSYNC_E2E_TOKEN isn't set (playwright.config.ts sets it)");
  const response = await request.post("/api/session/ticket", { headers: { Authorization: `Bearer ${token}` } });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { ticket: string };
  return body.ticket;
}

/**
 * Opens a sign-in address (the "t" fragment holding a ticket) as a fresh page load, the way the launcher does. The address is set from
 * inside the page (from about:blank, so it is a full load), never through page.goto: Playwright puts goto's URL
 * in its step titles, and the HTML report must hold no ticket (it is uploaded from a public repository).
 */
export async function openSignInAddress(page: Page, ticket: string): Promise<void> {
  const target = `http://127.0.0.1:${process.env.SHELFSYNC_E2E_PORT ?? "47699"}/`;
  await page.goto("about:blank");
  await Promise.all([
    page.waitForURL((url) => url.href.startsWith(target)),
    page.evaluate(([base, value, key]) => window.location.assign(`${base}#${key}=${value}`), [
      target,
      ticket,
      TICKET_KEY,
    ] as const),
  ]);
}

/** Sets the sign-in fragment in an already-open tab (no page load), without the ticket in any step title. */
export async function setTicketHash(page: Page, ticket: string): Promise<void> {
  await page.evaluate(
    ([value, key]) => {
      window.location.hash = `${key}=${value}`;
    },
    [ticket, TICKET_KEY] as const,
  );
}

/** True when the page's address still holds the ticket. Asserted as a boolean, so a failure message never
 *  repeats the ticket. */
export function addressHolds(page: Page, ticket: string): boolean {
  return page.url().includes(ticket);
}

/** Opens the sign-in address and waits for the shell. */
export async function signIn(page: Page, request: APIRequestContext, hash = ""): Promise<string> {
  const ticket = await newTicket(request);
  await openSignInAddress(page, ticket);
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  if (hash) await page.goto(`/${hash}`);
  return ticket;
}

export function axe(page: Page): AxeBuilder {
  return new AxeBuilder({ page }).withTags(WCAG_TAGS);
}

declare global {
  interface Window {
    __cspViolations?: string[];
  }
}

// Chrome logs every non-2xx fetch as a console error. A tab that can't sign in gets 401 from the sign-in exchange
// (POST /api/session) or from the session check (GET /api/session/status): that is the signed-out state working.
// Those 401s, on those two paths only, are not counted as problems; every other status and path still is.
const EXPECTED_401_PATHS = new Set(["/api/session", "/api/session/status"]);
function isExpectedSessionAnswer(text: string, url: string, abortsSessionRequests: boolean): boolean {
  const refused = /^Failed to load resource: net::ERR_/.test(text);
  if (!/^Failed to load resource: the server responded with a status of 401\b/.test(text)) {
    if (!(refused && abortsSessionRequests)) return false;
  }
  try {
    return EXPECTED_401_PATHS.has(new URL(url).pathname);
  } catch {
    return false;
  }
}

/** A test that makes the session requests get no answer (page.route aborts them) marks itself with this
 *  annotation; the network error Chrome logs for those two paths is then expected too. */
export const ABORTS_SESSION_REQUESTS = "aborts-session-requests";

/**
 * Every test fails on a console error, an uncaught page error or a CSP violation (the console message and the
 * securitypolicyviolation event are both watched; the listener is added before any page script runs).
 */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use, testInfo) => {
      const problems: string[] = [];
      const aborts = () => testInfo.annotations.some((annotation) => annotation.type === ABORTS_SESSION_REQUESTS);
      page.on("console", (message) => {
        if (isExpectedSessionAnswer(message.text(), message.location().url, aborts())) return;
        if (message.type() === "error" || /Content Security Policy|Refused to/i.test(message.text())) {
          problems.push(`console ${message.type()}: ${message.text()}`);
        }
      });
      page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
      await page.addInitScript(() => {
        window.__cspViolations = [];
        document.addEventListener("securitypolicyviolation", (event) => {
          window.__cspViolations?.push(`${event.violatedDirective} ${event.blockedURI}`);
        });
      });
      await use(problems);
      const violations = await page.evaluate(() => window.__cspViolations ?? []).catch(() => [] as string[]);
      expect([...problems, ...violations.map((v) => `CSP violation: ${v}`)]).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
