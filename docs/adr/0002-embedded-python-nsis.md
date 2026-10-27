# ADR 0002: Embedded signed Python + NSIS installer, no PyInstaller, no code-signing certificate

- **Status:** Accepted (owner, with plan Draft 3, 2026-10-25). **Changed 2026-10-25 (owner):** NSIS replaces Inno Setup, and releases are signed with an offline key
- **Date:** 2026-10-25

## Context
The owner wants one `Setup.exe` for a fresh PC and pays for no tools. PyInstaller-style programs are unsigned and often flagged by antivirus, and a code-signing certificate costs money. Inno Setup 6.5+ asks commercial users to buy a licence (not legally required; [04-A V16](../04-architecture-appendix/A-stack-verification.md)). The owner chose a tool with no such request.

## Decision
- Ship the official **Python 3.14 Windows embeddable package (3.12 until 2026-10-27; see [ADR 0001](0001-python-fastapi-sqlite-react.md)'s amendment)** (its executables are Authenticode-signed by the Python Software Foundation, V12), with `python314._pth` edited to enable site-packages (V11), and the app's code as plain Python and web files.
- Build a **per-user** installer with **NSIS** (zlib licence, free, V15): no admin prompt.
- **Stable paths:** a `current` directory junction points at the active version, so shortcuts and the Start-with-Windows value never change ([04 §8](../04-architecture.md)).
- **In-app updates** download through the app, verify the **Ed25519 signature made with the owner's offline key** and the checksums ([06 §6](../06-security.md)), install side by side, and switch back automatically on a failed health check.

## Consequences
- **SmartScreen** warns each time a newly downloaded, unsigned `Setup.exe` is opened ("More info → Run anyway"; the README's install section shows it from M1b). In-app updates aren't downloaded by the browser, so they show no warning (V17).
- **Smart App Control**, if on, can block the unsigned installer and unsigned DLLs with no override (V18). The owner checks the state before M1b. Removing both warnings needs a paid certificate: **optional, not used**.
- The shortcut needs an AppUserModelID for toast notifications; how NSIS sets it is verified at M1b.
- Uninstall removes every version folder the updater added, not only what NSIS installed.
- Some wheels contain DLLs their projects don't sign; the M1b test runs on a clean account with Defender on and records the Smart App Control state.
