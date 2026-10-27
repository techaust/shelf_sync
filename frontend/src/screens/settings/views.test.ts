// UI-SET: each state of Settings › Updates and Settings › App as the page draws it, and the shared parts
// (ConfirmDialog, SecretField, Switch) as markup: the unit tests run in Node with no DOM, so the views are rendered
// to static HTML (react-dom/server). Behaviour that needs a browser (focus, the dialog's top layer) is in
// dialog.test.ts with fakes, and was checked by hand in the built-in browser pane (run file section 4).
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { Updates } from "../../api/settings";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { SecretField } from "../../components/SecretField";
import { Switch } from "../../components/Switch";
import { AppView } from "./AppView";
import { formFrom } from "./forms";
import { SETTINGS_PAGES, Settings } from "./Settings";
import { Restarting, UpdatesFailed, UpdatesLoading, UpdatesView } from "./UpdatesView";
import { type DateFormat, describeUpdates, type Phase } from "./updatesModel";
import { A, LATER, T, U } from "./wording";

const date: DateFormat = (iso) => (iso ? "28 October 2026 at 09:30 India Standard Time" : null);
const base: Updates = {
  development: false,
  key_available: true,
  installed: "0.2.0",
  previous: null,
  can_roll_back: false,
  database_changed: false,
  backup_at: null,
  backup_available: false,
  checking: false,
  busy: false,
  last_check: null,
  available: null,
  token: { set: false, expires_at: null, notice: false },
  last_result: null,
};
const actions = {
  onCheck: vi.fn(),
  onInstall: vi.fn(),
  onRollBack: vi.fn(),
  onSaveToken: vi.fn(async () => undefined),
  onRemoveToken: vi.fn(async () => undefined),
};
const decode = (html: string) => html.replaceAll("&#x27;", "'").replaceAll("&quot;", '"').replaceAll("&amp;", "&");
function updates(over: Partial<Updates>, phase: Phase = { kind: "idle" }, actionError: string | null = null) {
  const model = describeUpdates({ ...base, ...over }, phase, date);
  return decode(renderToStaticMarkup(h(UpdatesView, { model, phase, actionError, actions })));
}
const ok = { at: "2026-10-28T04:00:00Z", outcome: "ok" as const, detail: null };

describe("Settings › Updates", () => {
  it("loading: the card's layout in quiet blocks, marked busy", () => {
    const html = renderToStaticMarkup(h(UpdatesLoading));
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('class="sk is-title"');
  });

  it("load failed: the reason and Try again", () => {
    const html = decode(renderToStaticMarkup(h(UpdatesFailed, { text: U.loadFailed, onRetry: vi.fn() })));
    expect(html).toContain('role="alert"');
    expect(html).toContain(U.loadFailed);
    expect(html).toContain(">Try again</button>");
  });

  it("empty: the optional-token wording, Not set, and a password input for a new token", () => {
    const html = updates({});
    expect(html).toContain(U.empty);
    expect(html).toContain("ShelfSync 0.2.0");
    expect(html).toContain(">Check now</button>");
    expect(html).toContain("Not set");
    expect(html).toMatch(/<input[^>]*id="up-token"[^>]*type="password"/);
    expect(html).toMatch(/<input[^>]*id="up-token"[^>]*autoComplete="off"/); // React 19 writes the attribute as spelled in JSX
    expect(html).not.toContain("Roll back app");
    expect(html).not.toContain("Installs in under a minute"); // 13 section 6: not measured, dropped
  });

  it("up to date: the 13 line and the check's time", () => {
    const html = updates({ last_check: ok, token: { set: true, expires_at: null, notice: false } });
    expect(html).toContain("ShelfSync 0.2.0 is up to date.");
    expect(html).toContain("Checked 28 October 2026 at 09:30 India Standard Time.");
    expect(html).not.toContain(U.empty);
    expect(html).toContain("Saved");
  });

  it("ready: the update card with Install <v> and restart", () => {
    const html = updates({ last_check: ok, available: { version: "0.3.0", ready: true } });
    expect(html).toContain("Version 0.3.0 is ready to install.");
    expect(html).toContain("Install 0.3.0 and restart");
    expect(html).toMatch(
      /<button type="button" class="btn is-primary"><svg[\s\S]*?<\/svg>Install 0.3.0 and restart<\/button>/,
    );
  });

  it("preparing: the line while the files are checked, and the busy button", () => {
    const html = updates(
      { last_check: ok, available: { version: "0.3.0", ready: true } },
      { kind: "preparing", version: "0.3.0" },
    );
    expect(html).toContain("Checking the files of 0.3.0 before it's installed.");
    expect(html).toMatch(/aria-disabled="true" aria-busy="true"/);
  });

  it("error: the check's problem and an action's refusal at the top of the card", () => {
    const html = updates(
      { last_check: { ...ok, outcome: "token_refused" }, token: { set: true, expires_at: null, notice: false } },
      { kind: "idle" },
      "A check ran a moment ago. Try again in a minute.",
    );
    expect(html).toContain("GitHub refused the token. Check it, or remove it to check without one.");
    expect(html).toContain("A check ran a moment ago. Try again in a minute.");
    expect(html.match(/role="alert"/g)?.length).toBe(2);
  });

  it("development copy: the reason, and Check now off and described by it", () => {
    const html = updates({ development: true });
    expect(html).toContain('id="up-notice-development"');
    expect(html).toContain(U.development);
    expect(html).toMatch(/aria-disabled="true" aria-describedby="up-notice-development"/);
  });

  it("roll back without its backup: off, with the reason beside it", () => {
    const html = updates({ previous: "0.1.4", can_roll_back: true, database_changed: true, backup_available: false });
    expect(html).toMatch(/aria-disabled="true" aria-describedby="up-rollback-why"/);
    expect(html).toContain(U.rollBackNoBackup);
  });

  it("restarting: the panel, the line and, when late, the Start menu line", () => {
    const html = decode(renderToStaticMarkup(h(Restarting, { version: "0.3.0", late: false })));
    expect(html).toContain("ShelfSync is restarting");
    expect(html).toContain("This tab reloads when ShelfSync 0.3.0 answers.");
    expect(html).not.toContain(U.restartingLate);
    expect(decode(renderToStaticMarkup(h(Restarting, { version: "0.3.0", late: true })))).toContain(U.restartingLate);
  });
});

