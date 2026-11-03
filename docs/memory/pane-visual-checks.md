---
name: pane-visual-checks
description: "How to compare two builds' colours in the built-in pane reliably; a hidden pane freezes CSS transitions and slows timers"
metadata:
  node_type: memory
  type: project
  originSessionId: 4623b6b4-245e-4d34-8d4e-5dcbed53d755
  modified: 2026-11-02T02:34:07.971Z
---

Learned 2026-11-02 checking T4/T5 against `main` in the built-in browser pane (CLAUDE.md rule 10):
- Serve each build with the real `create_app` and in-memory stores (`MemorySecretStore`, the app's defaults) on its own port, minting a fresh single-use `#t=` ticket every 45 s; all ports share one cookie, so sign in again after switching.
- **A hidden pane (the owner away, window covered) renders no frames:** CSS transitions freeze at their start colours, timers slow to about one a minute, lazy pages may not have loaded. Inject `*{transition:none!important;animation:none!important}`, wait until the element count is stable, run captures in the background and collect later.
- Showing the pane re-syncs its colour scheme to the app's theme: set `colorScheme` explicitly before each run. Keep the pointer off the page (hover and tooltips change the capture). Border widths change with the device pixel ratio: leave widths out.
- Late in a long session the pane's screenshots may come back cropped; read the page text instead and say so.

**Why:** a first comparison showed false differences from all of these before any real one.
**How to apply:** compare computed colours per element (hash per page and theme), in light, Dark by setting, dark from Windows, and Light over a dark Windows. Related: [[claude-app-msix-virtualization]], [[audit-to-ten]].
