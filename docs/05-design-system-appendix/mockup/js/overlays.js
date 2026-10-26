/* ShelfSync mockup, P3.4 part B: ConfirmDialog (05 section 5) and the help panel (UI-HELP).
   Both are native modal <dialog> elements: the rest of the page is inert while one is open, Tab stays inside it,
   Esc closes it, and focus goes back to the control that opened it. Nothing is saved or sent. */
"use strict";
(() => {
  const SS = window.SS;
  const { $, esc, icon, storeBadge, toast, mt } = SS;

  // A stable way to find the opener again if the page redrew it while the dialog was open (finding 1):
  // its id, or the first data-* attribute that names exactly one element.
  function locator(el) {
    if (!el) return null;
    if (el.id) return `#${CSS.escape(el.id)}`;
    for (const a of el.attributes) {
      if (!a.name.startsWith("data-")) continue;
      const sel = `[${a.name}="${CSS.escape(a.value)}"]`;
      if (document.querySelectorAll(sel).length === 1) return sel;
    }
    return null;
  }
  function trapReturn(dlg, opener) {
    const sel = locator(opener);
    dlg.addEventListener("close", () => {
      const region = document.getElementById("toasts");
      if (dlg.contains(region)) document.body.append(region); // toasts shown while the dialog was open
      dlg.remove();
      const back = opener && document.contains(opener) ? opener : sel && document.querySelector(sel);
      if (back) back.focus(); else SS.focusHeading();
    }, { once: true });
  }

  /* ---------- ConfirmDialog ----------
     opts: title, lead, plan [{target, label, from, to, check, wait}], body (html), note, confirm (label), danger,
     done (toast text), wire(dlg, api) for dialogs with their own controls, opener */
  const planRow = (r) => {
    const target = r.target === "S3" ? `<span class="store-badge">${icon("hard-drive")}S3</span>` : storeBadge(r.target);
    let files;
    if (r.wait) files = `<span class="is-wait">${icon("triangle-alert")}${esc(r.wait)}</span>`;
    else if (r.check) files = `<span class="plan-check">${icon("circle-check")}<span class="mono">${esc(r.check)}</span> is in S3</span>`;
    else files = `${r.from ? `<span class="mono is-old">${esc(r.from)}</span>${icon("arrow-right")}<span class="sr-only">to</span>` : ""}<span class="mono">${esc(r.to)}</span>`;
    return `<li><span class="target">${target} <small>${esc(r.label || "")}</small></span><span class="files">${files}</span></li>`;
  };
  SS.planRows = (plan) => `<ul class="change-plan">${plan.map(planRow).join("")}</ul>`;

  SS.confirm = (o) => {
    const dlg = document.createElement("dialog");
    dlg.className = "confirm-dialog";
    dlg.setAttribute("aria-labelledby", "dlg-title");
    dlg.innerHTML = `<form method="dialog" class="confirm-dialog__inner">
      <div class="confirm-dialog__head"><h2 class="confirm-dialog__title" id="dlg-title"></h2>
        <button class="btn is-ghost icon-btn" value="cancel" aria-label="Close">${icon("x")}</button></div>
      <div class="confirm-dialog__body">
        ${o.lead ? `<p class="confirm-dialog__lead">${mt(o.lead)}</p>` : ""}
        ${o.body || ""}
        ${o.plan ? `<h3 class="sec-title">What will change</h3><div class="dlg-plan">${SS.planRows(o.plan)}</div>` : ""}
        ${o.note !== undefined ? `<p class="plan-note dlg-note">${mt(o.note)}</p>` : ""}
      </div>
      <div class="confirm-dialog__foot">
        <span class="sample-tag">${icon("flask-conical")}Mockup: nothing is sent</span><span class="spacer"></span>
        <button class="btn" value="cancel">Cancel</button>
        <button class="btn ${o.danger ? "is-danger-solid" : "is-primary"}" value="ok" id="dlg-ok">${esc(o.confirm)}</button>
      </div></form>`;
    dlg.querySelector("#dlg-title").innerHTML = mt(o.title); // file names in the title are set in Plex Mono
    document.body.append(dlg);
    trapReturn(dlg, o.opener);
    const api = {
      setPlan: (plan) => { dlg.querySelector(".dlg-plan").innerHTML = SS.planRows(plan); },
      setNote: (t) => { dlg.querySelector(".dlg-note").innerHTML = mt(t); },
      setConfirm: (label, enabled = true) => {
        const b = dlg.querySelector("#dlg-ok");
        b.textContent = label;
        b.disabled = !enabled;
      },
    };
    if (o.wire) o.wire(dlg, api);
    dlg.addEventListener("close", () => {
      if (dlg.returnValue === "ok") toast(o.confirm, o.done || "Nothing was sent.", true);
      if (o.onClose) o.onClose(dlg.returnValue === "ok");
    });
    dlg.showModal();
    // destructive dialogs start on Cancel; others on the confirm button
    // dialogs with their own choices start on the first choice; destructive ones on Cancel; the rest on the confirm button
    const firstChoice = o.wire && dlg.querySelector(".confirm-dialog__body input:checked, .confirm-dialog__body input, .confirm-dialog__body select");
    (firstChoice || (o.danger ? dlg.querySelector('button[value="cancel"]:not(.icon-btn)') : dlg.querySelector("#dlg-ok"))).focus();
  };

  /* ---------- Help panel ---------- */
  const GLOSSARY = [
    ["Slug", "The short, web-address form of a name, e.g. <span class=\"mono\">jupiterx</span>"],
    ["Canonical slug", "The one slug ShelfSync uses for a product across all stores, and for its file names; it starts as the shared URL slug and you can edit it"],
    ["Twin", "The same product on another store, linked by its slug"],
    ["Slot", "One download button on a product (most have one, \"Download\")"],
    ["Fingerprint", "What a matching ZIP looks like inside (folder, header name, author)"],
    ["Band", "How sure the match is: Certain, Likely, Unsure, No match"],
    ["Held", "Waiting in Review because a safety rule stopped it"],
    ["Partial", "Updated on some stores but not all; nothing was deleted"],
    ["Change plan", "The exact list of what will change, shown before anything changes"],
    ["MD5", "A fingerprint of a file's bytes, used to check an upload arrived intact"],
    ["Range read", "Reading only part of a file in S3, so the whole ZIP isn't downloaded"],
    ["<span class=\"mono\">modified_after</span>", "Asking a store for only the products changed since a time"],
    ["SSE", "How the page gets live progress from ShelfSync without refreshing"],
    ["WAL", "The SQLite setting that keeps the database safe when the app stops suddenly"],
    ["ETag", "A value S3 returns for a file; not used as proof of content"],
    ["Trust ramp", "The first 50 Certain ZIPs, which wait for your approval before auto-apply is allowed"],
  ]; // 13 section 5, unchanged

  const TOPIC = {
    review: { title: "Help: Review", sections: [
      ["How Review works", "<p>A ZIP waits here when ShelfSync isn't sure of the match, or when a safety rule held it. Nothing changes on a store until you approve.</p>"],
      ["Bands", `<ul class="help-bands"><li>${SS.pill("certain")}<span>Matched by a confirmed fingerprint or an approved file name.</span></li><li>${SS.pill("likely")}<span>A strong match with at least one difference to check.</span></li><li>${SS.pill("unsure")}<span>Several products fit about as well.</span></li><li>${SS.pill("nomatch")}<span>Nothing scored high enough. Paste the product's address.</span></li></ul>`],
      ["Held", `<p>These safety rules hold a ZIP in Review even when it's Certain:</p><ul class="plain-list">
        <li>a downgrade</li><li>the same version with a different MD5</li><li>versions that disagree with each other</li>
        <li>a version family jump: the first number goes down, or up by more than 1</li><li>the product isn't linked on every active store</li>
        <li>the slot fails the attachment check</li><li>the download was changed outside ShelfSync</li>
        <li>Windows Defender found a threat (it can only be discarded), or couldn't scan the ZIP</li></ul>
        <p>Apply anyway always asks first.</p>`],
      ["Shortcuts", `<ul class="help-keys"><li><span class="kbd-hint">J</span><span class="kbd-hint">K</span> next, previous</li><li><span class="kbd-hint">1</span>–<span class="kbd-hint">3</span> pick a candidate</li><li><span class="kbd-hint">A</span> approve and apply</li><li><span class="kbd-hint">U</span> paste URL</li><li><span class="kbd-hint">D</span> discard</li></ul><p>They only work when you aren't typing in a field, and you can turn them off in the queue.</p>`],
    ] },
    cleanup: { title: "Help: Cleanup", sections: [
      ["What Cleanup finds", "<p>Twins that weren't linked, stale version keys, downloads changed outside ShelfSync, products deleted or trashed outside ShelfSync, and files in S3 that ShelfSync didn't upload.</p>"],
      ["Suggested fixes", "<p>Each issue says why it's here and what ShelfSync suggests. Apply suggested fixes links the near-miss twins and removes the stale version keys; the number on the button counts those. A download changed outside ShelfSync and a file ShelfSync didn't upload always wait for you to choose.</p>"],
    ] },
  };
  const general = { title: "Help", sections: [
    ["Getting around", "<p>Drop ZIPs on the Dashboard or in Upload. ZIPs that need you wait in Review; problems on your stores show in Cleanup; every change is in Activity.</p>"],
    ["Pause everything", "<p>Pauses every upload and store write. Nothing starts again until you click Resume.</p>"],
  ] };

  SS.openHelp = (opener, focusGlossary) => {
    const t = TOPIC[SS.st.route] || general;
    const dlg = document.createElement("dialog");
    dlg.className = "help-panel";
    dlg.setAttribute("aria-labelledby", "help-title");
    dlg.innerHTML = `<div class="help-panel__head"><h2 class="help-panel__title" id="help-title">${esc(t.title)}</h2>
        <button class="btn is-ghost icon-btn" type="button" id="help-close" aria-label="Close help">${icon("x")}</button></div>
      <div class="help-panel__body">
        ${t.sections.map(([h, b]) => `<section class="help-sec"><h3>${h}</h3>${b}</section>`).join("")}
        <section class="help-sec"><h3>Guides</h3><ul class="help-guides">
          <li><a href="#" data-mock="Would open the guide: make a Shop Manager key for a store.">${icon("book-open")}Make a Shop Manager key</a></li>
          <li><a href="#" data-mock="Would open the guide: the S3 access policy (IAM) ShelfSync needs.">${icon("book-open")}Set up the S3 access policy (IAM)</a></li>
          <li><a href="#" data-mock="Would open the guide: make a read-only GitHub token for updates.">${icon("book-open")}Make a GitHub token for updates</a></li>
        </ul></section>
        <section class="help-sec" aria-labelledby="gl-title"><h3 id="gl-title">What does this word mean?</h3>
          <label class="field__label" for="gl-find">Find a word</label>
          <input class="input" id="gl-find" type="search" autocomplete="off" placeholder="Slug, twin, held…">
          <dl class="glossary" id="glossary">${GLOSSARY.map(([w, m]) => `<div><dt>${w}</dt><dd>${m}</dd></div>`).join("")}</dl>
          <p class="muted help-none" id="gl-none" hidden>No word matches. Try a shorter search.</p>
        </section>
      </div>`;
    document.body.append(dlg);
    trapReturn(dlg, opener);
    dlg.querySelector("#help-close").addEventListener("click", () => dlg.close());
    // close only on a click on the backdrop, outside the drawer's box; a click in the drawer's empty space keeps it open (finding 5)
    dlg.addEventListener("click", (e) => {
      if (e.target !== dlg) return;
      const r = dlg.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dlg.close();
    });
    dlg.querySelector("#gl-find").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      let shown = 0;
      dlg.querySelectorAll("#glossary > div").forEach((d) => { const hit = !q || d.textContent.toLowerCase().includes(q); d.hidden = !hit; shown += hit; });
      dlg.querySelector("#gl-none").hidden = shown > 0;
    });
    dlg.showModal();
    (focusGlossary ? dlg.querySelector("#gl-find") : dlg.querySelector("#help-close")).focus();
  };
  /* ---------- Popover (WhyPanel, the red health chip) ----------
     Non-modal: it sits next to its trigger in the DOM (so Tab moves from the trigger into it), is drawn fixed so no
     card or table clips it, takes focus when it opens, and closes on Esc (focus back to the trigger), on a click
     outside, on scroll, or when focus leaves it. */
  let open = null, popN = 0;
  SS.closePopover = (returnFocus) => {
    if (!open) return;
    const o = open; open = null;
    o.el.remove();
    o.trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", o.onKey, true);
    document.removeEventListener("pointerdown", o.onDown, true);
    window.removeEventListener("scroll", o.onScroll, true);
    window.removeEventListener("resize", o.onScroll);
    if (returnFocus && document.contains(o.trigger)) o.trigger.focus();
  };
  SS.popover = (trigger, { title, html }) => {
    const same = open && open.trigger === trigger;
    SS.closePopover(false);
    if (same) return; // a second click on the trigger closes it
    const id = `pop-${++popN}`;
    const el = document.createElement("div");
    el.className = "popover"; el.id = id; el.tabIndex = -1;
    el.setAttribute("role", "dialog"); el.setAttribute("aria-labelledby", `${id}-t`);
    el.innerHTML = `<p class="popover__title" id="${id}-t">${title}</p><div class="popover__body">${html}</div>`;
    // inside the ink app bar the popover would inherit its dark tone, so there it goes to the end of the page instead
    if (trigger.closest(".tone-dark")) document.body.append(el); else trigger.after(el);
    trigger.setAttribute("aria-expanded", "true"); trigger.setAttribute("aria-controls", id);
    const r = trigger.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight, m = 8;
    let top = r.bottom + m;
    if (top + h > innerHeight - m && r.top - h - m > m) top = r.top - h - m;
    el.style.left = `${Math.max(m, Math.min(r.left, innerWidth - w - m))}px`;
    el.style.top = `${top}px`;
    // Tab order (finding 25): the popover reads as if it sat right after its trigger, even when it lives at the end of
    // <body> (app-bar chips). Shift+Tab from its first stop closes it and returns to the trigger; Tab from its last stop
    // closes it and moves to the next stop after the trigger.
    const TABBABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const stops = (root) => [...root.querySelectorAll(TABBABLE)].filter((x) => x.getClientRects().length && !x.closest("[hidden], [inert]"));
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); SS.closePopover(true); return; }
      if (e.key !== "Tab" || !el.contains(document.activeElement)) return;
      const own = stops(el), first = own[0], last = own.at(-1), a = document.activeElement;
      if (e.shiftKey && (a === el || a === first)) { e.preventDefault(); SS.closePopover(true); return; }
      if (!e.shiftKey && (a === last || !own.length)) {
        e.preventDefault();
        const page = stops(document.body).filter((x) => !el.contains(x));
        const next = page[page.indexOf(trigger) + 1];
        SS.closePopover(false);
        (next || trigger).focus();
      }
    };
    const onDown = (e) => { if (!el.contains(e.target) && !trigger.contains(e.target)) SS.closePopover(false); };
    const onScroll = (e) => { if (e.type === "resize" || !el.contains(e.target)) SS.closePopover(false); };
    // focus leaving for anywhere else, including nowhere (relatedTarget null: the window or the page lost focus), closes it
    el.addEventListener("focusout", (e) => { if (!e.relatedTarget || (!el.contains(e.relatedTarget) && e.relatedTarget !== trigger)) SS.closePopover(false); });
    el.addEventListener("click", (e) => { if (e.target.closest("a[href^='#/']")) SS.closePopover(false); });
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onDown, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    open = { el, trigger, onKey, onDown, onScroll };
    el.focus();
  };
})();
