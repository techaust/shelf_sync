# Runbook: carry on after formatting the PC (fresh start)

The owner keeps no backups of their own (owner, 2026-11-03, [11](../11-decisions.md)). Everything needed to carry on is on GitHub (`techaust/shelf_sync`: the code, the record, the memory notes in [docs/memory/](../memory/README.md)) or on claude.ai (the plan and mockup pages, the `shelf_sync` cloud environment). Secrets are never on GitHub, so new keys are made when they're next needed.

## Before you format
Nothing to do. On 2026-11-03 everything was checked and is on GitHub. If you work more days before formatting, say **"end the day"** on the last one: it saves the record and the memory notes.

## After you format: your part (about 10 minutes)
1. **Git for Windows:** in Edge, open **git-scm.com**, click **Download for Windows**, run the installer and click **Next** on every page (the defaults are fine). Claude Code on Windows needs it.
2. **The Claude desktop app:** install it from **claude.ai/download** and sign in with your Team account (`admin@techaust.com`).
3. **The folder:** in File Explorer, make the folder `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE` (only the folders that don't exist yet). Use **exactly** this path: the project's commands use it, and Claude finds its memory by it.
4. In the Claude app, open the **Code** tab, start a new session in that `SOFTWARE` folder on **Opus 5.5, high**, and type:

   > Fresh start: set up shelf_sync from https://github.com/techaust/shelf_sync/blob/main/docs/runbooks/fresh-start.md

5. Claude will ask you **one yes** for the tools it installs, and ask you to **sign in to GitHub** in the browser (you type the code it shows). It never sees your password.
6. When Claude says it's done, start a **new** session in the `shelf_sync` folder and say **"start the day"**.

## Claude's part (in the `SOFTWARE` session)
Follow CLAUDE.md's rules from the copy on GitHub. Check every download link and version before using it; never guess one.
1. **One question, one yes** (rule 8) for the tools, at the versions in [04 §2.1](../04-architecture.md) ("Local tools"): Python 3.14.8 (python.org's per-user Windows installer, 64-bit), Node.js 24.19.0, uv 0.12.19, GitHub CLI. Check each download against its published SHA-256 where one is published.
2. **GitHub sign-in:** `gh auth login --web` as the `techaust` account; the owner enters the code in the browser.
3. **Clone** into the exact paths:
   - `https://github.com/techaust/shelf_sync.git` → `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync`
   - `https://github.com/techaust/techaust_platform.git` → `D:\BUSINESS\1. PARENT PROJECT\TECHAUST TECHNOLOGIES\WEBSITE\techaust_platform` (read-only reference, CLAUDE.md rule 5)
4. **In `shelf_sync`:** `git config user.name "TecHaust Technologies"`, `git config user.email admin@techaust.com`, `git config core.hooksPath .githooks` (the pre-push guard).
5. **NSIS 3.13:** download the portable `nsis-3.13.zip`, check its SHA-256 against the pin in [04 §2.1](../04-architecture.md), and unzip it to `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\tools\nsis-3.13\`.
6. **Plugins:** compare the account's plugins with [09 §2](../09-tooling.md). Add back any that are missing only with the owner's yes. The project's own `.claude/settings.json` (cloned) turns off the ones ShelfSync doesn't use.
7. **Hand over:** tell the owner to open a new session in the `shelf_sync` folder and say "start the day". That session's step 0 installs the packages (`uv sync --locked`, `npm ci`) and restores the memory notes (`bash tools/memory-sync.sh restore`).

## What doesn't come back, and what replaces it
| Lost | What happens |
|---|---|
| **Keys** in Windows Credential Manager (store Shop Manager keys, AWS keys) | Made new when the next task needs them ([keys-and-policies.md](keys-and-policies.md)); Claude then gives the steps to delete the old ones in each store and in AWS ([key-rotation.md](key-rotation.md)) |
| **OmniSync** (never on GitHub; the owner let it go, 2026-11-03) | Not needed by ShelfSync. [research-scripts.md](research-scripts.md) can't run any more; the audit's evidence ([01-B](../01-audit-appendix/B-omnisync-evidence.md)) stays as recorded |
| ShelfSync's local data (test settings, test database) | Starts empty; nothing live used it |
| Old chat history | Not needed: the record and the memory notes carry on |
| The leftover folders in `.claude\worktrees\` | Gone with the format |
| The release signing key | None existed on 2026-11-03, so nothing is lost |

**Windows security:** a freshly installed Windows may start with Smart App Control in Evaluation mode; before the format it was **Off** ([09 §1](../09-tooling.md)). That's your decision, and Claude never changes it (CLAUDE.md rule 12).
