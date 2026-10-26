import { randomBytes } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

// Playwright + axe run in CI only (owner: no test browser is downloaded to this PC, docs/11). They drive the real
// backend serving the built UI on 127.0.0.1 (e2e/server.py), so the CSP, the Host check and the sign-in are the
// real ones. The install token is a fresh throwaway for each run, held in memory by the test server.
const PORT = Number(process.env.SHELFSYNC_E2E_PORT ?? 47699);
const token = process.env.SHELFSYNC_E2E_TOKEN ?? randomBytes(32).toString("base64url");
process.env.SHELFSYNC_E2E_TOKEN = token; // the test workers read it to ask for tickets (e2e/support.ts)
process.env.SHELFSYNC_E2E_PORT = String(PORT);

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Never bypassCSP: a CSP violation must show up as one.
    bypassCSP: false,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: "uv run --locked python -B frontend/e2e/server.py",
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: { PYTHONPATH: "backend", SHELFSYNC_E2E_TOKEN: token, SHELFSYNC_E2E_PORT: String(PORT) },
    reuseExistingServer: false,
    stdout: "ignore",
    stderr: "pipe",
    timeout: 60_000,
  },
});
