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

/** A single-use ticket, asked for the way the launcher does: the install token, and no Origin header. */
export async function newTicket(request: APIRequestContext): Promise<string> {
  const token = process.env.SHELFSYNC_E2E_TOKEN;
  if (!token) throw new Error("SHELFSYNC_E2E_TOKEN isn't set (playwright.config.ts sets it)");
  const response = await request.post("/api/session/ticket", { headers: { Authorization: `Bearer ${token}` } });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { ticket: string };
  return body.ticket;
}

/** Opens the sign-in address and waits for the shell. */
export async function signIn(page: Page, request: APIRequestContext, hash = ""): Promise<string> {
  const ticket = await newTicket(request);
  await page.goto(`/#t=${ticket}`);
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

// Chrome logs every non-2xx fetch as a console error. The sign-in exchange answers 401 when the tab can't sign in,
// and the session check answers 401 (signed out) or 405 (signed in; see SESSION_PROBE_PATH in src/api/session.ts,
// an open question for the lead). Those expected answers, on those two paths only, are not counted as problems.
const EXPECTED_STATUS_PATHS = new Set(["/api/session", "/api/session/reset-token"]);
function isExpectedSessionAnswer(text: string, url: string): boolean {
  if (!/^Failed to load resource: the server responded with a status of (401|405)\b/.test(text)) return false;
  try {
    return EXPECTED_STATUS_PATHS.has(new URL(url).pathname);
  } catch {
    return false;
  }
}

/**
 * Every test fails on a console error, an uncaught page error or a CSP violation (the console message and the
 * securitypolicyviolation event are both watched; the listener is added before any page script runs).
 */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        if (isExpectedSessionAnswer(message.text(), message.location().url)) return;
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
