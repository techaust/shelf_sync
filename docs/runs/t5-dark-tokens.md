Status: open
Tier: C ([12 §2](../12-models-and-usage.md)): screen styles only, no new parts
Usage: lead `claude-opus-5-5/high` (cloud session; model and effort from `get_session` and the model-guard hook, not from `model-audit`, whose log isn't on this machine); designer `claude-opus-5-5/high` (its agent file; `frontend-design` and Context7 not available here), two runs; reviewer `claude-opus-5-5/high` (its agent file) [`code-review`], review and re-check. 5-hour reading posted by the orchestrator: **31 % at 00:51 IST, 2026-11-02** (resets about 02:20 IST); every agent started under 2 hours after it (the last at 01:17 IST), so the gate was open; no later reading (this session can't read usage).

# T5: dark values as component tokens

One of the parallel follow-up tasks the orchestrator (a PC session) runs on 2026-11-02, approved by the owner that day. It closes the open follow-up "Token task: move the duplicated dark rules in `app.css` into component tokens" ([10](../10-status.md); m1a.3 review low 7, [m1a.3-app-shell.md](m1a.3-app-shell.md)).

Runs in a cloud session: no visual checks here (CLAUDE.md rule 10). The orchestrator checks light and dark on the PC and opens the PR.

## 1. Brief

### PRD IDs
- UI-SHELL (theme follows Windows, with a manual override), SET-06 (theme: system, light, dark), NFR-2 (WCAG 2.2 AA in both themes). Nothing new is built: every computed colour stays as it is.

