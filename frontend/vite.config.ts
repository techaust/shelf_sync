import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The built app runs under the backend's CSP unchanged (docs/runs/m1a.2-security.md item 6):
//   default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; ...
// So the build must emit files only: no data: URLs for fonts or images (assetsInlineLimit 0), no inline scripts.
// There is no dev-server setup on purpose: the page is checked as the backend serves frontend/dist, so the CSP,
// the Host check and the sign-in are the real ones (no setting loosens a check, not even in development).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    sourcemap: false,
    // Edge and Chrome (the browsers ShelfSync opens) support <link rel="modulepreload">; no polyfill needed.
    modulePreload: { polyfill: false },
    target: "es2023",
  },
});
