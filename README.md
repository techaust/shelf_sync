# ShelfSync

**ShelfSync by TecHaust.** A localhost-only Windows app, for the owner of the GPLFamily and PluginWay stores, that takes vendor ZIPs (WordPress themes and plugins), works out which product each belongs to, scans it with Windows Defender, uploads one file to S3, and updates the download on every WooCommerce store. No AI, no silent guesses, and no paid tools. The one exception is under a cent of AWS request charges for the one-off calibration ([plan §11](docs/02-plan.md)).

**Status:** documentation phase; no code yet ([docs/10-status.md](docs/10-status.md)). **Start here:** [docs/02-plan.md](docs/02-plan.md).

## Installing (from M1b)
1. Download `ShelfSync-Setup.exe` from the `shelf_sync` repo's Releases page (signed in to GitHub).
2. Open it. Windows SmartScreen will say "Windows protected your PC", because the installer isn't code-signed (a paid certificate would remove this; not used). Click **More info → Run anyway**. A screenshot is added here at M1b.
3. It installs for your Windows user only (no admin), adds a desktop icon, and opens the first-run wizard.

Updates then install from inside the app, with no warning.

## Documentation
| Doc | What's in it |
|---|---|
| [01 Audit](docs/01-audit.md) | Why OmniSync is replaced, with evidence ([A: store data](docs/01-audit-appendix/A-store-data-checks.md), [B: OmniSync code and log](docs/01-audit-appendix/B-omnisync-evidence.md)) |
| [02 Plan](docs/02-plan.md) | The design (Draft 4) |
| [03 PRD](docs/03-prd.md) | Requirements, acceptance tests and milestone, by ID |
| [04 Architecture](docs/04-architecture.md) | Stack, folders, data model, API, jobs, packaging ([A: what's verified](docs/04-architecture-appendix/A-stack-verification.md)) |
| [05 Design system](docs/05-design-system.md) | The Patina tokens, the ShelfSync logo brief, components, screens |
| [06 Security](docs/06-security.md) | Threats, defences, residual risks |
| [07 Testing](docs/07-testing.md) | Test layers, calibration, canary, trust ramp |
| [08 Roadmap](docs/08-roadmap.md) | Phases, milestones M1a–M7, approval gates |
| [09 Tooling](docs/09-tooling.md) | This PC, skills, plugins, MCP servers, agents, and when each is used |
| [10 Status](docs/10-status.md) | Where things stand |
| [11 Decisions](docs/11-decisions.md) | Every decision, one row each |
| [12 Models and usage](docs/12-models-and-usage.md) | Which model and effort each kind of work uses |
| [13 Content](docs/13-content.md) | Wording in the app, and the glossary |
| [ADRs](docs/adr/) · [Runbooks](docs/runbooks/README.md) · [Run files](docs/runs/README.md) | Decision records, procedures, task records |

Rules for working in this project: [CLAUDE.md](CLAUDE.md).
