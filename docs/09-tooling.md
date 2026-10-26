# 09: Tooling (skills, plugins, MCP servers, agents, and when each is used)

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**); corrected after the 2026-10-25 independent review |
| **Date** | 2026-10-25 |
| **Rule** | CLAUDE.md hard rule 8: **every tool that fits a task is used automatically**, without the owner asking (§3). Using a tool never bypasses the approval rules: anything that writes to the live stores, S3 or GitHub, or installs a plugin, MCP server or package, still needs the owner's yes for that action. Models and effort: [12](12-models-and-usage.md) |

## 1. This PC (checked 2026-10-25)

| Item | Found | Needed | Action |
|---|---|---|---|
| Windows | 11 Home Single Language | 10/11 | Home has no Windows Sandbox: the clean-account test uses a second local account ([07 §7](07-testing.md)) |
| CPU / RAM | Intel i3-1115G4, 2 cores / 4 threads; 7.8 GB | — | At most two agents at once; heavy commands queued ([12 §4](12-models-and-usage.md)); the NFR-3 targets are set for this PC |
| Free disk | C: 77.5 GB, D: 256.5 GB | ~5 GB for the test stack and the calibration cache | OK |
| Python | 3.12.10 | 3.12 | OK |
| Node / npm | 24.19.0 / 11.17.0 | For the UI and the hook scripts | OK |
| git / GitHub CLI | 2.55.0 / 2.101.0, signed in as `techaust` | — | Repo creation waits for the owner's yes (M1a) |
| NSIS | not installed | Release builds (CI); locally only for M1b testing | Installed at M1b with the owner's yes |
| LocalWP | not checked | Test stack (M2) | Installed at M2 with the owner's yes |
| moto | not installed | Test stack (M2) | A pip package in the dev dependencies |
| Smart App Control state | **Off** (owner, 2026-10-25) | Re-recorded on the clean account at M1b | Owner checks (runbook `clean-account.md`); Claude never changes it |

## 2. Found in this environment (2026-10-26, Team plan)
- **Skills on the account:** the built-in set plus Anthropic document skills (docs, docx, xlsx, pptx, pdf, google-workspace, morning, import-memory); a skills search for this project's topics found no custom or org skills.
- **Plugins:** GitHub, Context7, Playwright, frontend-design, security-guidance (the Security review plugin), AWS core, Cloudflare, Sentry, Supabase, Upstash. Expo is no longer enabled on the account. User-level MCP servers: `aws-mcp`, `supabase`, `upstash`. The Team plan adds a Claude Docs connector.
- **Turned off for this project only** in `.claude/settings.json` (§5 says why): Cloudflare and Playwright plugins (`enabledPlugins`); the tools of Supabase, Upstash, Cloudflare, Sentry, Playwright, Claude in Chrome and Claude Docs (`permissions.deny`); every skill of those plugins, the AWS-core skills other than `aws-sdk-python-usage`, `aws-iam` and `signing-in-to-aws`, `claude-api`, and the document skills other than `pdf` (`skillOverrides`). The account plugins stay installed because turning off account plugins per project would also drop security-guidance.
- **Context7 coverage** (checked): WooCommerce REST API (`/woocommerce/woocommerce-rest-api-docs`), pystray (`/moses-palmer/pystray`) are indexed; **NSIS is not** (its official docs at nsis.sourceforge.io are used instead).
- **Not installed (optional, free):** Design (Anthropic), A11y Enforcer (community).

## 3. Automatic use: task → tools
Before starting a task, the lead (and each agent) loads every skill in its row and says which were loaded; one that doesn't apply is skipped with the reason.

