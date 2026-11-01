Status: open
Tier: C ([12 §2](../12-models-and-usage.md)): screen styles only, no new parts
Usage: lead `claude-opus-5-5/high` (cloud session, from `get_session`; no `model-audit` log here). 5-hour readings posted by the orchestrator: **31 % at 00:51 IST, 2026-11-02** (resets about 02:20 IST).

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
_(designer)_

## 5. Review
_(reviewer, copied in by the lead)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead)_
