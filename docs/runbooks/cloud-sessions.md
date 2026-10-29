# Runbook: cloud sessions

A cloud session is a Claude Code session that runs on a virtual machine Anthropic hosts (Ubuntu 24.04, about 4 processors and 16 GB of memory), started from the Desktop app, claude.ai/code or the phone. It counts toward the same 5-hour limit, and there's no separate charge. It works on a fresh copy of the GitHub repo, so it only sees what is pushed. Model, effort, agent limits and the budget gate are in [12 §4–§5](../12-models-and-usage.md).

The button names below are from Anthropic's cloud-session documentation (checked 2026-10-29); if a screen looks different, the names may have moved slightly.

## 1. What may run in a cloud session

| Runs there | Never there (this PC only) |
|---|---|
| Backend code and its tests (`uv run pytest`), ruff, mypy, bandit, pip-audit | Visual checks and screenshots (the built-in browser pane, CLAUDE.md rule 10): the designer's self-check and the reviewer's visual review |
| Screen code and its unit tests (`npm test`, Vitest), Biome, typecheck, `npm run build` | The Windows checks (`pytest -m windows`, `-m defender`) |
| Docs and the record | The release build (`packaging/release-build.ps1`) and so any change to `packaging/`, `release.yml`, the launcher or `paths.py` |
| | Anything that touches the live stores or the S3 bucket |

## 2. Set it up once

### 2.1 Let cloud sessions reach the repo
1. Open https://github.com/apps/claude in your browser and click **Install** (or **Configure** if it's already installed).
2. Pick the **techaust** account.
3. Choose **Only select repositories**, pick **shelf_sync**, and click **Install** (or **Save**).

This also lets the app's **Auto-fix** watch ShelfSync's pull requests.

### 2.2 Turn on the GitHub connector (Team plan, once)
On a Team plan, cloud sessions reach GitHub only after an Owner turns this on.
1. Open https://claude.ai/admin-settings/connectors.
2. Switch **GitHub** on (skip if it's on already).

### 2.3 Make the `shelf_sync` environment
On the Team plan the owner makes it as an Owner, on the **Cloud environments** admin page (2026-10-29: the screens differ from Anthropic's docs).
1. Open https://claude.ai/admin-settings and click **Cloud environments**, then add an environment.
2. **Name:** `shelf_sync`.
3. **Network access:** **Limited** (the screen offers None, Limited and Full). In **Allowed domains**, one per line, exactly the sites the setup and the lock files need (checked against `uv.lock` and `frontend/package-lock.json`, 2026-10-29):
   ```text
   github.com
   release-assets.githubusercontent.com
   objects.githubusercontent.com
   nodejs.org
   pypi.org
   files.pythonhosted.org
   registry.npmjs.org
   ```
   Pushes, pull requests and `gh` go through Anthropic's GitHub proxy, which this list doesn't affect. If a session fails because a site is blocked, its error names the site: add that line, nothing broader.
4. **Environment variables:** leave empty. The repo's `.claude/settings.json` already sets what's needed. Never put a key or password here: every member of the organization can read them.
5. **Setup script:** **Choose file**, and pick
   `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync\tools\cloud\setup.sh`
   (or paste its whole text if there's only a text box).
6. Save it.

### 2.4 Connect GitHub to your Claude account
1. Open https://claude.ai/code. If it asks you to connect GitHub, follow it and click **Authorize** on GitHub's page.
2. If it shows **Create your first cloud environment**, keep the defaults and click **Create & finish** (a plain **Default** environment; ShelfSync sessions use `shelf_sync`).

The setup script installs the same Python 3.14.8, Node 24.19.0 and uv 0.12.19 that CI uses. Each download is checked against a fingerprint written in the script. If any fingerprint doesn't match, the session doesn't start, which is the safe outcome; tell the lead. The result is kept for about 7 days, so later sessions start quickly.

When `tools/cloud/setup.sh` changes in the repo, load it again (2.3 step 5): the environment keeps its own copy.

## 3. Start a cloud session
1. In the **Code** tab, start a new session, pick **Cloud** and the **shelf_sync** environment, and the repo **techaust/shelf_sync** on branch **main** (or the branch the lead names).
2. Pick **Opus 5.5** in the model menu. If the session doesn't say its effort is high, type `/effort high`.
3. Type **start the day** (or **continue**).
4. If there's no usage tool in that session, the lead asks you for the 5-hour %: type it as a number, for example `42 %`. Without a reading that day, nothing new starts there.

What the session does by itself:
- `tools/cloud/session-start.sh` puts the pinned tools first, sets the commit identity and the pre-push guard, and installs the locked packages. It prints one line per tool and a **PROBLEM** line for anything wrong.
- When a task is done, it pushes its branch and opens the PR, and GitHub merges it once the required checks pass (CLAUDE.md, Git workflow).

## 4. What's been checked
- **2026-10-29, the first cloud session:** the setup script and the start-up script ran clean: Python 3.14.8, Node 24.19.0 and uv 0.12.19 first on PATH, `uv sync --locked` and `npm ci` passed, no PROBLEM lines. The Limited network with the seven sites was enough.
- **2026-10-29, the first cloud PR:** m2.6's PR (#33) was pushed from the cloud session and merged itself on green.
- **Not yet:** the pre-push guard refusing a push in a cloud session.