### Skills and tools ([09 §3](../09-tooling.md))
- `frontend-design`: **not available in this cloud session** (it isn't in the session's skill list). Nothing visual is designed here; the change keeps every colour as it is.
- Context7 for Tailwind v4: **not available to the lead** (the Context7 server isn't connected in this session). The `designer` has the Context7 tools in its file and tries them first; if they aren't connected it says so. The change uses no Tailwind feature: plain CSS custom properties in the unlayered token files, as `tokens.css` and `shelfsync-tokens.css` already are.

### What changes
The theme rules written twice today, once as `:root[data-theme="dark"] …` and once as `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) … }`:

| Rule | File | Light (today) | Dark (today) | Also dark in `.tone-dark` today? |
|---|---|---|---|---|
| `.card` border colour | `app.css` | `--color-border` | `transparent` | no |
| `.store-dot` background | `app.css` | `--dot-light` (set on the element from store data) | `--dot-dark` | **yes** (`.tone-dark .store-dot`) |
| `.sk` background | `settings.css` | `--color-fill-subtle` | `--color-border` | no |
| `.secret-pair__mask` background | `stores.css` | `--color-fill-subtle` | `--color-surface-alt` | no |

`settings.css` and `stores.css` are included: the same pair, in files this task owns. `storage-backup.css` has none.

### Where the tokens live (lead's decision, with reasons)
A new hand-written **`frontend/src/styles/component-tokens.css`**, imported in `app.css` right after `generated/shelfsync-tokens.css` (unlayered, like the other token files). Not `brand/tokens.json` and not the generator:
1. `brand/tokens.json` is TecHaust's file, **copied unchanged** (its `$source` records the commit and SHA-256), and its renderer has no notion of components. ShelfSync component tokens there would break that contract and every future TecHaust sync.
2. These tokens carry no brand data: each is a reference to an existing semantic token or a CSS keyword. Nothing needs generating, and `sync-tokens.mjs` (which builds the ShelfSync layer from brand data) is outside this task's files.
3. One file holds every component's dark value, so each theme scope is written once, not once per stylesheet.

### The two mechanisms
1. **Component dark tokens** (`.card`, `.sk`, `.secret-pair__mask`): a token is set **only in the two dark scopes**, and the rule reads it with its light value as the fallback, e.g. `border: 1px solid var(--card-border-dark, var(--color-border));`.
   - Why not also set a light value on `:root`: a custom property that refers to another is substituted **where it is declared**, so `--x: var(--color-border)` on `:root` would freeze `:root`'s value and stop `.tone-dark` (which redefines `--color-border`) from reaching the rule. The fallback is substituted at the element, so light stays exactly as today in every scope.
   - Dark values declared on `:root` are safe: the `.tone-dark` values are the dark values (both come from `tokens.json`'s `dark` column), and the test checks that.
   - Names: `--<component>-<property>-dark`; the designer may adjust if a name reads badly, and records it.
2. **Theme switches** (`.store-dot`): its colours are set on each element from store data, so no token on `:root` can hold them. Two switches, set once per theme scope: `--theme-light` and `--theme-dark`; each is a single space (an empty value) while that theme is in force, and `initial` (guaranteed-invalid, so a `var()` fallback is used) otherwise. Then `var(--theme-dark, X)` reads "X unless dark", and the rule is written once:
   `background: var(--theme-dark, var(--dot-light)) var(--theme-light, var(--dot-dark));`
   - Set on `:root` (light), in both dark scopes, and on `.tone-dark` (dark), which keeps today's `.tone-dark .store-dot`.
   - Checked by the lead before this brief: Lightning CSS (the frontend's own copy) keeps the single-space value in normal and minified output. The designer also checks the built `dist/` CSS.

### Out of scope, owned elsewhere
- **Never touch:** `frontend/src/screens/**`, `app/**`, `lib/**`, `main.tsx`, `theme/**` (task T4), `backend/`, `packaging/`, `tools/`, `.github/`, `pyproject.toml`, `uv.lock`, `docs/10-status.md`, `CHANGELOG.md`. Also left alone: `frontend/scripts/`, `frontend/src/components/**`, `brand/`. **No class name in any TSX file changes**; if one must, the designer stops and the question goes to the orchestrator.
- No colour, size or wording changes. No new package.

### Done when
1. No `[data-theme="dark"]` or `prefers-color-scheme` selector is left in `app.css`, `settings.css`, `stores.css` or `storage-backup.css`; theme scopes exist only in the token files.
2. A new test, `frontend/src/styles/component-tokens.test.ts`, reads the CSS as text (`?raw`) and proves the result per theme without a browser:
   - parses the theme scopes of `generated/tokens.css`, `generated/shelfsync-tokens.css` and `component-tokens.css` (`:root`, the system-dark `@media` block, `[data-theme="dark"]`, `.tone-dark`);
   - the two dark forms in `component-tokens.css` declare exactly the same tokens with the same values (they can't drift);
   - reads the real declarations of the four rules from the stylesheets and resolves them with a small `var()` resolver that models substitution where declared, inheritance into `.tone-dark`, `initial` and the empty value;
   - for every context: `data-theme` light, dark or absent × system light or dark, on the page and inside `.tone-dark`, and for every `STORE_PALETTE` pair, the resolved colour equals today's rule (the table above), as hex;
   - the `.tone-dark` semantic values equal the dark ones (the assumption behind mechanism 1).
3. In `frontend/`, through `bash tools/heavy.sh --log <name> …`: `npm run lint`, `npm run typecheck`, `npm test` (with `tokens.test.ts` and `contrast.test.ts`), `npm run build` all pass. The built CSS still holds the switches and the component tokens (grep `dist/`).
4. The reviewer approved (code review; no visual review here). The run file has the report, the review and a handover.

### Order
Run file (this) → `designer` (own worktree, commits there, never pushes) → `reviewer` (`code-review`) → fixes → re-check → lead integrates on `refactor/dark-tokens`, runs the checks, pushes. **No PR**: the orchestrator checks light and dark on the PC and opens it.

## 4. Designer report
_(designer, cloud session, own worktree `agent-a47ec4f3c09046274`, base `ed3e3a7`; claude-opus-5-5/high)_

**Skills and tools.** `frontend-design`: not available in this session (not in the skill list), so it changed nothing; nothing visual was designed, every colour stays as it was. Context7: not available (no Context7 tools, and no tool search to load them, are exposed to this agent); not needed, the change uses no Tailwind feature. `dataviz`: not relevant (no chart). No browser and no screenshots: visual checks never run in a cloud session (CLAUDE.md rule 10).

**Files changed** (all under `frontend/src/styles/`)
- `component-tokens.css` (new, unlayered, imported in `app.css` right after `generated/shelfsync-tokens.css`, with a one-line comment above the import): header comment on both mechanisms and on the two dark forms that must match; the theme switches on `:root`, both dark scopes and `.tone-dark`; the component dark tokens in the two dark scopes only.
- `app.css`: the import; `.card` and `.store-dot` written once; both dark pairs, `.tone-dark .store-dot`, and the comment above the `.card` pair removed (a one-line pointer to `component-tokens.css` now sits above `.card`). Everything else unchanged.
- `settings.css`: `.sk` written once, its pair removed. `stores.css`: `.secret-pair__mask` written once, its pair removed. `storage-backup.css`: untouched (it had none).
- `component-tokens.test.ts` (new): see below.
- No TSX file, class name, generated file, script or brand file changed.

**Tokens added** (light = the fallback the rule uses; dark = the value in both dark scopes)

| Token | Read by | Light | Dark |
|---|---|---|---|
| `--theme-light` | `.store-dot` | ` ` (single space, empty: light in force) | `initial` |
| `--theme-dark` | `.store-dot` | `initial` | ` ` (single space, empty); also on `.tone-dark` |
| `--card-border-dark` | `.card` `border` | not set (fallback `var(--color-border)`) | `transparent` |
| `--sk-background-dark` | `.sk` `background` | not set (fallback `var(--color-fill-subtle)`) | `var(--color-border)` |
| `--secret-pair-mask-background-dark` | `.secret-pair__mask` `background` | not set (fallback `var(--color-fill-subtle)`) | `var(--color-surface-alt)` |

Name: `.secret-pair__mask` gives `--secret-pair-mask-background-dark` (the BEM `__` flattened to `-`, as custom property names usually are). `.store-dot`'s rule: `background: var(--theme-dark, var(--dot-light)) var(--theme-light, var(--dot-dark));`.

Specificity: the old dark rules were `(0,3,0)` and now the dark value sits in the base rule `(0,1,0)`. I checked every rule in the stylesheets: no other rule sets `border`/`border-color` on a `.card` or `background`/`background-color` on `.sk`, `.secret-pair__mask` or `.store-dot` (the forced-colors blocks set none of these), so nothing can now win over the dark value. Since the fix round the test enforces this: in every `src/styles/*.css` (by glob, except `component-tokens.css`), in any media query, a rule whose selector's last compound carries the class (`.card.is-x`, `.card:hover`, `.foo .card`; not `.card-alert`) may not set that property or its colour longhand; only the bare-class base rule does. Not covered: a rule on another class the same element carries (`.store-card { border-color: … }` on `card store-card`); none exists today.

**The test** (`component-tokens.test.ts`, 71 tests; 73 after the fix round): a small CSS reader (style rules with their `@media` conditions; `@layer` transparent; a nested rule or an unknown theme scope throws) and a `var()` resolver: substitution where declared (`:root` declarations against `:root`, `.tone-dark` ones against `.tone-dark`, which inherits from `:root`; an element's own `--dot-*` against itself), nested fallbacks, `initial` and undeclared as guaranteed-invalid, the empty value, cycles, and a declaration that ends up invalid (a distinct result that never equals an expected colour). Cascade among the token scopes by specificity, then file order (`tokens.css`, `shelfsync-tokens.css`, `component-tokens.css`).
- Resolver sanity (3): a hand-worked case (substitution where declared vs at the element, the switches, invalid results, a cycle with and without a fallback).
- Colours (60): `data-theme` light, dark, absent × Windows light, dark × page, inside `.tone-dark` × `.card`, `.sk`, `.secret-pair__mask` and both `STORE_PALETTE` pairs; the rule is read from the stylesheet, the expectation comes from an independent table of the old rules (the brief's), turned into hex from `brand/tokens.json` in the right scope.
- Structure (8; 10 since the fix round): no `[data-theme="dark"]` or `prefers-color-scheme` in any `src/styles/*.css` but `component-tokens.css` (since the fix round by glob, `fonts.css` included, with a test that all five sheets were found and none is empty); the two dark forms in `component-tokens.css` identical; the rules read exactly the tokens `component-tokens.css` declares (needed because `fill-subtle` and `surface-alt` are both `ink-750` in dark, so a misspelt mask token would still resolve to the right colour); `.tone-dark`'s `--color-*` values equal both dark blocks of `tokens.css`; `StoreBadge.tsx` still sets `--dot-light`/`--dot-dark` (read as text, not changed).
- **It fails when broken** (tried locally, each restored after): `.tone-dark` switches removed (6 fail); a light value `--sk-background-dark: var(--color-fill-subtle)` on `:root` (3 fail: `.sk` inside `.tone-dark` in light); the dark forms drifting (3 fail); both switches empty in light (6 fail); `.card` reading no token (7 fail); the mask rule reading a misspelt token (1 fail). Back to 71 passed after restore.

**Commands and results** (in the worktree's `frontend/`, through `bash ../tools/heavy.sh --log <name> …`; logs in `frontend/.logs/`, git-ignored)
- `npm ci` (t5-npm-ci): exit 0.
- `npm run lint` (t5-lint): first run exit 1, Biome formatting of the new test file only; after `npx biome check --write` on the new files, exit 0 (124 files, no fixes).
- `npm run typecheck` (t5-typecheck): exit 0.
- `npm test` (t5-test): exit 0, 29 files, 1008 tests passed. The three style tests alone (`component-tokens`, `tokens`, `contrast`): 440 passed. `tokens.test.ts` scans `component-tokens.css` too: it types no colour.
- `npm run build` (t5-build): exit 0.

**Built CSS** (`frontend/dist/assets/index-woCGEt7l.css`; the single-space values survive minification):
```
:root{--theme-light: ;--theme-dark:initial}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--theme-light:initial;--theme-dark: ;--card-border-dark:transparent;--sk-background-dark:var(--color-border);--secret-pair-mask-background-dark:var(--color-surface-alt)}
.tone-dark{--theme-light:initial;--theme-dark: }
:root[data-theme=dark]{--theme-light:initial;--theme-dark: ;--card-border-dark:transparent;--sk-background-dark:var(--color-border);--secret-pair-mask-background-dark:var(--color-surface-alt)}
.card{background:var(--color-surface);border:1px solid var(--card-border-dark,var(--color-border));border-radius:var(--radius-md);box-shadow:var(--shadow-1);min-width:0}
.store-dot{background:var(--theme-dark,var(--dot-light)) var(--theme-light,var(--dot-dark));flex:none;width:.625rem;height:.625rem}
.sk{border-radius:var(--radius-sm);background:var(--sk-background-dark,var(--color-fill-subtle));display:block}
.secret-pair__mask{padding:var(--space-1) var(--space-3);border-radius:var(--radius-sm);background:var(--secret-pair-mask-background-dark,var(--color-fill-subtle));display:inline-block}
```
No `.card`, `.store-dot`, `.sk` or `.secret-pair__mask` selector with `data-theme` or `.tone-dark` is left in the built CSS.

**Not verified**
- Real-browser rendering in light and dark (Same as Windows, Light, Dark; a live Windows switch; the app bar's store dots; skeletons; a saved secret mask; cards), and forced-colors mode: no browser in a cloud session. The orchestrator checks these on the PC.
- That the browser (WebView/Edge) treats the single-space custom property as a valid empty value: modern CSS Variables allows it and Lightning CSS keeps it, but no browser ran here.
- The resolver models the CSS rules it needs, not the whole of CSS (no `!important`, no nesting, no `inherit`/`unset` on custom properties: those throw); the colour table is my reading of the old rules, cross-checked against the brief's table.

**Sample or placeholder data:** none. **Open questions:** none.

### Fix round (review: approved, one medium and lows 2-5; low 6 skipped as asked)
- **Medium 1:** `declaration()` now reads every stylesheet in `src/styles/` (glob `./*.css` minus `component-tokens.css`: `app.css`, `fonts.css`, `settings.css`, `storage-backup.css`, `stores.css`) and fails on any rule whose last compound carries the class (the pattern `\.<class>(?![\w-])` on the last compound, after splitting on combinators) that sets the colouring property or its longhand, besides the bare-class base rule. The forced-colors blocks touch none of these properties, so the old forced-colors exclusion is gone (stricter). The specificity sentence above is corrected.
- **Low 2:** the theme scopes resolve inside each test (a `parent()` call), so no `expect` runs while Vitest collects.
- **Low 3:** both sides of every colour comparison are lower-cased (`lower()`), and the expected dot colour is checked to be `#rrggbb`.
- **Low 4:** the "no theme scope of its own" check runs over the same glob (now five sheets, `fonts.css` included), with a test that the glob found all five and that none is empty.
- **Low 5:** the `component-tokens.css` header describes both mechanisms as the CSS Custom Properties spec defines them, and says that browser rendering is checked on the PC and is not yet recorded in 04-A.
- **Probes** (each appended or edited, run, then restored): the reviewer's `.card.chunk-failed { border-color: var(--color-border); }` in `app.css` now fails 13 tests (it passed 71 before); `.store-dot.is-circle { background: var(--dot-light); }` in `storage-backup.css` fails 25; `.foo .sk:hover { background-color: var(--color-border); }` in `fonts.css` fails 13. The six earlier breaks still fail (6, 3, 3, 6, 7, 1). After restore: 73 passed.
- **Checks** (in `frontend/`, through `bash ../tools/heavy.sh --log t5-fix-<name> …`): `npm run lint` exit 0 (124 files); `npm run typecheck` exit 0; `npm test` exit 0, 29 files, 1010 tests (`component-tokens.test.ts`: 73); `npm run build` exit 0, and the built CSS still holds `:root{--theme-light: ;--theme-dark:initial}` and `.tone-dark{--theme-light:initial;--theme-dark: }`.
- Still not verified: real-browser rendering (on the PC, as above).

## 5. Review
_(reviewer `claude-opus-5-5/high`, `code-review` loaded (it ran a forked read-only helper; the reviewer re-checked each of its points); `frontend-design` not available; code review only, no visual review (CLAUDE.md rule 10). Copied in by the lead.)_

**Review of `ed3e3a7..54a5890`: APPROVE.** The hard requirement is met: every computed colour is as at `ed3e3a7` in light, dark by setting, dark by system, `data-theme="light"` with system dark, and inside `.tone-dark`.
- **Cascade:** no other rule sets `border`/`border-color` on a `.card` or `background` on `.sk`, `.store-dot` or `.secret-pair__mask`. The other rules on these elements set only size, radius or clip-path, the other classes they carry colour nothing, and no Tailwind utility sits on them. So the drop from (0,3,0) to (0,1,0) changes nothing today.
- **Scope:** `.tone-dark` is only on `AppBar.tsx`'s `<header>`, and `.store-dot` is rendered only by `StoreBadge.tsx` (`IdentifierPicker` goes through it).
- **Mechanisms:** the CSS reasoning is correct per the spec. The shorthand gives `"#hex "` or `" #hex"`. Without `--dot-*` it is invalid at computed-value time, so the dot is transparent, as before. Forced colours are unchanged.
- **Checks the reviewer ran:** `vitest run src/styles` 444 passed; lint, typecheck exit 0; `npm test` 1008 passed; build exit 0, and the built CSS holds the switches and tokens.
- **Probes:** the old `.store-dot` rule restored → 19 failed (good). `.card.chunk-failed { border-color: var(--color-border); }` → all passed, which was finding 1.

| # | Severity | Finding | Outcome |
|---|---|---|---|
| 1 | medium | The test only checked rules whose last selector part was exactly the class, and skipped `storage-backup.css`: a later `.card.x { border-color }` would win in dark with every test green; the run file overstated the guard | fixed (`6ab9976`) |
| 2 | low | `scopes(context)` ran an `expect` during Vitest's collection | fixed (`6ab9976`) |
| 3 | low | expected dot colour lower-cased, computed not | fixed (`6ab9976`) |
| 4 | low | "no theme scope" check over a hand-written list of four sheets | fixed: glob over `src/styles/*.css` (`6ab9976`) |
| 5 | low | `component-tokens.css` stated browser behaviour as fact, which isn't verified in 04-A | fixed: worded per the CSS spec, browser check on the PC (`b21fdcb`) |
| 6 | low | `semantic()` duplicates `contrast.test.ts` helpers | skipped by the lead: a shared helper would also change `contrast.test.ts`, outside this task's change |
| 7 | low | the decision belongs in `11-decisions.md` as "Lead (proposed)"; `Usage:` lacked the agent runs | `Usage:` filled; the `11` row is left to the orchestrator (§7): `11-decisions.md` isn't in this task's files, and parallel tasks may edit it |

**Re-check of the fix diff `54a5890..b32ef6e`: APPROVE.** Findings 1–5 fixed.
- **Probes:** `.card.chunk-failed` now fails 13 tests. Lookalike names (`.card-alert.x`, `.secret-pair__masks .y`, `.card__section`) pass, as they should. A forced-colours background on `.store-dot.is-square` in `fonts.css` fails 25, so the glob reaches `fonts.css`.
- **Checks the reviewer ran:** `npm test -- component-tokens` 73 passed; lint exit 0.
- **One new low:** the run file's "Structure (8)" bullet was stale. The lead fixed it.
- **Not verified by the reviewer:** real-browser rendering. The re-check didn't re-run build, typecheck or the full suite; the lead did (§6).

## 6. Integration notes
_(lead, 2026-11-02, cloud session)_
- The designer's worktree commits were fast-forwarded onto `refactor/dark-tokens` (no squash here; GitHub squash-merges the PR). Base `main` at `f5f95a4`.
- **Full checks on the integrated branch** (in `frontend/`, through `bash ../tools/heavy.sh --log t5-lead-<name> …`): `npm run lint` exit 0; `npm run typecheck` exit 0; `npm test` exit 0, 29 files, 1010 tests; `npm run build` exit 0, and `dist/` CSS holds `:root{--theme-light: ;--theme-dark:initial}` and `.tone-dark{--theme-light:initial;--theme-dark: }`, with no `data-theme`/`.tone-dark` selector left on the four components. `brand/` untouched, so its checks didn't need to run.
- **Files changed:** `frontend/src/styles/{app,settings,stores,component-tokens}.css`, `frontend/src/styles/component-tokens.test.ts`, this file. No file another task owns.
- **Duplicated dark pairs left:** none, in `app.css` or any other stylesheet. The only theme scopes are in the token files: `generated/tokens.css`, `generated/shelfsync-tokens.css`, and `component-tokens.css`. `component-tokens.css` holds its own one pair of scope blocks, as the token files do; the test keeps the two blocks identical.
- **Pushed** `refactor/dark-tokens`. **No PR** (the orchestrator checks light and dark on the PC, then opens it).

- **Visual check on the PC (orchestrator, 2026-11-02, CLAUDE.md rule 10):** `main` and this branch, each built and served by the real `create_app` with in-memory stores and two test stores, in the built-in pane. Every element's computed colours (text, background, four border colours, shadow, outline, fill, stroke, opacity, background image), transitions off, on all 12 pages: **identical to `main` in all 48 comparisons** (light, Dark by setting, dark from Windows, Light over a dark Windows). That covers the store dots in the health chips, on Settings › Stores and in the identifier picker, the cards and the secret masks. Recorded as 04-A V54; `component-tokens.css` now points to it (review low 5).
- **Not checked visually:** the loading skeletons (`.sk`, only for a moment while Settings loads) and forced colours (the pane can't emulate them); both are covered by `component-tokens.test.ts`.

## 7. Handover
_(lead, 2026-11-02)_ Code done, reviewed and pushed; the task waits on the orchestrator.

**For the orchestrator, on the PC:**
1. **Light and dark check** of the built app: Same as Windows (Windows light and dark, and a live switch), Light, Dark. Look at:
   - cards: a border in light, none in dark;
   - store dots in the app bar's health chips (the dark dot in both themes) and on Settings › Stores and the identifier picker (the light dot in light, the dark one in dark);
   - skeletons while Settings loads;
   - a saved secret's mask on Settings › Stores;
   - forced colours.
   Any getComputedStyle value should equal `main`'s. The only new browser dependency is the single-space custom property (the `--theme-*` switches): if store dots go transparent, that's where to look.
2. **After it passes:** add a 04-A row ("Edge/WebView2 honours a whitespace-only custom property as an empty value, and `initial` as guaranteed-invalid", with the date), and point `component-tokens.css`'s header to it (review low 5).
3. **`11-decisions.md`, "Lead (proposed)" row:** component tokens live in a hand-written `frontend/src/styles/component-tokens.css`, not `brand/tokens.json` (TecHaust's file, copied unchanged) or `sync-tokens.mjs` (no brand data in them). Dark-only tokens are read with the light value as the fallback, and `.store-dot` uses theme switches (reasons in §1).
4. Then open the PR, close the follow-up in `10`, and add the CHANGELOG line.
5. **Clean up:** the designer's worktree `.claude/worktrees/agent-a47ec4f3c09046274` (branch `worktree-agent-a47ec4f3c09046274`) is local to this cloud VM and was never pushed. It's integrated; this session removes it.
