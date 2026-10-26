import { defineConfig } from "vitest/config";

// Unit tests run in Node: no DOM package is in the approved list (04 section 2.1), so the modules that touch the
// browser take their window objects as arguments and the tests pass fakes. The screens themselves are checked by
// Playwright + axe in CI and in the built-in browser on this PC.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
