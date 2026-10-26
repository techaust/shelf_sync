# 05: Design system (ShelfSync by TecHaust)

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**); corrected after the 2026-10-25 independent review. §1.2–1.4 updated 2026-10-26 with the approved S-cut logo (P3.1–P3.2, audited in [14](14-brand-audit.md)). Phase 3 approved 2026-10-26: assets in `brand/`, mockup and screenshots in the appendix (§8) |
| **Date** | 2026-10-25 |
| **Decision** | [ADR 0006](adr/0006-techaust-product-brand.md): ShelfSync is a TecHaust product on the **Patina** identity, with a new ShelfSync logo and asset set; store colours are small identifiers only |
| **Source** | TecHaust's `packages/ui/tokens/tokens.json` and `docs/06-design-system.md` in `techaust_platform` (read-only reference) |
| **Implements** | [03 PRD](03-prd.md) UI-*, NFR-1, NFR-2 |

> **One source of truth.** All tokens live in `brand/tokens.json`, copied from TecHaust's tokens (identity "Patina", 2026-10-06) and kept in step with them. A build script generates the CSS custom properties and the Tailwind v4 `@theme` the UI uses. A colour or size is never typed by hand in a component. If TecHaust changes a token, ShelfSync takes the change in a reviewed commit.

---

## 1. Brand foundations

### 1.1 The idea
TecHaust's Patina, ink green and verdigris, means "systems built properly, then looked after for years". ShelfSync is exactly that kind of system: a careful shelf-keeper that keeps every store's product shelf in step. The app carries the TecHaust look so it reads as **"ShelfSync by TecHaust"**, while its own logo gives it a name of its own.

### 1.2 The ShelfSync logo: "S-cut" (approved 2026-10-26)
Of three concepts (Shelves, S-cut, One to many), the owner chose **S-cut**. It was refined and scored in [14](14-brand-audit.md) and approved on 2026-10-26 ([11](11-decisions.md)). The source is `brand/geometry.mjs`; `npm run build` in `brand/` regenerates every asset and `npm test` guards them (P3.3). The P3.2 refinement board is in `05-design-system-appendix/p3.2-logo-refine/`, and the asset review page is in `05-design-system-appendix/p3.3-brand-assets/`.

**The symbol:** an "S" built from two offset ink blocks, separated by one diagonal channel, using the same construction as the TecHaust TH mark.
- **Grid and strokes:** solid blocks on a 100-unit grid. Verticals are 19 units and horizontals 17.5 (7.9 % thinner). The spine's centre is at 48.5.
- **One device:** a single 45° channel, exactly one stroke wide (19 units measured square to the cut). The cut **always runs "/"**, the same way as TecHaust's mark.
- **Turned terminals:** both ends of the S carry a short spur (9 units) so it can't be read as a 5 at small sizes.
- **Colour:** ink, with **verdigris only on the cut piece**, the part of the spine the channel separates (about 11 % of the mark). It's never swapped, and the accent is verdigris-700 at every size. On dark backgrounds use mist + verdigris-300. The shape never depends on the colour: the channel separates the halves, so it reads as an S with the verdigris removed.
- **Never:** arrows, circles of arrows, clouds or boxes with a tick.

**Wordmark:** "ShelfSync" in **Archivo** (OFL), outlined (artwork, not live text), at weight 620 and width 116 %, tracking −6. The **f crossbar carries the 45° "/" cut**, one stroke wide, as TecHaust's T bar does. These letter pairs are optically re-spaced, measured as white area against "no" ([14 §2.4](14-brand-audit.md)): Sh −2, lf −2, yn −2, fS −3, Sy −3. Mixed case (Shelf + Sync) keeps both words readable.

**Endorsement:** "BY TECHAUST" in IBM Plex Mono caps, at 0.3 × the wordmark's cap height, with its cap line one stroke below the baseline. It appears in the installer, the About panel, the README and the GitHub social preview, and never in the app bar.

