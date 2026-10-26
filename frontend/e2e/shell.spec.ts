// UI-SHELL, SYS-03, NFR-1 and 05 section 7 / 07 section 4, against the real backend serving the built UI.
// Every test also fails on any console error or CSP violation (support.ts).
import { axe, expect, newTicket, ROUTES, signIn, test } from "./support";

test.describe("sign-in (SYS-03)", () => {
  test("a ticket signs the tab in and leaves the address bar", async ({ page, request }) => {
    const ticket = await signIn(page, request);
    expect(page.url()).not.toContain(ticket);
    expect(page.url()).toMatch(/\/#\/$/);
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(ticket);
    const cookies = await page.context().cookies();
    expect(cookies.find((cookie) => cookie.name === "shelfsync_session")?.httpOnly).toBe(true);
    expect(await page.evaluate(() => document.cookie)).not.toContain("shelfsync_session");
  });

  test("a refresh keeps the tab signed in", async ({ page, request }) => {
    await signIn(page, request, "#/review");
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();
  });

  test("no ticket and no session shows the signed-out state, once, with no retry", async ({ page }) => {
    const apiCalls: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/")) apiCalls.push(request.url());
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    await expect(page.getByText("Open ShelfSync from the tray icon or the Start menu.")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await expect(page.getByRole("textbox")).toHaveCount(0); // no token prompt
    await page.waitForTimeout(1500);
    expect(apiCalls).toHaveLength(1);
  });

  test("a used ticket can't sign a second tab in", async ({ page, request, browser }) => {
    const ticket = await signIn(page, request);
    const other = await browser.newPage();
    await other.goto(`/#t=${ticket}`);
    await expect(other.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    expect(other.url()).not.toContain(ticket);
    await other.close();
  });

  test("an unknown ticket shows the signed-out state", async ({ page }) => {
    await page.goto("/#t=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    expect(page.url()).not.toContain("AAAAAAAA");
  });

  test("the signed-out state has no accessibility violations, in light and dark", async ({ page }) => {
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect((await axe(page).analyze()).violations).toEqual([]);
    }
  });
});

test.describe("the shell (UI-SHELL)", () => {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`every nav route has its title, its empty state and no axe violations (${colorScheme})`, async ({
      page,
      request,
    }) => {
      await page.emulateMedia({ colorScheme });
      await signIn(page, request);
      await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
      for (const route of ROUTES) {
        await page.goto(`/${route.hash}`);
        await expect(page.getByRole("heading", { level: 1, name: route.title })).toBeVisible();
        await expect(page.locator(".empty")).toBeVisible();
        expect((await axe(page).analyze()).violations, `${route.name} (${colorScheme})`).toEqual([]);
      }
    });
  }

  test("the app bar, the health area, Pause everything and the status strip are there", async ({ page, request }) => {
    await signIn(page, request);
    await expect(page.getByRole("link", { name: "ShelfSync, go to Dashboard" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Connections" })).toContainText("No stores or storage yet");
    const pause = page.getByRole("button", { name: "Pause everything" });
    await expect(pause).toHaveAttribute("aria-disabled", "true");
    await pause.focus();
    await expect(page.getByRole("tooltip")).toContainText("Nothing runs yet, so there's nothing to pause.");
    const strip = page.getByRole("region", { name: "Status" });
    await expect(strip).toContainText("Auto-apply off");
    await expect(strip).toContainText("Trust ramp 0 / 50");
    await expect(strip).toContainText("Last sync not yet");
    await expect(strip).toContainText("Next snapshot 02:00");
  });

  test("keyboard: Tab reaches every nav item in order, and Enter opens the screen with focus on its title", async ({
    page,
    request,
  }) => {
    await signIn(page, request);
    await page.locator("body").focus();
    const names: string[] = [];
    for (let i = 0; i < 25 && names.length < ROUTES.length; i += 1) {
      await page.keyboard.press("Tab");
      const inNav = await page.evaluate(() => Boolean(document.activeElement?.closest("nav")));
      const name = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
      if (inNav && !name.endsWith("menu")) names.push(name);
    }
    expect(names).toEqual(ROUTES.map((route) => route.name));
    await page.getByRole("link", { name: "Review" }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#\/review$/);
    await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeFocused();
  });

  test("the skip link moves focus to the content", async ({ page, request }) => {
    await signIn(page, request);
    await page.locator("body").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Skip to content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
  });

  test("the theme menu overrides Windows and the choice survives a reload", async ({ page, request }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await signIn(page, request);
    await page.getByRole("button", { name: "Theme: Same as Windows" }).click();
    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: "Theme: Dark" }).click();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.getByRole("button", { name: "Theme: Same as Windows" })).toBeFocused();
  });

  test("at 1024 px the nav collapses to icons and keeps its names", async ({ page, request }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await signIn(page, request);
    await expect(page.locator(".app-shell")).toHaveAttribute("data-collapsed", "true");
    for (const route of ROUTES) await expect(page.getByRole("link", { name: route.name, exact: true })).toBeVisible();
    expect((await axe(page).analyze()).violations).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });

  test("an address that isn't a screen says so", async ({ page, request }) => {
    await signIn(page, request, "#/nope");
    await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toBeVisible();
  });
});

test.describe("served files (NFR-1, the CSP)", () => {
  test("every response the page loads comes from 127.0.0.1 and carries the CSP", async ({ page, request }) => {
    const hosts = new Set<string>();
    const missingCsp: string[] = [];
    page.on("response", (response) => {
      const url = new URL(response.url());
      hosts.add(url.host);
      if (!url.pathname.startsWith("/api/") && !response.headers()["content-security-policy"]) {
        missingCsp.push(url.pathname);
      }
    });
    await signIn(page, request);
    await page.reload();
    expect([...hosts]).toEqual([new URL(page.url()).host]);
    expect(missingCsp).toEqual([]);
  });

  test("the ticket route refuses a request that carries an Origin, as the page would send", async ({ request }) => {
    const ticket = await newTicket(request);
    expect(ticket.length).toBeGreaterThan(20);
    const token = process.env.SHELFSYNC_E2E_TOKEN ?? "";
    const refused = await request.post("/api/session/ticket", {
      headers: { Authorization: `Bearer ${token}`, Origin: `http://127.0.0.1:${process.env.SHELFSYNC_E2E_PORT}` },
    });
    expect(refused.status()).toBe(403);
  });
});
