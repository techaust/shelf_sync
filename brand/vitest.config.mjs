import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.mjs"],
    environment: "node",
    watch: false,
    testTimeout: 60_000,
    hookTimeout: 120_000,
    maxWorkers: 2, // this PC has 7.8 GB RAM (CLAUDE.md); the suite is CPU-light
  },
});