### 1.3 Lockups and rules
| Lockup | Use | Minimum |
|---|---|---|
| **Primary (horizontal)**: the symbol at 1.28 × the cap height, centred on the caps, with a two-stroke gap | App bar, installer, README | **119 px** wide (the symbol inside stays at 16 px or more) |
| Symbol | Tray icon, favicon, app icon, desktop shortcut | 16 px |
| Wordmark only | Where the symbol is already near | — |
| Endorsed | Primary + "by TecHaust": installer welcome page, About, social preview | 266 px wide (a 12 px endorsement) |
| Endorsed, **stacked** (installer only) | The NSIS welcome/finish side panel (164 px wide): the symbol above the wordmark, with "BY TECHAUST" at 12 px | Fits 164 px |
| Endorsed, **compact** (installer only) | The NSIS header image (150 × 57): the primary at its 119 px minimum, with "BY TECHAUST" at 12 px | Fits 150 px |

Clear space: one mark stroke on every side. Colour versions: full colour on light, on dark, and one colour (ink, white or black). **Never** stretch, rotate, outline, recolour outside the palette, add shadows or gradients, or set "ShelfSync" in a live font in place of the wordmark.

### 1.4 Deliverables (`brand/`, all generated from code)
The mark and the wordmark edits are defined as numbers in a geometry file, and a script regenerates every asset, so the brand changes only through a reviewed commit (as TecHaust's `geometry.ts`). Tests guard the geometry, contrast and file sizes.

**Pixel fitting:** at 64 px and below the symbol is pixel-fitted, so every edge lands on a whole pixel and both cuts stay 45° "/". It's fitted at 16, 20, 24, 32, 48 and 64 px, following TecHaust's `pixelMark` rule: v = round(0.19 · px), h = v below 40 px, channel run = round(v · √2). **The one exception (owner, 2026-10-26):** at 16 px the horizontals are 2 px against 3 px stems, so the openings next to the turned ends stay at least 2 px. **And one ICO exception (owner, 2026-10-26):** the 16 px frame of `shelfsync.ico` and `favicon.ico` holds the symbol fitted at 14 px inside a 1 px ink rim, so it keeps its edge on white (File Explorer, browser tabs).

| Asset | Files |
|---|---|
| Vector logos | 6 lockups (primary, symbol, wordmark, endorsed, endorsed stacked, endorsed compact) × 5 colour versions (colour, dark, ink, white, black) = 30 SVGs |
| Favicon | `favicon.svg` (pixel-fitted, switches colours in dark), `favicon.ico` (16/32/48) |
| **Tray icons** | Multi-size `.ico` (16, 20, 24, 32 px) for light and dark taskbars, in 3 states: **normal**; **paused**, two bars in the info colour; **needs attention**, a dot in the warning colour. Each badge is cut out of the mark's lower-right corner, below the spine, so the verdigris cut piece is never clipped. The two badges differ in shape, so status never relies on colour alone. The taskbar theme is read from `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\SystemUsesLightTheme` and re-read when Windows reports a theme change. pystray takes a Pillow image, so the right size is picked from the `.ico` for the screen's DPI (checked at M1) |
| App icon | `shelfsync.ico` (16–256 px) for the desktop shortcut, Start menu, toasts and `Setup.exe` |
| Installer art | NSIS Modern UI images with the endorsed lockup: the welcome/finish side panel (164 × 314 px) and the header image (150 × 57 px). How NSIS scales them on high-DPI screens is checked at M1 at 150 % and 200 % scaling; if it stretches them badly, the art is kept simple enough (flat colour, large mark) to survive it |
| GitHub | Repo social preview 1280 × 640; README header (light and dark) |

### 1.5 Personality → design principles (TecHaust's, applied to a tool)
| Principle | In ShelfSync |
|---|---|
| **Calm** | Few colours on screen; status colour only where something needs the owner; no constant motion, no glows |
| **Engineered** | One type family, exact alignment, the diagonal cut as the only decoration; tabular numbers for versions, counts and times |
| **Premium, not flashy** | Hairline borders, restrained shadows; verdigris used sparingly, never as large fills |
| **Honest** | Every automatic decision shows "Why?"; nothing pretends to be live when it isn't; sample data in mockups is labelled |

---

## 2. Colour

### 2.1 Palette (from TecHaust `tokens.json`, unchanged)
| Group | Tokens |
|---|---|
| **Ink** | `ink-950 #0D1613` · `ink-900 #14231F` (brand ink) · `ink-800 #15211D` · `ink-750 #111C18` · `ink-700 #1B2924` · `ink-600 #26352F` · `ink-500 #61796F` · `ink-400 #485752` · `ink-300 #9DB0A8` |
| **Verdigris** | `verdigris-900 #1F4A40` · `-800 #175548` · `-700 #1E6B5C` (brand) · `-500 #2E8B77` · `-300 #6CC4AE` (brand on dark) · `-200 #8AD4C1` · `-100 #D7ECE5` |
| **Stone** | `stone-50 #F6F7F5` (page) · `-100 #ECEFEB` · `-200 #E1E6E2` · `-300 #D3DBD6` · `-500 #75867F` (control borders) |
| **Other** | `mist #E4EBE7` (dark-theme text) · `white` · `black` |
| **Status** | success `#44700E` / `#A9D46B` · warning `#8F5B00` / `#E9B44C` · danger `#B3261E` / `#FF8A80` · info `#2B5797` / `#8DB4FF` (light / dark) |

### 2.2 Semantic tokens (what components use)
| Token | Light | Dark |
|---|---|---|
| `--color-bg` | `stone-50` | `ink-950` |
| `--color-surface` / `-alt` / `-raised` | `white` / `stone-100` / `white` + shadow | `ink-800` / `ink-750` / `ink-700` |
| `--color-fill-subtle` | `stone-200` | `ink-750` |
| `--color-text` / `-muted` | `ink-900` / `ink-400` | `mist` / `ink-300` |
| `--color-text-accent`, `--color-focus` | `verdigris-700` | `verdigris-300` |
| `--color-border` / `-control` | `stone-300` / `stone-500` | `ink-600` / `ink-500` |
| `--color-btn-primary-bg` / `-fg` / `-hover` | `verdigris-700` / `white` / `verdigris-800` | `verdigris-300` / `ink-950` / `verdigris-200` |
| `--color-link` / `--color-link-hover` | `ink-900` (underlined) / `verdigris-700` | `mist` (underlined) / `verdigris-300` |
| `--color-btn-secondary-fg` | `ink-900` | `mist` |
| `--color-accent-decor` | `verdigris-500` | `verdigris-300` |
| `--color-selection` | `verdigris-100` | `verdigris-900` |
| `--color-appbar-bg` / `-fg` / `-muted` (**ShelfSync additions**) | `ink-900` / `mist` / `ink-300` | `ink-750` / `mist` / `ink-300` |

**Contrast** (TecHaust's measured table, copied unchanged because the tokens are the same; ShelfSync's tokens test re-checks every pair at M1a):

| Pair | Light | Dark | Level |
|---|---|---|---|
| Text on page | 15.2 | 15.2 | AAA |
| Muted text on page / on alternate section | 7.1 / 6.6 | 8.1 / 7.7 | AAA on page |
| Accent text on page / alternate section | 5.9 / 5.5 | 8.9 / 8.4 | AA |
| Button label on primary button / on hover | 6.3 / 8.6 | 8.9 / 10.8 | AA |
| Control border on page / card (dark: also dialog 3.2) | 3.57 / 3.84 | 3.9 / 3.5 | AA non-text |
| Focus ring on page | 5.9 | 8.9 | AA non-text |
| Decorative verdigris on page | 3.9 | 8.9 | Large text and non-text only |
| Success / warning / danger / info on page | 5.47 / 5.3 / 6.1 / 6.7 | 10.8 / 9.7 / 8.1 / 8.9 | AA |

**The new app-bar pairs** (computed 2026-10-25): mist on the light bar (`ink-900`) **13.4:1**, on the dark bar (`ink-750`) **14.4:1**; muted `ink-300` 7.1:1 / 7.7:1; the focus ring (`verdigris-300` on the bar) 7.9:1 / 8.4:1. All AAA.

### 2.3 Store identifiers
Store colours never style the app. Each store is shown as a **shape + colour dot and its two-letter code in text**, so it is never told apart by colour alone, and PluginWay's teal can't be mistaken for the app's verdigris.

| Store | Shape | Light dot | Dark dot | Lowest contrast on any surface it can sit on (light / dark) |
|---|---|---|---|---|
| GPLFamily `GF` | circle | `#4d4d99` (brand primary) | `#a3a3e6` | 5.9:1 on `stone-200` / 4.2:1 on `verdigris-900` (selected row) |
| PluginWay `PW` | square | `#007b80` (a deeper teal chosen for contrast; PluginWay's `#009699` drops to 2.85:1 on `stone-200`) | `#3cc8cb` | 4.0:1 on `stone-200` / 4.9:1 on `verdigris-900` |
| A store added later | the next free shape (triangle, diamond) | owner-picked, checked ≥ 3:1 on every surface (white, stone-50/100/200, verdigris-100; ink-950/800/750/700, verdigris-900) | | |

Non-text marks need 3:1 (WCAG 1.4.11); every pair above passes on every surface.

Where it's used: store badges (neutral surface + dot + code), the per-store step chips in Upload, the tick per store in tables, the column header in Catalog. The code text always uses `--color-text`.

### 2.4 Bands and job states (always icon + label + colour)
| Meaning | Style | Icon (Lucide) |
|---|---|---|
| Certain / Applied / In step | success | `circle-check` |
| Likely | info | `circle-dot` |
| Unsure | warning | `circle-help` |
| No match | neutral (stone fill, ink text) | `search-x` |
| Held (downgrade, version conflict, changed outside) | danger outline + reason text | `shield-alert` |
| Threat found / Not scanned | danger / warning, with the threat name or reason | `shield-x` / `shield-question` |
| Partial | danger | `triangle-alert` |
| Running (inspect, scan, upload, write) | neutral, with a progress bar in the row; the `loader-circle` icon is used only inside buttons | — |
| Auto / You (who approved) | neutral with icon | `bot` / `user-check` |

Icon names are Lucide's current names, checked against the pinned `lucide-react` version at M1a.

---

## 3. Typography
Archivo + IBM Plex Mono, **self-hosted** woff2 (works offline, NFR-1), the same variable Archivo file as TecHaust.

| Token | Size / line-height | Weight | Family | Use |
|---|---|---|---|---|
| `text-display-2` | 36 px (fixed in the app) / 1.1 | 560 | Archivo Expanded | Page title |
| `text-h2` | 28 px / 1.15 | 560 | Archivo Expanded | Section title, big KPI numbers |
| `text-h3` | 24 px / 1.25 | 600 | Archivo | Card title (large) |
| `text-h4` | 20 px / 1.3 | 600 | Archivo | Card title |
| `text-body` | 16 px / 1.6 | 400 | Archivo | **App body**, forms |
| `text-sm` | 14 px / 1.45 | 400/500 | Archivo | Table cells, secondary UI |
| `text-caption` | 12 px / 1.4, letter-spacing 0.08em | 500 | Archivo | Table headers, eyebrows, small labels. **Minimum size.** |
| `text-code` | 14 px / 1.5 | 400 | IBM Plex Mono | File names, slugs, MD5, keys, times |

Rules: `tabular-nums` on versions, counts, IDs and times; file names and slugs in Plex Mono; **arrows are always the Lucide `arrow-right` icon** between two values, never a text arrow (Archivo has no → glyph). Wording rules are in [13](13-content.md).

## 4. Space, shape, motion
- **Spacing:** 4 px base: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64.
- **Radius:** 4 px inputs and tags · 8 px buttons and cards · 12 px dialogs · full for pills.
- **Shadows:** `shadow-1` on cards, `shadow-2` on dialogs and menus (light); a 1 px `ink-600` outline instead in dark.
- **Signature detail:** the **diagonal cut** on the active-nav indicator's corner and the drop zone's top-right corner. Nothing else is decorated.
- **Motion:** 120 ms hover/focus, 200 ms menus, 320 ms dialogs, `cubic-bezier(.2,.8,.2,1)`; progress bars animate only while work runs; `prefers-reduced-motion` → no transitions.

## 5. Components (React, Radix primitives, styled with the tokens)
| Component | Notes |
|---|---|
| `AppShell` | Side nav 248 px (collapsible to 64 px), app bar, status strip, content up to 1440 px |
| `StatusStrip` | Auto-apply state, trust ramp (`37 / 50`), last sync, next snapshot; one line of `text-sm` |
| `HealthChip` | Store or S3: identifier + state + latency |
| `PauseButton` | Always visible in the app bar; Resume needs a click, never automatic |
| `DropZone` | Dashed `--color-border-control` with the diagonal-cut corner; keyboard "Browse files" button; announces files added |
| `JobRow` | File, matched product, step chips (inspect, match, S3, one per store), result |
| `StepChip` | Neutral → running (accent) → done (success) / held (danger outline) / failed (danger) |
| `BandPill`, `StatePill` | §2.4 |
| `CandidateCard` | Rank number, product, store links, reasons as `+`/`−` chips, score bar; selected state; shortcut number |
| `ChangePlan` | One row per target: S3, then each store's slot: the current file and the new file in Plex Mono with an `arrow-right` icon between them |
| `VersionCompare` | "On your stores now" vs "This ZIP", the lower one marked with a danger icon and text |
| `WhyPanel` | Popover listing signals and points in plain words |
| `DataTable` | Sticky header, sort, filters synced to the URL, keyboard row focus, **virtualised rows** (TanStack Virtual) so 2398+ rows stay fast (NFR-3) |
| `FilterChips`, `SearchField` | Catalog and Activity |
| `Timeline` | Product history |
| `IssueCard` | Cleanup: title, pairs, reason, suggested fix, actions |
| `KPITile` | Number (tabular), label, one-line detail, link |
| `Chart14d` | Stacked bars (auto vs you), per `dataviz` rules: labelled axes, legend, a table fallback |
| `SettingsForm`, `SecretField` | Masked value, Replace (write-only), Test button with result |
| `ConfirmDialog` | For Apply anyway, Roll back, Restore, Delete: what will change, on which stores |
| `Toast` | `role="status"` / `role="alert"`; never the only place an error shows |
| `KbdHint` | Shortcut keys in Plex Mono, bordered |

Shared rules (from TecHaust §5.1): targets ≥ 44 × 44 px for main actions (compact table actions ≥ 32 px with 8 px spacing), visible 2 px focus ring in `--color-focus`, every state designed (default, hover, focus, active, disabled, loading, error, selected), and WAI-ARIA patterns exactly.

## 6. Screens (layout notes for the mockups)
| Screen | Layout |
|---|---|
| Dashboard | Greeting + date; 4 KPI tiles (Review, Partial, Cleanup, Applied today); the drop zone; two columns: latest updates table (wide), connections and the 14-day chart |
| Upload | Compact drop zone; the batch table of `JobRow`s |
| Review | Two columns: the queue (330 px) and the detail card (alert, version compare, inside the ZIP, candidates, change plan, actions with shortcuts) |
| Catalog | Search + filter chips; the table with store identifier columns; row → Product |
| Product | Header with actions; left: store link cards, slots, fingerprints; right: canonical slug, history, stale store data |
| Cleanup | One card per issue group, each with its bulk action |
| Activity | Search + range chips; the log table, before and after in Plex Mono with an `arrow-right` icon between |
| Settings | Left sub-nav (Stores, Storage, Rules, Updates, Backup, App); store cards with fields, masked secrets, Test |
| First-run wizard | A centred 720 px card with a numbered step rail (Stores, Storage, Test, Catalog, Cleanup, Teach); one task per step; Back never loses input; the last step lands on the Dashboard |
| Tray menu | Windows' native menu: Open ShelfSync (default, bold), Pause everything / Resume, View logs, separator, Quit |
| Toasts | Windows toast: the symbol, a one-line title, one line of detail, one action ("Open Review"); wording in [13 §4](13-content.md) |
| Help panel | A right-hand drawer (400 px) opened from each screen's header "?"; short sections, the glossary, and links to the in-app guides |

**States on every screen:**
- **Loading:** skeleton rows in the real layout (no full-page spinner).
- **Empty:** one line on what will appear here, plus the next action (e.g. Review: "Nothing waiting. ZIPs that need a decision appear here.").
- **Error:** an inline alert at the top of the affected card with the reason and one action (Retry, Test connection, Open Settings); never only a toast.
- **Long content:** names truncate with an ellipsis and a full-text tooltip; tables scroll inside their card.

Responsive: designed for 1280–1920 px; usable at 1024 px (nav collapses to icons); no phone layout (a desktop app).

## 7. Accessibility checklist
- WCAG 2.2 AA in light and dark; status never by colour alone; minimum text 12 px.
- Every action reachable by keyboard; Review's single-key shortcuts only fire when focus isn't in a text field, and can be turned off.
- Live regions announce job progress milestones (not every percent).
- axe runs on every screen in both themes in CI ([07 §4](07-testing.md)).

## 8. Mockups and screenshots (Phase 3)
- Mockups are built **from these tokens and components** (not hand-picked colours) as HTML in `docs/05-design-system-appendix/mockup/`, with sample data from the catalog clearly labelled as sample. Appendix folders may hold HTML and images; the docs themselves stay Markdown ([CLAUDE.md](../CLAUDE.md) conventions).
- **Screenshots:** 8 screens × light and dark = **16 PNGs** at a 1440 × 900 viewport, full page, 2× pixel density, in `docs/05-design-system-appendix/screenshots/`, plus the wizard and the empty states as extras. They're taken in the **built-in browser pane** (the owner declined headless Chrome). Each is checked against this document before it's sent, and the mockup is also published as an artifact for clicking through.
- The `designer` agent builds them; `frontend-design` is loaded first, and `dataviz` for the dashboard chart ([09 §3](09-tooling.md), [12 §4](12-models-and-usage.md)).

- **Done (2026-10-26, approved):**
  - The mockup is in `docs/05-design-system-appendix/mockup/` ([runs/p3.4-mockups.md](runs/p3.4-mockups.md)).
  - The 16 screenshots plus 13 extras, PNG at 2× and full page, are in `docs/05-design-system-appendix/screenshots/`, made with the in-pane capture helper ([runs/p3.5-screenshots.md](runs/p3.5-screenshots.md)).
  - The clickable artifact is https://claude.ai/artifact/Gzzm2Mztikj8xqL49UoiRj. On a phone it shows the desktop layout shrunk to fit.

## 9. What the owner approves in this document
1. The Patina tokens unchanged, plus the three app-bar tokens (§2.2).
2. Store identifiers as shape + dot + code, with PluginWay's dot in its deeper teal `#007b80` on light surfaces (§2.3).
3. The band and state styles (§2.4).
4. The logo rules and the three concept directions (§1.2); the logo itself is chosen in Phase 3.
5. The asset list, including tray-icon states and installer art (§1.4).
