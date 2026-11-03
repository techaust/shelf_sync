---
name: claude-app-msix-virtualization
description: "Anything started from the Claude desktop app (even unsandboxed) runs inside its MSIX package, so %LOCALAPPDATA% writes land in a private copy Explorer can't see"
metadata:
  node_type: memory
  type: project
  originSessionId: f4026695-dced-42b2-8f93-078aa020cc52
  modified: 2026-10-27T09:20:57.624Z
---

The Claude desktop app is an MSIX package (`Claude_pzs8sxrjxfjjc`). Every process it starts — Bash, PowerShell, the terminal panel, and `dangerouslyDisableSandbox` too — inherits the package context. New folders it creates under `%LOCALAPPDATA%` are redirected to `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\…`. Those processes see the merged view; Explorer and anything else outside the package don't. Found 2026-10-27 in the M1a exit test: View logs showed "Location is not available" for `%LOCALAPPDATA%\ShelfSync\logs`.

**Why:** a ShelfSync started by the lead or an agent isn't a real-world run, so results from it can mislead. The HKCU Run key may be virtualized the same way (not checked).

**How to apply:** for any check where Windows itself has to see the app's files or registry (Explorer, Start with Windows, the installer), the owner starts ShelfSync from a normal PowerShell window or the Start menu, outside Claude. Say so in the run files and status. Related: [[owner-profile]]