| Task | Load / use |
|---|---|
| Any logo, brand asset, mockup, screen or UI component | `frontend-design`; `dataviz` for any chart, KPI tile or report; built-in browser (`built-in-browser` skill) for screenshots and visual checks |
| Writing code that uses a library (any layer) | Context7 for that library's current docs before writing; the official site where Context7 has none (NSIS) |
| S3 code: range reads, uploads, checksums, the moto endpoint | `aws-sdk-python-usage` |
| IAM policies and the AWS guide | `aws-iam` |
| Inspecting the real bucket (calibration prep) | AWS MCP `run_script`, read-only, after the owner's go-ahead |
| Anything in `secure/`, `inspect/`, `apply/`, `update/`, `platform/`, the API middleware or the installer | `security-review` (by the `reviewer`) |
| Every finished task | `code-review` (by the `reviewer`); `simplify` at the end of each milestone |
| Checking a change in the running app | `run` |
| A page, report or plan for the owner to view or share | `artifact-design` |
| Repo, PRs, CI, releases | GitHub MCP / `gh` (writes only with the owner's yes) |
| Start or end of a working day | `start-session`, `end-session` |
| "Where is X" in the code | the `code-finder` agent |
| Running a test suite | the `test-runner` agent |

## 4. The tools in use

| # | Tool | Kind | What it does here | Limits |
|---|---|---|---|---|
| T1 | **GitHub** plugin + `gh` | MCP + CLI | Creates `shelf_sync` (M1a), PRs, Actions results, Releases, Dependabot | Repo creation, pushes, settings and releases: owner's yes per action |
| T2 | **Context7** | MCP | Current library docs (§2) | Read-only public docs |
| T3 | **aws-sdk-python-usage** | Skill | boto3 patterns | Local code |
| T4 | **aws-iam** | Skill | The two least-privilege policies ([06 §5](06-security.md)) | Writes no AWS settings |
| T5 | **AWS MCP** (`run_script`) | MCP | Read-only bucket checks | Each use with the owner's go-ahead; never writes |
| T6 | **Built-in browser** pane | Built in | Screenshots and visual checks (owner declined headless Chrome) | Local pages only |
| T7 | **frontend-design**, **dataviz**, **artifact-design** | Skills | Design work, charts, owner-facing pages | No external access |
| T8 | **code-review**, **security-review**, **simplify**, **run** | Skills | Reviews, clean-up, running the app | Local only |
| T9 | **Security review** plugin | Plugin (hooks) | Warns on risky edits as they happen | Already on |
| T10 | **Agents** (`.claude/agents/`): analyst, builder, designer, reviewer, code-finder, test-runner, doc-clerk | Claude Code subagents | [12 §3](12-models-and-usage.md) | Fixed tool lists; no connectors |
| T11 | **model-guard hook**, **model-audit**, **heavy.sh**, **watch.sh** | Repo scripts (`tools/`) | Keep to the three models; audit runs; queue heavy commands (shared lock with techaust_platform); stall and memory alarms | Local only |
| T12 | **start-session** / **end-session** | Project skills | "start the day" / "end the day" | Local |

## 5. Not used for this project
| Tool | Why not |
|---|---|
| Supabase, Upstash, Expo, Cloudflare, most AWS-core skills | Not part of the stack (local SQLite plus one S3 bucket) |
| Sentry | Localhost, single user, local logs; a SaaS doesn't fit NFR-5 or the $0 rule |
| `claude-api` | ShelfSync uses no AI |
| **Claude in Chrome** | Uses the owner's real, signed-in Chrome; the built-in browser is isolated and enough |
| Playwright **MCP** browser | May run headless Chrome, which the owner declined. Blocked in `.claude/settings.json`; using it needs the owner's yes and the block lifted. (The Playwright **test runner** is used in CI; that's a package, not this tool) |
| Axe Accessibility (Deque) MCP | Its workflow may need a paid Deque account; free axe-core in CI covers it |
| Community workflow and audit plugins (Clawness, Agent Protocols, beads-superpowers, securitymaxxing) | Broad hooks on every prompt; overlap with the built-in skills and our agents |
| Built-in Explore, Plan, general-purpose agents | Refused by the hook; `code-finder` instead. Exception: helpers the review skills start on their own ([12 §3](12-models-and-usage.md)) |
| Claude Docs connector; docs, docx, xlsx, pptx, google-workspace, morning, import-memory skills | The record is Markdown in `docs/`; owner-facing pages use `artifact-design`. `pdf` stays on for reading vendor documentation |

## 6. Optional (free; install only if the owner wants)
- **Design** (Anthropic): `accessibility-review` and `design-critique` for the Phase 3 screenshots; its bundled MCP servers stay unconnected.
- **A11y Enforcer** (community, skill only): contrast and focus checks during UI work.

## 7. Packages (added with the owner's yes at the milestone that needs them)
- **Python, run time:** fastapi, uvicorn, python-multipart, httpx, boto3, keyring, cryptography, pystray, Pillow, windows-toasts.
- **Python, dev:** uv (hash-locked dependencies), ruff, mypy, pytest, pytest-cov, pytest-benchmark, hypothesis, respx, moto[server], bandit, pip-audit.
- **UI, run time:** react, react-dom, react-router, @tanstack/react-query, @tanstack/react-virtual, @radix-ui/* (incl. Toast), lucide-react.
- **UI, dev:** vite, typescript, tailwindcss, @biomejs/biome, vitest, @playwright/test, @axe-core/playwright, openapi-typescript.
- **Build:** NSIS; the Python 3.12 embeddable package (SHA-256 pinned).
- **Brand (dev-only, P3.3):** chosen by the designer with the owner's yes; TecHaust's pipeline (sharp for rasters, a font-outline library) is the reference.
- Exact pins are recorded in [04 §2](04-architecture.md) at M1a.
