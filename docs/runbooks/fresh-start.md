# Runbook: carry on after formatting the PC (fresh start)

The owner keeps no backups of their own (owner, 2026-11-03, [11](../11-decisions.md)). Everything needed to carry on is on GitHub (`techaust/shelf_sync`: the code, the record, the memory notes in [docs/memory/](../memory/README.md)) or on claude.ai (the plan and mockup pages, the `shelf_sync` cloud environment). Secrets are never on GitHub, so new keys are made when they're next needed.

Used for real on 2026-11-04, with the folder layout below (the owner's, from that day; [11](../11-decisions.md)).

## The folders
| What | Where |
|---|---|
| ShelfSync (this repo) | `D:\Business\2. GPL Projects\3. Other Assets\Applications\shelf_sync` |
| NSIS 3.13 (build tool, beside the repo) | `D:\Business\2. GPL Projects\3. Other Assets\Applications\tools\nsis-3.13` |
| OmniSync (read-only reference, CLAUDE.md rule 4) | `D:\Business\2. GPL Projects\3. Other Assets\Applications\Omni_Sync` |
| techaust_platform (read-only reference, rule 5) | `D:\Business\1. Parent Project\TecHaust Technologies\Application\techaust_platform` |

Claude finds its memory notes by the repo's full path (`tools/memory-sync.sh`), so a new path is fine as long as the project's own paths are updated in the same PR.

## Before you format
Nothing to do. If you work more days before formatting, say **"end the day"** on the last one: it saves the record and the memory notes.

## After you format: your part (about 15 minutes)
1. **Git for Windows:** in Edge, open **git-scm.com**, click **Download for Windows**, run the installer and click **Next** on every page (the defaults are fine). Claude Code on Windows needs it.
2. **The Claude desktop app:** install it from **claude.ai/download** and sign in with your Team account (`admin@techaust.com`).
3. **Python 3.15.2, installed by you, not by Claude:** anything Claude starts runs inside the Claude app's package, which hides new `AppData\Local` folders from the rest of Windows (04-A V36), so a Python that Claude installs isn't there for the checks you run in your own PowerShell.
   1. In Edge, open `https://www.python.org/downloads/release/python-3152/`, scroll to **Files** and click **Windows installer (64-bit)** (`python-3.15.2-amd64.exe`, 35.9 MB).
   2. Ask Claude to check its SHA-256 before you run it: python.org's page gives `06e225a228191b0f4d1dcf6905fbb21bf9f6970d13a2ec63137ab9bee76f15aa`.
   3. Double-click it in **Downloads**, tick **Add python.exe to PATH**, click **Install Now**, then **Close**.
4. **The folders:** make `D:\Business\2. GPL Projects\3. Other Assets\Applications` and `D:\Business\1. Parent Project\TecHaust Technologies\Application` in File Explorer (only the folders that don't exist yet). If you already have a downloaded copy of `shelf_sync` there (GitHub's **Download ZIP**), that's fine: Claude turns it into a clone.
5. In the Claude app, open the **Code** tab, start a new session in the `shelf_sync` folder (or in `Applications` if it doesn't exist yet) on **Opus 5.5, high**, and type:

   > start the day. I have formatted my PC; set up the project from docs/runbooks/fresh-start.md

6. Claude asks you **one yes** for the tools it installs, and asks you to **sign in to GitHub** in the browser if `gh` isn't signed in (you type the code it shows). It never sees your password.

## Claude's part
Follow CLAUDE.md's rules from the copy on GitHub. Check every download link and version before using it; never guess one.
1. **One question, one yes** (rule 8) for the tools Claude installs, at the versions in [04 §2.1](../04-architecture.md) ("Local tools"): uv 0.12.19 (Astral's GitHub release `uv-x86_64-pc-windows-msvc.zip`, checked against its `.sha256`, unpacked into `C:\Users\<user>\.local\bin`, which is added to the user PATH) and NSIS 3.13 (below). Neither writes under `AppData`, so V36 doesn't hide them. Node.js and the GitHub CLI: use what's installed if it's the same major version (Node 24) and say so; install only with the owner's yes. Python is the owner's (step 3 above): check the installer's SHA-256 in `Downloads` against python.org's release page before they run it.
2. **GitHub sign-in:** `gh auth status`; if not signed in, `gh auth login --web` as the `techaust` account and the owner enters the code in the browser.
3. **The repos:**
   - `shelf_sync`: clone `https://github.com/techaust/shelf_sync.git` into the path above. If a downloaded copy is already there, make it a clone without touching its files: `git init -b main`, `git remote add origin https://github.com/techaust/shelf_sync.git`, `git fetch origin`, `git reset origin/main` (keeps the files), `git branch -u origin/main`; then `git status` must show nothing changed (on 2026-11-04 it matched `main` exactly).
   - `techaust_platform`: clone `https://github.com/techaust/techaust_platform.git` into the path above if it isn't there (read-only reference).
4. **In `shelf_sync`:** `git config user.name "TecHaust Technologies"`, `git config user.email admin@techaust.com`, `git config core.hooksPath .githooks` (the pre-push guard), `git config core.longpaths true`.
5. **NSIS 3.13:** download the portable `nsis-3.13.zip` (`https://sourceforge.net/projects/nsis/files/NSIS%203/3.13/nsis-3.13.zip/download`), check its SHA-256 against the pin in [04 §2.1](../04-architecture.md), and unzip it into `…\Applications\tools\` (it makes `nsis-3.13\`). `makensis.exe -VERSION` prints `v3.13`.
6. **Plugins:** compare the account's plugins with [09 §2](../09-tooling.md). Add back any that are missing only with the owner's yes. The project's own `.claude/settings.json` turns off the plugins and connectors ShelfSync doesn't use. The per-project MCP list doesn't travel with the repo: in this project's entry of `~/.claude.json` set `"disabledMcpServers": ["supabase", "upstash", "aws-mcp", "plugin:sentry:sentry", "plugin:supabase:supabase", "plugin:upstash:upstash", "scheduled-tasks", "claude.ai Claude Docs"]` (back the file up first), then check `claude mcp list` shows them "Disabled for this project".
7. **Carry on with "start the day":** its step 0 installs the packages (`uv sync --locked`, `npm ci`) and restores the memory notes (`bash tools/memory-sync.sh restore`).
8. **If the folders moved:** replace every old path in the repo (CLAUDE.md, `.claude/settings.json`'s read blocks, the runbooks, 04 §2.1, `brand/draft/*.mjs`) in one PR, and add a row to 11.

## What doesn't come back, and what replaces it
| Lost | What happens |
|---|---|
| **Keys** in Windows Credential Manager (store Shop Manager keys, AWS keys) | Made new when the next task needs them ([keys-and-policies.md](keys-and-policies.md)); Claude then gives the steps to delete the old ones in each store and in AWS ([key-rotation.md](key-rotation.md)) |
| **OmniSync** (never on GitHub) | Let go on 2026-11-03; the owner put the folder back on 2026-11-04 (above), without its `venv` or its keys, so [research-scripts.md](research-scripts.md) still can't run. ShelfSync doesn't need it; the audit's evidence ([01-B](../01-audit-appendix/B-omnisync-evidence.md)) stays as recorded |
| ShelfSync's local data (test settings, test database) | Starts empty; nothing live used it |
| Old chat history | Not needed: the record and the memory notes carry on |
| The leftover folders in `.claude\worktrees\` | Gone with the format |
| The release signing key | None existed on 2026-11-03, so nothing is lost |

**Windows security:** a freshly installed Windows may start with Smart App Control in Evaluation mode; before the format it was **Off** ([09 §1](../09-tooling.md)), and on 2026-11-04 it read **Off** again (`VerifiedAndReputablePolicyState` 0). That's your decision, and Claude never changes it (CLAUDE.md rule 12).