describe("Settings › App", () => {
  const stored = {
    port: 47615,
    theme: "system" as const,
    start_with_windows: true,
    notifications: true,
    log_retention_days: 30,
    installed: true,
  };
  const handlers = { onTheme: vi.fn(), onChange: vi.fn(), onSave: vi.fn(), onReset: vi.fn() };
  const app = (over: Partial<Parameters<typeof AppView>[0]> = {}) =>
    decode(
      renderToStaticMarkup(
        h(AppView, {
          form: formFrom(stored),
          errors: {},
          theme: "system",
          installed: true,
          saving: false,
          result: null,
          themeFailed: false,
          handlers,
          ...over,
        }),
      ),
    );

  it("normal: the theme, two switches, the two numbers, the danger zone and Save app", () => {
    const html = app();
    for (const text of [A.theme, "Same as Windows", "Light", "Dark", A.startHint, A.notificationsHint, A.portHint])
      expect(html).toContain(text);
    expect(html).toMatch(/<input type="radio" name="app-theme" checked="" value="system"/);
    expect(html.match(/role="switch"/g)?.length).toBe(2);
    expect(html).toContain(`${A.resetText} ${A.resetLine}`);
    expect(html).toContain('class="btn is-danger"');
    expect(html).toContain(">Save app</button>");
  });

  it("a development copy: Start with Windows off, locked, with the one-line reason", () => {
    const html = app({ installed: false });
    expect(html).toMatch(
      /id="app-start" class="toggle" aria-checked="false" aria-describedby="app-start-hint" aria-disabled="true"/,
    );
    expect(html).toContain(A.startDevelopment);
  });

  it("a field error: the field is invalid and described by its error", () => {
    const html = app({ errors: { port: A.portLimit(47615, 47624) } });
    expect(html).toMatch(/id="app-port"[^>]*aria-invalid="true" aria-describedby="app-port-error app-port-hint"/);
    expect(html).toContain("Use a port from 47615 to 47624.");
  });

  it("Start with Windows not applied: the warning beside Save", () => {
    const html = app({ result: { tone: "warning", text: A.savedNotApplied, note: null } });
    expect(html).toMatch(/class="form-foot__result"><div class="alert is-warning" role="status"/);
    expect(html).toContain(A.savedNotApplied);
  });

  it("saving: Save is off and busy", () => {
    expect(app({ saving: true })).toMatch(/type="submit" class="btn is-primary" aria-disabled="true" aria-busy="true"/);
  });

  it("the theme couldn't be saved: said under the choice", () => {
    expect(app({ themeFailed: true })).toContain(A.themeFailed);
  });
});

