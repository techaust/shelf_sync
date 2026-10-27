// UI-SHELL, SYS-03, NFR-1 and 05 section 7 / 07 section 4, against the real backend serving the built UI.
// Every test also fails on any console error or CSP violation (support.ts).
import {
  ABORTS_SESSION_REQUESTS,
  addressHolds,
  axe,
  expect,
  newTicket,
  openSignInAddress,
  ROUTES,
  setTicketHash,
  signIn,
  test,
} from "./support";

test.describe("sign-in (SYS-03)", () => {
  test("a ticket signs the tab in and leaves the address bar", async ({ page, request }) => {
    const ticket = await signIn(page, request);
    expect(addressHolds(page, ticket), "the ticket is still in the address").toBe(false);
    expect(page.url()).toMatch(/\/#\/$/);
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
    expect(stored.includes(ticket), "the ticket is in storage").toBe(false);
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
    await openSignInAddress(other, ticket);
    await expect(other.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    expect(addressHolds(other, ticket), "the ticket is still in the address").toBe(false);
    await other.close();
  });

  test("a sign-in address opened in an already-open tab signs it in, without a page load", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    const ticket = await newTicket(request);
    await setTicketHash(page, ticket);
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    expect(addressHolds(page, ticket), "the ticket is still in the address").toBe(false);
  });

  test("a sign-in address opened in a signed-in tab never reaches the router", async ({ page, request }) => {
    await signIn(page, request, "#/review");
    await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();
    // Record every screen title shown from here on: had the router read the sign-in fragment it would show "Not found".
    await page.evaluate(() => {
      const seen: string[] = [];
      (window as unknown as { __headings: string[] }).__headings = seen;
      new MutationObserver(() => {
        const h1 = document.querySelector("h1")?.textContent?.trim();
        if (h1 && seen.at(-1) !== h1) seen.push(h1);
      }).observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    const ticket = await newTicket(request);
    await setTicketHash(page, ticket);
    await expect(page).toHaveURL(/\/#\/$/);
    await expect(page.getByRole("heading", { level: 1, name: ROUTES[0].title })).toBeVisible();
    const headings = await page.evaluate(() => (window as unknown as { __headings: string[] }).__headings);
    expect(headings).not.toContain("Not found");
    expect(addressHolds(page, ticket), "the ticket is still in the address").toBe(false);
    // The new session works: a refresh stays signed in.
    await page.reload();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  });

  test("no answer to a ticket sign-in offers no Try again (the ticket is used up)", async ({ page, request }) => {
    test.info().annotations.push({ type: ABORTS_SESSION_REQUESTS });
    await page.route("**/api/session", (route) => route.abort("connectionrefused"));
    await openSignInAddress(page, await newTicket(request));
    await expect(page.getByRole("heading", { level: 1, name: /didn't answer/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toHaveCount(0);
  });

  test("no answer to the session check offers Try again, which checks once more", async ({ page, request }) => {
    await signIn(page, request);
    test.info().annotations.push({ type: ABORTS_SESSION_REQUESTS });
    await page.route("**/api/session/status", (route) => route.abort("connectionrefused"));
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: /didn't answer/ })).toBeVisible();
    await page.unroute("**/api/session/status");
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  });

  test("an unknown ticket shows the signed-out state", async ({ page }) => {
    await openSignInAddress(page, "A".repeat(43));
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    expect(addressHolds(page, "A".repeat(43)), "the made-up ticket is still in the address").toBe(false);
  });

  test("the signed-out state has no accessibility violations, in light and dark", async ({ page }) => {
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect((await axe(page).analyze()).violations).toEqual([]);
    }
  });

  test("the signed-out state follows a Windows light/dark switch live, with no reload", async ({ page }) => {
    const look = () =>
      page.evaluate(() => ({
        bg: getComputedStyle(document.documentElement).backgroundColor,
        theme: document.documentElement.dataset.theme ?? null,
      }));
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    const light = await look();
    expect(light.theme).toBeNull(); // "Same as Windows" sets no attribute: the stylesheet follows the media query
    await page.emulateMedia({ colorScheme: "dark" });
    await expect.poll(async () => (await look()).bg).not.toBe(light.bg);
    expect((await axe(page).analyze()).violations).toEqual([]);
    await page.emulateMedia({ colorScheme: "light" });
    await expect.poll(async () => (await look()).bg).toBe(light.bg);
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
      await expect(page.locator("html")).not.toHaveAttribute("data-theme"); // follows Windows through CSS
      const bar = await page.evaluate(() => {
        const css = getComputedStyle(document.documentElement);
        return [css.getPropertyValue("--color-appbar-bg"), css.getPropertyValue("--color-ink-750")];
      });
      expect(bar[0] === bar[1], "the app bar is ink-750 in dark only").toBe(colorScheme === "dark");
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
    // By keyboard: Enter on the button opens the menu on its first item, "Same as Windows"; Enter picks it.
    await page.getByRole("button", { name: "Theme: Dark" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menuitemradio", { name: "Same as Windows" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("html")).not.toHaveAttribute("data-theme");
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

// 05 section 7, 07 section 4: Windows high contrast (forced colours) and reduced motion, emulated.
async function highlightedItemOutline(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const item = document.querySelector<HTMLElement>(".menu__item[data-highlighted]");
    if (!item) return null;
    const css = getComputedStyle(item);
    return { style: css.outlineStyle, width: Number.parseFloat(css.outlineWidth) };
  });
}

test.describe("forced colours (Windows high contrast)", () => {
  test.use({ forcedColors: "active" });

  test("the shell and the signed-out state have no axe violations", async ({ page, request }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "This tab isn't signed in." })).toBeVisible();
    expect((await axe(page).analyze()).violations).toEqual([]);
    await signIn(page, request, "#/review");
    expect((await axe(page).analyze()).violations).toEqual([]);
  });

  test("the theme menu's highlighted item keeps a visible outline", async ({ page, request }) => {
    await signIn(page, request);
    await page.getByRole("button", { name: /^Theme: / }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menuitemradio", { name: "Same as Windows" })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("menuitemradio", { name: "Light" })).toBeFocused();
    const outline = await highlightedItemOutline(page);
    expect(outline?.style).toBe("solid");
    expect(outline?.width ?? 0).toBeGreaterThanOrEqual(2);
    await page.keyboard.press("Escape");
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("nothing animates, focus stays visible, and there are no axe violations", async ({ page, request }) => {
    await signIn(page, request);
    const moving = await page.evaluate(
      () =>
        [...document.querySelectorAll<HTMLElement>("body *")]
          .map((element) => getComputedStyle(element))
          .filter(
            (css) =>
              css.transitionProperty !== "none" &&
              css.transitionDuration.split(",").some((d) => Number.parseFloat(d) > 0),
          ).length,
    );
    expect(moving).toBe(0);
    await page.getByRole("button", { name: /^Theme: / }).focus();
    await page.keyboard.press("Enter");
    const outline = await highlightedItemOutline(page);
    expect(outline?.style).toBe("solid");
    expect(outline?.width ?? 0).toBeGreaterThanOrEqual(2);
    await page.keyboard.press("Escape");
    expect((await axe(page).analyze()).violations).toEqual([]);
  });
});