describe("the shared parts", () => {
  it("Switch: role switch, aria-checked, a visible label for it and a helper line", () => {
    const html = renderToStaticMarkup(
      h(Switch, { id: "s", label: "Notifications", checked: true, hint: "Helper.", onChange: vi.fn() }),
    );
    expect(html).toContain('<label class="switch-row__label" for="s">Notifications</label>');
    expect(html).toContain('<p class="field__hint" id="s-hint">Helper.</p>');
    expect(html).toMatch(
      /<button type="button" role="switch" id="s" class="toggle" aria-checked="true" aria-describedby="s-hint">/,
    );
  });

  it("SecretField: never a stored value in the page, only saved or not set", () => {
    const props = {
      id: "tok",
      text: T,
      maxLength: 300,
      check: () => null,
      onSave: vi.fn(async () => undefined),
      onRemove: vi.fn(async () => undefined),
    };
    const saved = decode(renderToStaticMarkup(h(SecretField, { ...props, set: true, expires: "Expires on 1 Jan." })));
    expect(saved).toContain("Saved");
    expect(saved).toContain(">Replace</button>");
    expect(saved).toContain(">Remove</button>");
    expect(saved).not.toContain("<input"); // no input until Replace
    expect(saved).not.toMatch(/•|\*\*\*/); // not even a mask
    const notSet = decode(renderToStaticMarkup(h(SecretField, { ...props, set: false })));
    expect(notSet).toContain("Not set");
    expect(notSet).toMatch(/<input[^>]*type="password"[^>]*maxLength="300"[^>]*value=""/);
    expect(notSet).not.toContain(">Remove</button>");
  });

  it("ConfirmDialog: a native dialog named by its title; the destructive button is is-danger", () => {
    const html = decode(
      renderToStaticMarkup(
        h(
          ConfirmDialog,
          {
            open: false,
            title: A.resetDialogTitle,
            confirmLabel: A.resetConfirm,
            danger: true,
            onConfirm: vi.fn(),
            onCancel: vi.fn(),
          },
          h("p", null, A.resetDialogLead),
        ),
      ),
    );
    expect(html).toMatch(/^<dialog class="confirm-dialog" aria-labelledby="(.+)-title" aria-describedby="\1-body"/);
    expect(html).toContain("Reset the access token?");
    expect(html).toContain('class="btn is-danger"');
    expect(html).toContain(">Cancel</button>");
    expect(html).not.toContain(" open");
  });
});

describe("the Settings shell", () => {
  const at = (path: string) =>
    decode(
      renderToStaticMarkup(
        h(
          MemoryRouter,
          { initialEntries: [path] },
          h(Routes, null, h(Route, { path: "/settings/:sub", element: h(Settings) })),
        ),
      ),
    );

  it("the sub-nav lists all six pages, the current one marked", () => {
    const html = at("/settings/stores");
    expect(SETTINGS_PAGES.map((page) => page.label)).toEqual([
      "Stores",
      "Storage",
      "Rules",
      "Updates",
      "Backup",
      "App",
    ]);
    for (const page of SETTINGS_PAGES) expect(html).toContain(`href="/settings/${page.sub}"`);
    expect(html).toMatch(
      /aria-current="page"[^>]*href="\/settings\/stores"|href="\/settings\/stores"[^>]*aria-current="page"/,
    );
    expect(html).toContain('<nav class="sub-nav" aria-label="Settings">');
  });

  it.each(["stores", "storage", "rules", "backup"] as const)("%s: the later-version panel", (sub) => {
    const html = at(`/settings/${sub}`);
    expect(html).toContain(LATER[sub].text);
    expect(html).toContain(LATER[sub].sub);
  });

  it("the sub-page's title is the focus target after a navigation", () => {
    expect(at("/settings/rules")).toContain('<h2 class="settings-title" tabindex="-1" data-nav-focus="">Rules</h2>');
  });

  it("an unknown page is Not found", () => {
    expect(at("/settings/nope")).toContain("There's no screen at this address.");
  });
});
