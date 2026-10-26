/* ShelfSync mockup, P3.4 part B: Catalog, Product, Cleanup, Activity, Settings and the first-run wizard.
   Each screen registers render(state) and wire(state) on window.SS.screens. Sample data is in data-b.js.
   Nothing is saved and nothing is sent: every action shows a "Mockup: would…" toast or a ConfirmDialog. */
"use strict";
(() => {
  const SS = window.SS, B = window.SAMPLE_B;
  const { D, st, $, $$, esc, icon, store, storeBadge, fmt, time, n, TZ, pill, alert, sk, toast, mt } = SS;
  const render = (r) => SS.render(r);
  const sameDay = (t) => fmt({ dateStyle: "short" }).format(t) === fmt({ dateStyle: "short" }).format(D.NOW);
  const when = (t) => (sameDay(t) ? time(t) : `${fmt({ day: "numeric", month: "short" }).format(t)}, ${time(t)}`);
  const longDate = (t) => fmt({ day: "numeric", month: "long", year: "numeric" }).format(t);
  const s3Badge = `<span class="store-badge">${icon("hard-drive")}S3</span>`;
  const where = (w) => (w === "S3" ? s3Badge : store(w) ? storeBadge(w) : w === "GF and PW" ? `${storeBadge("GF")} ${storeBadge("PW")}` : `<span class="muted">${esc(w)}</span>`);
  const WHO = { you: ["user-check", "You"], auto: ["bot", "Auto-rule"], rule: ["bot", "Rule: keep 1"], outside: ["store", "Outside ShelfSync"] };
  const who = (k) => `<span class="who">${icon(WHO[k][0])}${WHO[k][1]}</span>`;
  const kindOf = (x) => (/\.zip$|\/$|-/.test(x) ? "mono" : "num"); // files, folders and slugs in Plex Mono; versions in tabular sans
  const vchange = (from, to) => `<span class="vchange mono-change">${from ? `<span class="${kindOf(from)} is-old">${esc(from)}</span>${to ? `${icon("arrow-right")}<span class="sr-only">to</span>` : ""}` : ""}${to ? `<span class="${kindOf(to)}">${esc(to)}</span>` : ""}</span>`;
  const head = (title, sub, actions = "") => `<div class="page-head"><div><h1 class="page-title" tabindex="-1">${title}</h1>${sub ? `<p class="page-sub">${sub}</p>` : ""}</div>
    <div class="page-head__end">${actions}${SS.sampleTag}</div></div>`;
  const mockBtn = (label, ic, mock, cls = "") => `<button class="btn ${cls}" type="button" data-mock="${esc(mock)}">${ic ? icon(ic) : ""}${label}</button>`;
  const empty = (ic, text, sub, action = "") => `<div class="empty is-center"><span class="empty__icon">${icon(ic, "i-lg")}</span><p class="empty__text">${text}</p>${sub ? `<p class="empty__sub">${sub}</p>` : ""}${action}</div>`;
  const testConn = (name) => ({ label: "Test connection", icon: "plug", mock: `Would test the ${name} connection. Nothing was sent.` });
  const ERR01 = {
    GF: () => alert("danger", "triangle-alert", "GPLFamily can't be reached: HTTP 401 (the Shop Manager key was refused).", "Updates for it are waiting.", testConn("GPLFamily")),
    PW: () => alert("danger", "triangle-alert", "PluginWay can't be reached: HTTP 524 (Cloudflare timeout).", "Updates for it are waiting.", testConn("PluginWay")),
  };
  const skRows = (count, cols) => Array.from({ length: count }, () => `<div class="sk-row" style="grid-template-columns:${cols}">${cols.split(" ").map(() => sk("80%")).join("")}</div>`).join("");
  const field = (id, label, control, hint) => `<div class="field"><label class="field__label" for="${id}">${label}</label>${control}${hint ? `<p class="field__hint" id="${id}-hint">${hint}</p>` : ""}</div>`;
  // cls adds classes to the one class attribute (a second class attribute in attrs would be ignored, finding 3a)
  const input = (id, value, attrs = "", cls = "") => `<input class="input${cls ? ` ${cls}` : ""}" id="${id}" value="${esc(value)}" ${attrs}>`;
  const sw = (id, label, on, hint, attrs = "") => `<div class="switch-row"><div><label class="switch-row__label" for="${id}">${label}</label>${hint ? `<p class="field__hint">${hint}</p>` : ""}</div>
    <input class="toggle" type="checkbox" role="switch" id="${id}" ${on ? "checked" : ""} ${attrs}></div>`;
  const secret = (id, label, masked) => `<div class="field secret-field" data-secret="${id}"><span class="field__label" id="${id}-l">${label}</span>
    <div class="secret-field__row"><span class="mono secret-field__value" aria-labelledby="${id}-l">${esc(masked)}</span><button class="btn is-compact" type="button" data-replace="${id}">${icon("key-round")}Replace</button></div>
    <div class="secret-field__edit" hidden><label class="sr-only" for="${id}-new">New ${label.toLowerCase()}</label>
      <input class="input mono" id="${id}-new" type="password" autocomplete="off" spellcheck="false" placeholder="Paste the new value">
      <button class="btn is-compact is-primary" type="button" data-secret-save="${id}">Save</button><button class="btn is-compact" type="button" data-secret-cancel="${id}">Cancel</button></div>
    <p class="field__hint">Kept in Windows Credential Manager. It's never shown again or sent to this page.</p></div>`;
  function wireSecrets(root = document) {
    $$("[data-replace]", root).forEach((b) => b.addEventListener("click", () => {
      const f = b.closest(".secret-field"); f.querySelector(".secret-field__edit").hidden = false; b.hidden = true; f.querySelector("input").focus();
    }));
    const close = (f) => { const e = f.querySelector(".secret-field__edit"); e.hidden = true; f.querySelector("input").value = ""; const b = f.querySelector("[data-replace]"); b.hidden = false; b.focus(); };
    $$("[data-secret-cancel]", root).forEach((b) => b.addEventListener("click", () => close(b.closest(".secret-field"))));
    $$("[data-secret-save]", root).forEach((b) => b.addEventListener("click", () => {
      const f = b.closest(".secret-field"), label = f.querySelector(".field__label").textContent;
      close(f); toast(`Replace ${label.toLowerCase()}`, "Would store the new value in Windows Credential Manager. Nothing was sent or saved.", true);
    }));
  }
  const chipToggle = (group, items, active) => `<div class="filter-chips" role="group" aria-label="${group}">${items.map(([k, label, count]) =>
    `<button class="filter-chip" type="button" data-chip="${k}" aria-pressed="${k === active}">${label}${count !== undefined ? ` <span class="num">${n(count)}</span>` : ""}</button>`).join("")}</div>`;

  /* ======================= Catalog (UI-CAT) ======================= */
  // the virtual table's row height: 3.5rem, read from the root font size so it follows the user's text size
  const rowH = () => 3.5 * parseFloat(getComputedStyle(document.documentElement).fontSize);
  let ROW_H = 56;
  const healthPill = (h) => ({
    instep: `<span class="band-pill is-success">${icon("circle-check")}In step</span>`,
    partial: SS.pill("partial"),
    stale: `<span class="band-pill is-warning">${icon("database")}Stale key</span>`,
    outside: `<span class="band-pill is-held">${icon("shield-alert")}Changed outside</span>`,
    nearmiss: `<span class="band-pill is-neutral">${icon("link")}Near-miss twin</span>`,
  }[h]);
  function storeCell(r, code) {
    const v = r.v[code];
    if (!v) return `<span class="sc is-none" title="Not on ${esc(store(code).name)}">–<span class="sr-only">not on ${esc(store(code).name)}</span></span>`;
    const other = r.v[code === "GF" ? "PW" : "GF"];
    const behind = other && v !== other && r.health === "partial" && code === "PW";
    return `<span class="sc${behind ? " is-behind" : ""}">${behind ? icon("triangle-alert") : icon("circle-check")}<span class="num">${v}</span>${behind ? '<span class="sr-only">, not in step</span>' : ""}</span>`;
  }
  let catRows = B.rows, searchMs = 0;
  function filterRows() {
    const q = (st.extra.q || "").trim().toLowerCase(), f = st.extra.f || "all";
    const t0 = performance.now();
    catRows = B.rows.filter((r) => {
      if (!B.filters(r)[f]) return false;
      if (!q) return true;
      return r.name.toLowerCase().includes(q) || r.slug.includes(q) || `${r.slug}-${r.v.GF || r.v.PW}.zip`.includes(q) || Object.values(r.ids).some((id) => String(id) === q);
    });
    if (st.extra.sort === "updated") catRows = [...catRows].sort((a, b) => b.updated - a.updated);
    searchMs = performance.now() - t0;
  }
  function catalog(state) {
    const actions = `${mockBtn("Sync now", "refresh-cw", "Would start an incremental sync of both stores. Nothing was sent.")}
      ${mockBtn("Export CSV", "download", "Would save catalog-2026-10-26.csv with every product. Nothing was saved.")}`;
    const top = head("Catalog", state === "empty" ? "" : `<span class="num">${n(B.rows.length)}</span> products on GPLFamily and PluginWay.`, state === "empty" ? "" : actions);
    if (state === "empty") return `<div class="page">${top}<section class="card">${empty("store", "Add your first store to start.", "The catalog fills in from your stores' downloadable products.", `<a class="btn is-primary" href="#/settings/stores">${icon("plus")}Add a store</a>`)}</section></div>`;
    const counts = { all: 0, theme: 0, plugin: 0, notinstep: 0, onestore: 0, week: 0 };
    B.rows.forEach((r) => { const f = B.filters(r); for (const k in counts) if (f[k]) counts[k]++; });
    const tools = state === "loading" ? `<div class="toolbar">${sk("22rem", "t-lg")}${sk("30rem", "t-lg")}</div>`
      : `<div class="toolbar"><div class="search-field">${icon("search")}<label class="sr-only" for="cat-q">Search the catalog</label>
          <input class="input" id="cat-q" type="search" autocomplete="off" placeholder="Name, slug, file or product ID" value="${esc(st.extra.q || "")}"></div>
          ${chipToggle("Filter products", [["all", "All", counts.all], ["theme", "Themes", counts.theme], ["plugin", "Plugins", counts.plugin], ["notinstep", "Not in step", counts.notinstep], ["onestore", "On one store", counts.onestore], ["week", "Updated this week", counts.week]], st.extra.f || "all")}</div>`;
    const err = state === "error" ? ERR01.GF() : "";
    const body = state === "loading" ? `<div class="vtable" aria-busy="true"><div class="vtable__head">${sk("40%")}</div>${skRows(9, "3fr 1fr 1fr 1fr 1fr 1.2fr 1.3fr")}</div>`
      : `<p class="result-line" id="cat-result" role="status"></p><div id="cat-body">${catBody()}</div>`;
    return `<div class="page">${top}<section class="card">${tools}${err ? `<div class="card-alert">${err}</div>` : ""}${body}</section></div>`;
  }
  // the table part only: a search or filter redraws this, never the whole shell (finding 22)
  function catBody() {
    filterRows();
    if (!catRows.length) {
      return `<div class="empty">${icon("search-x", "i-lg empty__icon")}<p class="empty__text">No products match “${esc((st.extra.q || "").trim())}”${st.extra.f && st.extra.f !== "all" ? " with this filter" : ""}.</p><button class="btn" type="button" id="cat-clear">${icon("x")}Clear search and filter</button></div>`;
    }
    const sorted = (k) => st.extra.sort === k || (!st.extra.sort && k === "name");
    const sortBtn = (k, label) => `<button class="sort-btn" type="button" data-sort="${k}" aria-label="${label}, sort">${label}${icon(sorted(k) ? "arrow-down" : "arrow-up-down")}</button>`;
    const ariaSort = (k) => (sorted(k) ? (k === "name" ? "ascending" : "descending") : "none");
    return `<div class="vtable" role="table" aria-label="Catalog" aria-rowcount="${catRows.length + 1}" aria-describedby="cat-result">
        <div class="vtable__head" role="row" aria-rowindex="1">
          <span role="columnheader" aria-sort="${ariaSort("name")}">${sortBtn("name", "Product")}</span>
          <span role="columnheader">Type</span>
          <span role="columnheader">${storeBadge("GF")}</span><span role="columnheader">${storeBadge("PW")}</span>
          <span role="columnheader">Slots</span>
          <span role="columnheader" aria-sort="${ariaSort("updated")}">${sortBtn("updated", "Last update")}</span>
          <span role="columnheader">Health</span></div>
        <div class="vtable__scroll" id="cat-scroll" tabindex="-1"><div class="vtable__space" id="cat-space" role="rowgroup"></div></div>
      </div>
      <p class="vtable__foot muted" id="cat-foot"></p>`;
  }
  function catRow(r, i) {
    return `<a class="vrow" role="row" aria-rowindex="${i + 2}" href="#/product?id=${encodeURIComponent(r.id)}" style="top:${i * ROW_H}px" data-i="${i}">
      <span role="cell" class="vrow__name"><span class="trunc" title="${esc(r.name)}">${esc(r.name)}</span><span class="mono muted trunc">${esc(r.slug)}</span></span>
      <span role="cell" class="muted">${r.type}</span>
      <span role="cell">${storeCell(r, "GF")}</span><span role="cell">${storeCell(r, "PW")}</span>
      <span role="cell" class="num">${r.slots}</span>
      <span role="cell" class="num">${when(r.updated)}</span>
      <span role="cell">${healthPill(r.health)}</span></a>`;
  }
  let catTimer = 0, actTimer = 0;
  // a pending debounced redraw never runs after the screen has changed (finding 27)
  SS.beforeRender = () => { clearTimeout(catTimer); clearTimeout(actTimer); };
  function refreshCat(focusSel) {
    if (!$("#cat-body")) return;
    $("#cat-body").innerHTML = catBody();
    wireCatBody();
    SS.writeHash();
    if (focusSel) $(focusSel)?.focus();
  }
  function wireCatalog(state) {
    const q = $("#cat-q");
    if (!q || state === "loading") return;
    q.addEventListener("input", () => {
      st.extra.q = q.value;
      clearTimeout(catTimer);
      catTimer = setTimeout(() => refreshCat(), 150); // debounced; the field isn't redrawn, so focus and caret stay put
    });
    $$(".filter-chip").forEach((c) => c.addEventListener("click", () => {
      st.extra.f = c.dataset.chip;
      $$(".filter-chip").forEach((x) => x.setAttribute("aria-pressed", String(x === c)));
      refreshCat();
    }));
    wireCatBody();
  }
  function wireCatBody() {
    $$(".sort-btn").forEach((b) => b.addEventListener("click", () => { st.extra.sort = b.dataset.sort === "name" ? "" : b.dataset.sort; refreshCat(`.sort-btn[data-sort="${b.dataset.sort}"]`); }));
    const qtext = (st.extra.q || "").trim();
    $("#cat-result").innerHTML = catRows.length
      ? `Showing <strong class="num">${n(catRows.length)}</strong> of <span class="num">${n(B.rows.length)}</span> products${qtext ? ` for “${esc(qtext)}”` : ""}. Times in ${TZ}. <span class="muted">Searched in ${searchMs < 1 ? "under 1" : Math.round(searchMs)} ms in this browser.</span>`
      : "";
    $("#cat-clear")?.addEventListener("click", () => {
      st.extra.q = ""; st.extra.f = "all";
      $("#cat-q").value = "";
      $$(".filter-chip").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.chip === "all")));
      refreshCat("#cat-q");
    });
    const sc = $("#cat-scroll");
    if (!sc) return;
    const space = $("#cat-space");
    ROW_H = rowH();
    space.style.height = `${catRows.length * ROW_H}px`;
    let last = "";
    const draw = () => {
      const start = Math.max(0, Math.floor(sc.scrollTop / ROW_H) - 4), end = Math.min(catRows.length, start + Math.ceil(sc.clientHeight / ROW_H) + 8);
      const key = `${start}-${end}`;
      if (key === last) return;
      last = key;
      const focusedI = document.activeElement?.classList.contains("vrow") ? document.activeElement.dataset.i : null;
      space.innerHTML = catRows.slice(start, end).map((r, k) => catRow(r, start + k)).join("");
      $("#cat-foot").textContent = `Rows ${n(start + 1)}–${n(end)} of ${n(catRows.length)} are in the page now; the rest render as you scroll.`;
      if (focusedI !== null) space.querySelector(`[data-i="${focusedI}"]`)?.focus({ preventScroll: true });
    };
    sc.addEventListener("scroll", draw, { passive: true });
    draw();
    space.addEventListener("keydown", (e) => {
      const row = e.target.closest(".vrow");
      if (!row || !["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const i = Number(row.dataset.i), to = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : e.key === "Home" ? 0 : catRows.length - 1;
      if (to < 0 || to >= catRows.length) return;
      const top = to * ROW_H;
      if (top < sc.scrollTop) sc.scrollTop = top; else if (top + ROW_H > sc.scrollTop + sc.clientHeight) sc.scrollTop = top + ROW_H - sc.clientHeight;
      last = ""; draw();
      space.querySelector(`[data-i="${to}"]`)?.focus({ preventScroll: true });
    });
  }
  SS.screens.catalog = { title: "Catalog", render: catalog, wire: wireCatalog };

  /* ======================= Product (UI-PRD) ======================= */
  // the version before v, for sample rows without one; x.0.0 steps back a major version (finding 13)
  const prevVer = (v) => {
    const p = v.split(".").map(Number);
    if (p[2] > 0) p[2]--; else if (p[1] > 0) { p[1]--; p[2] = 9; } else if (p[0] > 1) { p[0]--; p[1] = 9; p[2] = 4; } else return "0.9.8";
    return p.join(".");
  };
  function productData() {
    const r = B.rows.find((x) => x.id === st.productId) || B.rows.find((x) => x.id === "copperline");
    if (r.id === "copperline") return { r, d: { ...B.copperline, slots: B.copperline.slots.map((sl) => ({ ...sl, byStore: Object.fromEntries(r.stores.map((c) => [c, sl.current])) })) } };
    const v = r.v.GF || r.v.PW, pv = r.prev || prevVer(v);
    const file = (x) => `${r.slug}-${x}.zip`;
    // per store: a partial product keeps each store's own current file (finding 6)
    const byStore = Object.fromEntries(r.stores.map((c) => [c, file(r.v[c] || v)]));
    const snapAt = [B.day(0, 2.2), B.day(1, 2.2)];
    const d = {
      canonical: r.slug,
      storeCards: r.stores.map((code) => ({ code, productId: r.ids[code], state: r.health === "partial" && code === "PW" ? "behind" : "instep", read: B.min(14) })),
      slots: Array.from({ length: r.slots }, (_, k) => ({ name: k ? "Legacy" : "Download", ids: Object.fromEntries(r.stores.map((c) => [c, k + 1])), current: k ? file(pv) : file(v), previous: k ? null : file(pv),
        byStore: k ? Object.fromEntries(r.stores.map((c) => [c, file(pv)])) : byStore })),
      fingerprints: [{ kind: "Folder", value: `${r.slug}/`, source: "learned from current file", at: B.day(61) }],
      history: [{ at: r.updated, what: "Updated", from: `${r.slug}-${pv}.zip`, to: `${r.slug}-${v}.zip`, where: r.health === "partial" ? "GF" : r.stores.length === 2 ? "GF and PW" : r.stores[0], who: "you" }],
      stale: [],
      // a nightly snapshot taken before the last update holds the previous file
      snapshots: snapAt.map((at) => ({ at, files: r.updated > at ? file(pv) : file(v) })),
      s3: [`${r.slug}-${v}.zip`, `${r.slug}-${pv}.zip`],
    };
    return { r, d };
  }
  function product(state) {
    const { r, d } = productData();
    const back = `<a class="back-link" href="#/catalog">${icon("chevron-left")}Catalog</a>`;
    if (state === "loading") {
      return `<div class="page">${back}${head(sk("16rem", "t-lg"), sk("10rem"))}<div class="product-grid" aria-busy="true">
        <div class="stack">${[1, 2, 3].map(() => `<section class="card"><div class="card__body">${sk("30%")}<div class="gap-3"></div>${sk("90%")}<div class="gap-2"></div>${sk("70%")}</div></section>`).join("")}</div>
        <div class="stack">${[1, 2].map(() => `<section class="card"><div class="card__body">${sk("40%")}<div class="gap-3"></div>${sk("100%")}<div class="gap-2"></div>${sk("80%")}</div></section>`).join("")}</div></div></div>`;
    }
    const isEmpty = state === "empty";
    const cur = d.slots[0];
    const down = state === "error" ? "PW" : null;
    const actions = `${cur.previous ? `<button class="btn" type="button" id="act-rollback">${icon("rotate-ccw")}Roll back to ${esc(cur.previous.replace(`${r.slug}-`, "").replace(".zip", ""))}</button>` : ""}
      <button class="btn" type="button" id="act-restore">${icon("calendar-clock")}Restore to date</button>
      <button class="btn" type="button" id="act-manual">${icon("file-pen")}Set file manually</button>`;
    const health = healthPill(r.health) || "";
    const top = `${back}<div class="page-head product-head"><div><h1 class="page-title product-title" tabindex="-1">${esc(r.name)}</h1>
        <p class="page-sub">${r.type}, <span class="mono">${esc(d.canonical)}</span> ${health}</p></div>
      <div class="page-head__end">${SS.sampleTag}</div></div><div class="action-row">${actions}</div>`;

    const storeCards = `<section class="card" aria-labelledby="pc-stores"><div class="card__head"><h2 class="card__title is-sm" id="pc-stores">Stores</h2></div>
      ${down ? `<div class="card-alert">${ERR01.PW()}</div>` : ""}
      <div class="link-cards">${d.storeCards.map((c) => {
        const s = store(c.code), isDown = down === c.code;
        const statePill = isDown ? `<span class="band-pill is-danger">${icon("triangle-alert")}Can't reach</span>` : c.state === "instep" ? `<span class="band-pill is-success">${icon("circle-check")}In step</span>` : SS.pill("partial");
        return `<div class="link-card"><div class="link-card__top">${storeBadge(c.code, true)}<span class="link-card__name">${s.name}</span>${statePill}</div>
          <dl class="kv"><div><dt>Product ID</dt><dd class="num">${c.productId}</dd></div><div><dt>${isDown ? "Last read" : "Read"}</dt><dd class="num">${time(c.read)}</dd></div></dl>
          <a href="#" data-mock="Would open ${esc(r.name)} on ${esc(s.name)} in your browser.">Open on ${s.name}${icon("external-link")}</a></div>`;
      }).join("")}${r.stores.length < 2 ? `<div class="link-card is-missing"><p class="muted">Not on ${r.stores[0] === "GF" ? "PluginWay" : "GPLFamily"}.</p>${r.health === "nearmiss" ? '<a href="#/cleanup">A near-miss twin is waiting in Cleanup</a>' : ""}</div>` : ""}</div></section>`;

    const slots = `<section class="card" aria-labelledby="pc-slots"><div class="card__head"><h2 class="card__title is-sm" id="pc-slots">Slots</h2></div>
      <ul class="slot-list">${d.slots.map((sl, k) => `<li><div class="slot-list__head"><strong>${sl.name}</strong>${k === 0 ? '<span class="muted">main slot</span>' : ""}
          <span class="muted num slot-ids">Download ID ${Object.entries(sl.ids).map(([c, id]) => `${id} on ${c}`).join(", ")}</span></div>
        <dl class="kv">${new Set(Object.values(sl.byStore)).size > 1
          ? Object.entries(sl.byStore).map(([c, f]) => `<div><dt class="kv-store">Current on ${storeBadge(c)}</dt><dd class="mono">${esc(f)}</dd></div>`).join("")
          : `<div><dt>Current file</dt><dd class="mono">${esc(sl.current)}</dd></div>`}${sl.previous ? `<div><dt>Previous file</dt><dd class="mono muted">${esc(sl.previous)}</dd></div>` : ""}</dl></li>`).join("")}</ul></section>`;

    const fps = isEmpty ? [] : d.fingerprints;
    const fingerprints = `<section class="card" aria-labelledby="pc-fp"><div class="card__head"><h2 class="card__title is-sm" id="pc-fp">Fingerprints</h2></div>
      ${fps.length ? `<ul class="fp-list">${fps.map((f, k) => `<li>${icon("fingerprint-pattern")}<div><span class="muted fp-kind">${f.kind}</span><span${f.kind === "Folder" ? ' class="mono"' : ""}>${esc(f.value)}</span></div>
          <span class="fp-source">${f.source}, ${longDate(f.at)}</span><button class="btn is-compact" type="button" data-fp="${k}">${icon("trash-2")}Remove</button></li>`).join("")}</ul>`
        : `<div class="empty">${icon("fingerprint-pattern", "i-lg empty__icon")}<p class="empty__text">No fingerprints yet. Approving a match in Review, or teaching from current files, adds one.</p></div>`}</section>`;

    const slug = `<section class="card" aria-labelledby="pc-slug"><div class="card__head"><h2 class="card__title is-sm" id="pc-slug">Canonical slug</h2></div><div class="card__body">
      <div class="inline-form"><label class="sr-only" for="slug-in">Canonical slug</label>${input("slug-in", d.canonical, 'spellcheck="false" aria-describedby="slug-in-hint"', "mono")}
        <button class="btn" type="button" id="slug-save">${icon("save")}Save slug</button></div>
      <p class="field__hint" id="slug-in-hint">ShelfSync names this product's files with it: <span class="mono">${esc(d.canonical)}-&lt;version&gt;.zip</span>. Renaming changes only future file names.</p></div></section>`;

    const hist = isEmpty ? [] : d.history;
    const history = `<section class="card" aria-labelledby="pc-hist"><div class="card__head"><h2 class="card__title is-sm" id="pc-hist">History</h2><a class="card__link" href="#/activity">All in Activity${icon("chevron-right")}</a></div>
      ${hist.length ? `<ol class="timeline">${hist.map((h) => `<li><span class="timeline__when num">${when(h.at)}</span><div class="timeline__what"><p><strong>${esc(h.what)}</strong>${h.where && h.where !== "Catalog" ? ` <span class="muted">on</span> ${where(h.where)}` : ""}</p>
          ${h.to ? vchange(h.from, h.to) : ""}<p class="muted">${who(h.who)}</p></div></li>`).join("")}</ol><p class="field__hint card-foot">Times in ${TZ}.</p>`
        : `<div class="empty">${icon("history", "i-lg empty__icon")}<p class="empty__text">No changes yet. Every change ShelfSync makes to this product appears here.</p></div>`}</section>`;

    const staleRows = isEmpty ? [] : d.stale;
    const stale = `<section class="card" aria-labelledby="pc-stale"><div class="card__head"><h2 class="card__title is-sm" id="pc-stale">Stale store data</h2></div><div class="card__body">
      ${staleRows.length ? `<ul class="stale-list">${staleRows.map((s) => `<li>${storeBadge(s.code)}<span class="mono">${esc(s.key)}</span><span class="muted">= <span class="num">${esc(s.value)}</span></span></li>`).join("")}</ul>
        <p class="field__hint">A version key for an old slug. <a href="#/cleanup">Remove it in Cleanup</a></p>` : `<p class="muted">None. Both stores match ShelfSync's record.</p>`}</div></section>`;

    return `<div class="page">${top}<div class="product-grid"><div class="stack">${storeCards}${slots}${fingerprints}</div><div class="stack">${slug}${history}${stale}</div></div></div>`;
  }
  function wireProduct(state) {
    if (state === "loading") return;
    const { r, d } = productData();
    const cur = d.slots[0], stores = r.stores;
    // one plan row per store that would change; a store already on the target file is left out and named in the note
    const plan = (to) => {
      const change = stores.filter((c) => cur.byStore[c] !== to), same = stores.filter((c) => cur.byStore[c] === to);
      const where = change.length === 2 ? "both stores" : change.length ? store(change[0]).name : "";
      const sameNote = same.length ? ` ${same.map((c) => store(c).name).join(" and ")} already offers ${to}, so it doesn't change.` : "";
      return { rows: change.map((c) => ({ target: c, label: `${cur.name} slot`, from: cur.byStore[c], to })), change, where, sameNote };
    };
    $("#slug-save")?.addEventListener("click", () => toast("Save slug", `Would rename the canonical slug to ${$("#slug-in").value}. Only future file names change. Nothing was saved.`, true));
    $("#act-rollback")?.addEventListener("click", (e) => {
      const pv = cur.previous.replace(`${r.slug}-`, "").replace(".zip", "");
      const p = plan(cur.previous);
      SS.confirm({ opener: e.currentTarget, title: `Roll back ${r.name} to ${pv}?`,
        lead: "ShelfSync first checks that the previous file is still in S3, then points each store back at it and reads the store back.",
        plan: [{ target: "S3", label: "check", check: cur.previous }, ...p.rows],
        note: `This points ${p.where} back to ${cur.previous}.${p.sameNote} You can roll forward again from History.`,
        confirm: `Roll back to ${pv}`, done: `Would roll ${r.name} back to ${cur.previous} on ${p.change.join(" and ")}. Nothing was sent.` });
    });
    $("#act-restore")?.addEventListener("click", (e) => {
      const opts = d.snapshots.map((s, k) => `<label class="radio-row"><input type="radio" name="snap" value="${k}" ${k === 0 ? "checked" : ""}>
        <span><strong>${longDate(s.at)}, 02:00</strong><span class="mono muted">${esc(s.files)}</span>${s.missing ? `<span class="is-wait">${icon("triangle-alert")}File no longer in S3</span>` : ""}</span></label>`).join("");
      SS.confirm({ opener: e.currentTarget, title: `Restore ${r.name} to a date`,
        lead: "Pick a nightly snapshot. ShelfSync puts the slots and version fields back as they were then.",
        body: `<fieldset class="radio-list"><legend class="sec-title">Snapshots (kept 30 days)</legend>${opts}</fieldset><div id="snap-block"></div>`,
        plan: [], note: "", confirm: "Restore", done: `Would restore ${r.name} to the chosen snapshot. Nothing was sent.`,
        wire: (dlg, api) => {
          const update = () => {
            const s = d.snapshots[Number(dlg.querySelector('input[name="snap"]:checked').value)];
            const label = `Restore to ${fmt({ day: "numeric", month: "short" }).format(s.at)}`;
            if (s.missing) {
              dlg.querySelector("#snap-block").innerHTML = alert("danger", "triangle-alert", `Can't restore: ${mt(s.files)} is no longer in S3.`, "", { label: "Set file manually", icon: "file-pen", mock: "Would open Set file manually for this slot." });
              api.setPlan([{ target: "S3", label: "check", wait: `${s.files} is missing` }]);
              api.setNote("Nothing will change on the stores.");
              api.setConfirm(label, false);
            } else {
              dlg.querySelector("#snap-block").innerHTML = "";
              const p = plan(s.files);
              api.setPlan([{ target: "S3", label: "check", check: s.files }, ...p.rows]);
              api.setNote(!p.change.length ? "The files already match this snapshot; only the version fields would be checked." : `This points ${p.where} at ${s.files}.${p.sameNote} You can roll forward again from History.`);
              api.setConfirm(label, true);
            }
          };
          dlg.addEventListener("change", update); update();
        } });
    });
    $("#act-manual")?.addEventListener("click", (e) => {
      SS.confirm({ opener: e.currentTarget, title: `Set the ${cur.name} file manually`,
        lead: "Choose the file this slot should offer. It goes through the same path as an upload: change plan, Windows Defender scan, store write, read-back.",
        body: `<fieldset class="radio-list"><legend class="sec-title">File</legend>
          <label class="radio-row"><input type="radio" name="src" value="s3" checked><span><strong>A file already in S3</strong>
            <select class="input mono" id="man-file" aria-label="File in S3">${d.s3.map((f) => `<option ${f === cur.previous ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></span></label>
          <label class="radio-row"><input type="radio" name="src" value="up"><span><strong>Upload a file</strong><span class="muted">A ZIP from this PC. It's scanned before anything is written.</span></span></label></fieldset>`,
        plan: [], note: "You can undo it with Roll back on this page. Activity records it as set manually by you.", confirm: "Set file",
        done: `Would set the ${cur.name} slot of ${r.name} on ${stores.join(" and ")}. Nothing was sent.`,
        wire: (dlg, api) => {
          const update = () => {
            const src = dlg.querySelector('input[name="src"]:checked').value, f = dlg.querySelector("#man-file").value;
            dlg.querySelector("#man-file").disabled = src !== "s3";
            const p = plan(f);
            api.setPlan(src === "s3" ? p.rows
              : [{ target: "S3", label: "upload", to: "the ZIP you choose, after its scan" }, ...stores.map((c) => ({ target: c, label: `${cur.name} slot`, from: cur.byStore[c], to: "the uploaded file" }))]);
            api.setNote(src === "s3" && !p.rows.length ? `Every store already offers ${f}, so nothing would change.`
              : `${src === "s3" ? p.sameNote.trim() + " " : ""}You can undo it with Roll back on this page. Activity records it as set manually by you.`.trim());
            api.setConfirm("Set file", src !== "s3" || p.rows.length > 0);
          };
          dlg.addEventListener("change", update); update();
        } });
    });
    $$("[data-fp]").forEach((b) => b.addEventListener("click", () => {
      const f = d.fingerprints[Number(b.dataset.fp)];
      // the past jobs come from this product's own history: its updates that matched a ZIP (finding 30)
      const jobs = d.history.filter((h) => h.what === "Updated" && h.to);
      SS.confirm({ opener: b, title: `Remove the fingerprint ${f.value}?`,
        lead: jobs.length ? "ZIPs that look like this stop matching this product on their own. These past jobs matched through it; they don't change."
          : "ZIPs that look like this stop matching this product on their own. No past job matched through it.",
        body: jobs.length ? `<ul class="plain-list">${jobs.map((h) => `<li><a href="#/activity"><span class="mono">${esc(h.to)}</span>, ${fmt({ day: "numeric", month: "short" }).format(h.at)}</a></li>`).join("")}</ul>` : "",
        confirm: "Remove fingerprint", danger: true, done: "Would remove the fingerprint. Nothing was sent." });
    }));
  }
  SS.screens.product = { title: "Product", render: product, wire: wireProduct };

  /* ======================= Cleanup (UI-CLN) ======================= */
  const dismissed = new Set();
  // the groups still showing; the nav badge, the Dashboard tile and the bulk action all count from this (finding 14)
  SS.cleanupGroups = () => B.cleanup.filter((g) => !dismissed.has(g.id));
  function issueItems(g) {
    if (g.id === "twins") return g.items.map((p, k) => `<li class="issue-item"><div class="pair">${storeBadge(p.a.code)}<span class="mono">${esc(p.a.slug)}</span>${icon("arrow-left-right")}<span class="sr-only">and</span>${storeBadge(p.b.code)}<span class="mono">${esc(p.b.slug)}</span></div>
      <p class="issue-item__why"><strong>${esc(p.title)}</strong>: ${mt(p.why)}.</p>
      <div class="issue-item__acts">${mockBtn("Link", "link", `Would link ${p.a.slug} and ${p.b.slug} as one product. You can undo it from Activity. Nothing was sent.`, "is-compact")}${mockBtn("Not the same", "unlink", `Would mark ${p.a.slug} and ${p.b.slug} as different products. Nothing was sent.`, "is-compact")}</div></li>`).join("");
    if (g.id === "stale") return g.items.map((s) => `<li class="issue-item"><div class="pair"><strong>${esc(s.product)}</strong>${storeBadge(s.code)}<span class="mono">${esc(s.key)}</span><span class="muted">= <span class="num">${s.value}</span></span></div>
      <div class="issue-item__acts">${mockBtn("Remove key", "trash-2", `Would remove ${s.key} on ${store(s.code).name}. Nothing was sent.`, "is-compact")}</div></li>`).join("");
    if (g.id === "outside") return g.items.map((o, k) => `<li class="issue-item"><div class="pair"><strong>${esc(o.product)}</strong>${storeBadge(o.code)}<span class="muted">${o.slot} slot, changed at <span class="num">${time(o.at)}</span></span></div>
      ${vchange(o.from, o.to)}
      <div class="issue-item__acts">${mockBtn("Accept the store's change", "check", `Would keep ${o.to} as ShelfSync's record. Activity records it. Nothing was sent.`, "is-compact")}
        <button class="btn is-compact" type="button" data-restore-outside="${k}">${icon("rotate-ccw")}Restore ShelfSync's file</button></div></li>`).join("");
    return g.items.map((f) => `<li class="issue-item"><div class="pair">${s3Badge}<span class="mono">${esc(f.file)}</span><span class="muted num">${f.size}, last changed ${longDate(f.modified)}</span></div>
      <div class="issue-item__acts"><button class="btn is-compact is-danger" type="button" data-delete-file="${esc(f.file)}">${icon("trash-2")}Delete from S3</button></div></li>`).join("");
  }
  function cleanup(state) {
    const groups = SS.cleanupGroups();
    const total = groups.reduce((a, g) => a + g.count, 0);
    const fixable = groups.filter((g) => g.bulk).reduce((a, g) => a + g.count, 0);
    const help = `<button class="btn is-ghost" type="button" id="cln-help">${icon("circle-help")}What do these mean?</button>`;
    if (state === "empty") return `<div class="page">${head("Cleanup", "", help)}<section class="card">${empty("brush-cleaning", "No issues. ShelfSync checks your stores every 15 minutes.", "Last check at " + time(D.lastSync) + ".", mockBtn("Sync now", "refresh-cw", "Would start an incremental sync of both stores. Nothing was sent."))}</section></div>`;
    if (state === "loading") return `<div class="page">${head("Cleanup", sk("14rem"), help)}<div class="stack" aria-busy="true">${[1, 2, 3].map(() => `<section class="card issue-card"><div class="card__body">${sk("30%", "t-lg")}<div class="gap-3"></div>${sk("85%")}<div class="gap-2"></div>${sk("60%")}<div class="gap-4"></div>${sk("100%")}</div></section>`).join("")}</div></div>`;
    const sub = `<span class="num">${total}</span> issues. ShelfSync checks your stores every 15 minutes; the last check was at ${time(D.lastSync)}.`;
    const bulk = fixable ? `<button class="btn is-primary" type="button" id="cln-bulk">${icon("list-checks")}Apply suggested fixes <span class="num">(${fixable})</span></button>` : "";
    const err = state === "error" ? `<div class="stack-alert">${ERR01.PW()}<p class="field__hint">Issues on PluginWay may be out of date until it's reachable.</p></div>` : "";
    const cards = groups.map((g) => `<section class="card issue-card" aria-labelledby="ig-${g.id}">
      <div class="card__head"><h2 class="card__title is-sm issue-card__title" id="ig-${g.id}">${icon(g.icon)}${g.kind}<span class="nav-count" aria-label="${g.count} issues">${g.count}</span></h2>
        <div class="issue-card__acts">${g.bulk ? mockBtn(g.bulk, g.id === "twins" ? "link" : "trash-2", `Would ${g.bulk.toLowerCase()}. Each one is recorded in Activity. Nothing was sent.`) : ""}
          <button class="btn is-ghost" type="button" data-dismiss="${g.id}">${icon("x")}Dismiss</button></div></div>
      <div class="card__body"><p class="issue-card__reason">${mt(g.reason)}</p><p class="issue-card__fix"><strong>Suggested fix:</strong> ${mt(g.fix)}</p></div>
      <ul class="issue-list">${issueItems(g)}</ul></section>`).join("");
    return `<div class="page">${head("Cleanup", sub, `${help}${bulk}`)}${err}<div class="stack">${cards || `<section class="card">${empty("brush-cleaning", "No issues. ShelfSync checks your stores every 15 minutes.")}</section>`}</div></div>`;
  }
  function wireCleanup() {
    $("#cln-help")?.addEventListener("click", (e) => SS.openHelp(e.currentTarget));
    $("#cln-bulk")?.addEventListener("click", () => {
      const left = SS.cleanupGroups(), g = (id) => left.find((x) => x.id === id);
      const did = [g("twins") && `link the ${g("twins").count} near-miss pairs`, g("stale") && `remove the ${g("stale").count} stale keys`].filter(Boolean).join(" and ");
      const wait = [g("outside") && "the changed-outside download", g("notours") && "the S3 file"].filter(Boolean);
      toast("Apply suggested fixes", `Would ${did}. Each is recorded in Activity.${wait.length ? ` ${wait.join(" and ").replace(/^./, (c) => c.toUpperCase())} wait${wait.length === 1 ? "s" : ""} for you.` : ""} Nothing was sent.`, true);
    });
    $$("[data-dismiss]").forEach((b) => b.addEventListener("click", () => {
      dismissed.add(b.dataset.dismiss);
      toast("Dismiss", "Hidden until it changes again. You can bring it back from Activity. Nothing was saved.", true);
      render(false);
      $("#main .page-title").focus(); // the card is gone; the page title (tabindex -1) takes focus
    }));
    // every button, each reading its own item (finding 33)
    $$("[data-restore-outside]").forEach((b) => b.addEventListener("click", (e) => {
      const o = B.cleanup.find((g) => g.id === "outside").items[Number(e.currentTarget.dataset.restoreOutside)];
      SS.confirm({ opener: e.currentTarget, title: `Restore ShelfSync's file for ${o.product}?`, lead: `PluginWay's ${o.slot} slot was changed outside ShelfSync.`,
        plan: [{ target: "S3", label: "check", check: o.from }, { target: o.code, label: `${o.slot} slot`, from: o.to, to: o.from }],
        note: `This points ${store(o.code).name} back at ${o.from}. Activity keeps the before and after.`, confirm: "Restore ShelfSync's file", done: `Would restore the file on ${store(o.code).name}. Nothing was sent.` });
    }));
    $$("[data-delete-file]").forEach((b) => b.addEventListener("click", (e) => {
      const f = e.currentTarget.dataset.deleteFile;
      SS.confirm({ opener: e.currentTarget, title: `Delete ${f} from S3?`, lead: `ShelfSync didn't upload ${f}. A fresh read of both stores found no download that points at it.`,
        plan: [{ target: "S3", label: "delete", from: f, to: "deleted" }], note: "This can't be undone.", confirm: "Delete from S3", danger: true, done: `Would delete ${f}. Nothing was sent.` });
    }));
  }
  SS.screens.cleanup = { title: "Cleanup", render: cleanup, wire: wireCleanup };

  /* ======================= Activity (UI-ACT) ======================= */
  const RANGES = [["today", "Today", 1], ["7d", "Last 7 days", 7], ["30d", "Last 30 days", 30], ["all", "All time", 99999]];
  function activityRows() {
    const range = RANGES.find((r) => r[0] === (st.extra.range || "7d"));
    const q = (st.extra.aq || "").trim().toLowerCase();
    return B.activity.filter((a) => {
      if (range[0] === "today" ? !sameDay(a.at) : D.NOW - a.at > range[2] * 86400000) return false;
      if (!q) return true;
      return [a.what, a.product, a.from, a.to].some((x) => x && x.toLowerCase().includes(q));
    });
  }
  function activity(state) {
    const actions = mockBtn("Export CSV", "download", "Would save activity-2026-10-26.csv with the rows shown. Nothing was saved.");
    if (state === "empty") return `<div class="page">${head("Activity")}<section class="card">${empty("history", "Nothing changed yet. Every change ShelfSync makes to a store or S3 appears here.", "", `<a class="btn" href="#/upload">${icon("upload")}Upload a ZIP</a>`)}</section></div>`;
    const tools = state === "loading" ? `<div class="toolbar">${sk("22rem", "t-lg")}${sk("24rem", "t-lg")}</div>`
      : `<div class="toolbar"><div class="search-field">${icon("search")}<label class="sr-only" for="act-q">Search Activity</label>
          <input class="input" id="act-q" type="search" autocomplete="off" placeholder="Product, file or change" value="${esc(st.extra.aq || "")}"></div>
          ${chipToggle("Time range", RANGES.map(([k, l]) => [k, l]), st.extra.range || "7d")}</div>`;
    const err = state === "error" ? `<div class="card-alert">${alert("danger", "triangle-alert", "PluginWay didn't respond (HTTP 524, Cloudflare timeout). Nothing was changed there.", "", { label: "Retry PluginWay", icon: "refresh-cw", mock: "Would retry the PluginWay write for stackmart-6.4.0.zip. Nothing was sent." })}</div>` : "";
    const body = state === "loading" ? `<div class="card__body" aria-busy="true">${skRows(8, "6rem 2fr 5rem 3fr 7rem")}</div>` : `<div id="act-body">${actBody()}</div>`;
    return `<div class="page">${head("Activity", "Every change ShelfSync makes to a store or S3, newest first.", actions)}<section class="card">${tools}${err}${body}</section></div>`;
  }
  // the result line and the table only: a search or range change redraws this, never the whole shell (finding 34)
  function actBody() {
    let body;
    {
      const rows = activityRows();
      const label = RANGES.find((r) => r[0] === (st.extra.range || "7d"))[1].toLowerCase();
      body = rows.length ? `<p class="result-line" role="status"><strong class="num">${rows.length}</strong> changes, ${label}. Times in ${TZ}.</p><div class="table-wrap"><table class="data-table act-table">
        <colgroup><col style="width:7.5rem"><col><col style="width:7rem"><col style="width:34%"><col style="width:10rem"></colgroup>
        <thead><tr><th scope="col">Time</th><th scope="col">What</th><th scope="col">Where</th><th scope="col"><span class="th-arrow">Before${icon("arrow-right")}<span class="sr-only">and</span>after</span></th><th scope="col">Who</th></tr></thead>
        <tbody>${rows.map((a) => `<tr${a.failed ? ' class="is-failed"' : ""}><td class="num">${when(a.at)}</td>
          <td><span class="act-what">${a.failed ? icon("triangle-alert", "res-icon-danger") : ""}<span><strong class="trunc" title="${esc(a.product)}">${esc(a.product)}</strong><span class="act-what__text">${mt(a.what)}</span></span></span>
            ${a.why ? SS.whyBtn(a.why) : ""}${a.failed ? mockBtn("Retry PluginWay", "refresh-cw", "Would retry the PluginWay write. Nothing was sent.", "is-compact") : ""}${a.undo ? mockBtn("Undo", "undo-2", "Would undo this change. Activity records the undo. Nothing was sent.", "is-compact is-ghost") : ""}</td>
          <td>${where(a.where)}</td><td>${a.from || a.to ? vchange(a.from, a.to) : '<span class="muted">–</span>'}</td><td>${who(a.who)}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty">${icon("search-x", "i-lg empty__icon")}<p class="empty__text">No changes match${st.extra.aq ? ` “${esc(st.extra.aq)}”` : ""} ${label}.</p><button class="btn" type="button" id="act-all">Show all time</button></div>`;
    }
    return body;
  }
  function refreshAct(focusSel) {
    if (!$("#act-body")) return;
    $("#act-body").innerHTML = actBody();
    wireActBody();
    SS.writeHash();
    if (focusSel) $(focusSel)?.focus();
  }
  function wireActBody() {
    $("#act-all")?.addEventListener("click", () => {
      st.extra.range = "all"; st.extra.aq = "";
      $("#act-q").value = "";
      $$(".filter-chip").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.chip === "all")));
      refreshAct("#act-q");
    });
  }
  function wireActivity(state) {
    const q = $("#act-q");
    if (!q || state === "loading") return;
    q.addEventListener("input", () => { st.extra.aq = q.value; clearTimeout(actTimer); actTimer = setTimeout(() => refreshAct(), 150); });
    $$(".filter-chip").forEach((c) => c.addEventListener("click", () => {
      st.extra.range = c.dataset.chip;
      $$(".filter-chip").forEach((x) => x.setAttribute("aria-pressed", String(x === c)));
      refreshAct();
    }));
    wireActBody();
  }
  SS.screens.activity = { title: "Activity", render: activity, wire: wireActivity };

  /* ======================= Settings (UI-SET) ======================= */
  const SUBNAV = [["stores", "Stores", "store"], ["storage", "Storage", "hard-drive"], ["rules", "Rules", "sliders-horizontal"], ["updates", "Updates", "refresh-ccw"], ["backup", "Backup", "archive"], ["app", "App", "app-window"]];
  const S = B.settings;
  // Reset access token (owner, 2026-10-26): the same words on the page and in its dialog
  const RESET_LINE = "Every open ShelfSync tab is signed out. Open ShelfSync again from the tray icon or the Start menu.";
  const save = (what) => `<div class="form-foot"><button class="btn is-primary" type="button" data-mock="Would save the ${what} settings. Nothing was saved.">${icon("save")}Save ${what}</button></div>`;
  function storesPage(state) {
    if (state === "empty") return `<section class="card">${empty("store", "Add your first store to start.", "You need its address and a Shop Manager key.", `<button class="btn is-primary" type="button" data-mock="Would open the Add a store form.">${icon("plus")}Add a store</button>`)}</section>`;
    return S.stores.map((s) => {
      const meta = store(s.code), bad = state === "error" && s.code === "GF";
      return `<section class="card store-card" aria-labelledby="sc-${s.code}">
      <div class="card__head"><h2 class="card__title is-sm store-card__title" id="sc-${s.code}">${storeBadge(s.code, true)}${s.name}${s.active ? `<span class="band-pill is-success">${icon("circle-check")}Active</span>` : ""}</h2>
        <div class="issue-card__acts">${mockBtn("Pause store", "pause", `Would pause ${s.name}. Its updates wait until you resume it. Nothing was saved.`)}${mockBtn("Remove", "trash-2", `Would ask before removing ${s.name}. Nothing was changed.`, "is-ghost")}</div></div>
      ${bad ? `<div class="card-alert">${ERR01.GF()}</div>` : ""}
      <div class="card__body form-grid">
        ${field(`url-${s.code}`, "Store address", input(`url-${s.code}`, s.url, 'type="url" spellcheck="false"'))}
        ${field(`btn-${s.code}`, "Main button name", input(`btn-${s.code}`, s.button))}
        ${secret(`ck-${s.code}`, "Consumer key", s.ck)}
        ${secret(`cs-${s.code}`, "Consumer secret", s.cs)}
        <div class="field"><span class="field__label">Identifier</span><div class="ident"><span class="ident__swatch">${SS.dot(meta)}</span><span>${meta.shape === "circle" ? "Circle" : "Square"}, code <strong>${s.code}</strong></span>
          <button class="btn is-compact" type="button" data-mock="Would open the colour and code picker. Each colour is checked for 3:1 on every surface.">${icon("pencil")}Change</button></div></div>
        ${field(`sp-${s.code}`, "Time between requests", `<div class="unit-input">${input(`sp-${s.code}`, s.spacing, 'inputmode="decimal"')}<span>seconds</span></div>`)}
      </div>
      <div class="test-row"><button class="btn" type="button" data-mock="Would test the ${s.name} connection. Nothing was sent.">${icon("plug")}Test connection</button>
        ${bad ? `<p class="test-result is-bad">${icon("triangle-alert")}<span>HTTP 401: the Shop Manager key was refused.</span></p>` : `<p class="test-result">${icon("circle-check")}<span>Connected in <span class="num">${meta.latency}</span> ms. WooCommerce ${s.wc}, <span class="num">${n(s.products)}</span> downloadable products.</span></p>`}
        <button class="btn is-ghost" type="button" data-help>${icon("book-open")}Shop Manager key guide</button></div></section>`;
    }).join("") + `<button class="btn" type="button" data-mock="Would open the Add a store form.">${icon("plus")}Add a store</button>`;
  }
  function storagePage(state) {
    const g = S.storage;
    if (state === "empty") return `<section class="card">${empty("hard-drive", "Add the S3 bucket ShelfSync uploads to.", "You need its name, region and two access keys: one that can write, one read-only.", `<button class="btn is-primary" type="button" data-mock="Would open the storage form.">${icon("plus")}Add storage</button>`)}</section>`;
    const bad = state === "error";
    return `<section class="card" aria-labelledby="st-h"><div class="card__head"><h2 class="card__title is-sm" id="st-h">${SS.icon("hard-drive")} Amazon S3</h2></div>
      ${bad ? `<div class="card-alert">${alert("danger", "triangle-alert", "S3 refused access: AccessDenied (the access key isn't allowed to write to this bucket).", "Uploads are held.", { label: "Test again", icon: "plug", mock: "Would test the storage connection. Nothing was sent." })}</div>` : ""}
      <div class="card__body form-grid">
        ${field("s3-end", "Endpoint", input("s3-end", g.endpoint, 'spellcheck="false"', "mono"))}
        ${field("s3-reg", "Region", input("s3-reg", g.region, 'spellcheck="false"', "mono"))}
        ${field("s3-bucket", "Bucket", input("s3-bucket", g.bucket, 'spellcheck="false"', "mono"))}
        ${field("s3-keep", "Previous files to keep", `<div class="unit-input">${input("s3-keep", g.keep, 'inputmode="numeric"')}<span>per slot</span></div>`, "Kept for rollback. Older files are deleted only after every store succeeded.")}
        ${secret("s3-rw", "Access key ID (read and write)", g.rw)}${secret("s3-rws", "Secret access key (read and write)", g.rwSecret)}
        ${secret("s3-ro", "Access key ID (read-only)", g.ro)}${secret("s3-ros", "Secret access key (read-only)", g.roSecret)}
        <div class="field span-2">${`<label class="field__label" for="s3-tpl">Download link template</label>${input("s3-tpl", g.template, 'spellcheck="false" aria-describedby="s3-tpl-hint"', "mono")}<p class="field__hint" id="s3-tpl-hint">What each store's download points at. <span class="mono">{key}</span> becomes the file name.</p>`}</div>
      </div>
      <div class="test-row"><button class="btn" type="button" data-mock="Would write a tiny test file under shelfsync-test/ with the read and write key, read it back with the read-only key, then delete it. Nothing was sent.">${icon("plug")}Test connection</button>
        ${bad ? `<p class="test-result is-bad">${icon("triangle-alert")}<span>Failed at the write step: the read and write key got AccessDenied.</span></p>` : `<p class="test-result">${icon("circle-check")}<span>Passed in <span class="num">${D.s3.latency}</span> ms.</span></p>`}
        <button class="btn is-ghost" type="button" data-help>${icon("book-open")}S3 access policy guide</button>
        ${s3Steps(bad)}
        <p class="field__hint test-row__hint">Each test writes a tiny file under <span class="mono">shelfsync-test/</span>, reads it back and deletes it: about 4 small S3 requests, a tiny AWS charge.</p></div>${save("storage")}</section>`;
  }
  const chipList = (id, label, items, mono, emptyHint) => `<div class="field span-2"><span class="field__label" id="${id}-l">${label}</span><ul class="edit-chips" aria-labelledby="${id}-l"${!items.length && emptyHint ? ` aria-describedby="${id}-h"` : ""}>${items.map((w) => `<li class="edit-chip${mono ? " mono" : ""}">${esc(w)}<button type="button" class="edit-chip__x" aria-label="Remove ${esc(w)}" data-mock="Would remove ${esc(w)} from the list. Nothing was saved.">${icon("x")}</button></li>`).join("")}
    <li><label class="sr-only" for="${id}-add">Add to ${label.toLowerCase()}</label><input class="input edit-chips__add" id="${id}-add" placeholder="Add…" autocomplete="off"></li></ul>${!items.length && emptyHint ? `<p class="field__hint" id="${id}-h">${emptyHint}</p>` : ""}</div>`;
  // the storage Test's three steps, each with its key, so a failure says which key failed and where (decision 2026-10-26)
  function s3Steps(bad) {
    const steps = [["Write a test file", "read and write key"], ["Read it back", "read-only key"], ["Delete it", "read and write key"]];
    return `<ol class="test-steps" aria-label="Test steps">${steps.map(([what, key], k) => {
      const state = !bad ? "ok" : k === 0 ? "bad" : "skip";
      const ic = state === "ok" ? icon("circle-check") : state === "bad" ? icon("triangle-alert") : icon("circle-dot");
      const word = state === "ok" ? "Passed" : state === "bad" ? "Failed: AccessDenied" : "Not run";
      return `<li class="is-${state}">${ic}<span>${what} <span class="muted">with the ${key}</span></span><strong>${word}</strong></li>`;
    }).join("")}</ol>`;
  }
  function rulesPage(state) {
    const R = S.rules, brakeOn = SS.brakeOn(), ramp = st.ramp === "ramp" && !brakeOn; // the brake can only trip after the trust ramp
    const first = state === "empty"; // first use: the starting rules, nothing added yet
    const brake = brakeOn ? `<div class="card-alert">${alert("warning", "pause", "Auto-apply paused: more than 30 updates in 10 minutes.", "Check the latest updates in Activity, then resume.", { label: "Resume auto-apply", icon: "play", mock: "Would resume auto-apply. Nothing was sent." })}</div>` : "";
    const starting = first ? `<div class="stack-alert">${alert("info", "info", "These are the starting rules. Nothing has been changed yet.", "Change them when Review shows a pattern they miss, such as a vendor's name at the start of its ZIPs.")}</div>` : "";
    return `${starting}<section class="card" aria-labelledby="ru-h"><div class="card__head"><h2 class="card__title is-sm" id="ru-h">Auto-apply and brakes</h2></div>${brake}
      <div class="card__body form-stack">
        ${sw("r-auto", "Auto-apply Certain ZIPs", !ramp, ramp ? "Stays off until the trust ramp reaches 50 (37 / 50 now)." : "Certain ZIPs with no guard apply without waiting in Review.", ramp ? 'aria-disabled="true" data-locked="Auto-apply turns on after the trust ramp reaches 50."' : "")}
        <div class="form-grid">
          ${field("r-fails", "Pause after this many failures in a row", input("r-fails", R.brakeFails, 'inputmode="numeric"'))}
          ${field("r-count", "Pause after more than this many auto-applies in 10 minutes", input("r-count", R.brakeCount, 'inputmode="numeric"'))}
        </div>
        <p class="locked-line">${icon("lock")}Downgrades are always held in Review.</p>
      </div></section>
      <section class="card" aria-labelledby="ru-m"><div class="card__head"><h2 class="card__title is-sm" id="ru-m">Matching</h2></div><div class="card__body form-grid">
        ${chipList("r-ed", "Edition words", R.edition)}
        ${chipList("r-vp", "Vendor prefixes", first ? [] : R.prefixes, false, "None yet. Add a vendor's name when its ZIPs start with it, like Nexa in <span class=\"mono\">nexa-wishlist-premium-3.4.0.zip</span>.")}
        ${chipList("r-bf", "Bundled-folder names", R.bundled, true)}
      </div></section>
      <section class="card" aria-labelledby="ru-z"><div class="card__head"><h2 class="card__title is-sm" id="ru-z">ZIPs and sync</h2></div><div class="card__body form-stack">
        ${sw("r-defender", "Scan every ZIP with Windows Defender", true, "Recommended. A ZIP with a threat is held and can only be discarded.")}
        <div class="form-grid">${R.limits.map(([l, v], k) => field(`r-lim${k}`, l, input(`r-lim${k}`, v))).join("")}
          ${field("r-sync", "Sync interval", `<select class="input" id="r-sync"><option>5 minutes</option><option selected>15 minutes</option><option>30 minutes</option><option>60 minutes</option></select>`)}</div>
      </div>${save("rules")}</section>`;
  }
  function updatesPage(state) {
    const U = S.updates;
    const days = Math.round((U.expires - D.NOW) / 86400000);
    if (state === "empty") return `<section class="card">${empty("refresh-ccw", "Add a read-only GitHub token to check for updates.", "ShelfSync only reads its own releases with it.", `<button class="btn is-primary" type="button" data-help>${icon("book-open")}How to make the token</button>`)}</section>`;
    const bad = state === "error";
    return `<section class="card" aria-labelledby="up-h"><div class="card__head"><h2 class="card__title is-sm" id="up-h">ShelfSync <span class="num">${U.version}</span></h2>
        <span class="muted">Last checked at <span class="num">${time(U.checked)}</span></span></div>
      ${bad ? `<div class="card-alert">${alert("danger", "triangle-alert", "Can't check for updates: token expired.", "Make a new read-only token, then replace it below.", { label: "How to make the token", icon: "book-open", mock: "Would open the GitHub token guide." })}</div>`
        : `<div class="card-alert">${alert("warning", "clock", `Your GitHub token expires in ${days} days, on ${longDate(U.expires)}.`, "Make a new one before then, or update checks stop.", { label: "How to make the token", icon: "book-open", mock: "Would open the GitHub token guide." })}</div>`}
      <div class="card__body form-stack">
        ${bad ? "" : `<div class="update-card"><div><p class="update-card__title">ShelfSync ${U.latest} is ready</p><p class="muted">Installs in under a minute; your data stays.</p></div>
          <div class="issue-card__acts">${mockBtn("Install now", "download", "Would install 1.2.0 beside 1.1.0 after checking its signature, then switch. Nothing was installed.", "is-primary")}${mockBtn("Later", "", "Would remind you at the next start.", "is-ghost")}</div></div>`}
        ${secret("u-token", "GitHub token (read-only)", U.token)}
        <div class="test-row is-flat">${mockBtn("Check now", "refresh-cw", "Would check GitHub for a newer release. Nothing was sent.")}
          <button class="btn" type="button" id="u-rollback">${icon("rotate-ccw")}Roll back to ${U.previous}</button>
          <fieldset class="mock-inline"><legend>${icon("flask-conical")}Mockup: did ${U.version} change the database?</legend>
            ${[["no", "No"], ["yes", "Yes"]].map(([v, l]) => `<label><input type="radio" name="db-changed" value="${v}" ${(st.extra.db || "no") === v ? "checked" : ""}>${l}</label>`).join("")}</fieldset></div>
      </div></section>`;
  }
  function backupPage(state) {
    const K = S.backup;
    const err = state === "error" ? `<div class="card-alert">${alert("danger", "triangle-alert", mt("Can't open shelfsync-export.ssbak: the passphrase doesn't match."), "Nothing was imported.", { label: "Try another passphrase", icon: "key-round", mock: "Would ask for the passphrase again." })}</div>` : "";
    return `<section class="card" aria-labelledby="bk-x"><div class="card__head"><h2 class="card__title is-sm" id="bk-x">Export and import</h2></div>${err}<div class="card__body form-stack">
        <p>One file with your settings and the catalog. Secrets are included only if you set a passphrase.</p>
        <label class="check-row"><input type="checkbox" id="bk-secrets"><span>Include secrets (needs a passphrase)</span></label>
        <div id="bk-pass" hidden>${field("bk-pp", "Passphrase", `<input class="input" id="bk-pp" type="password" autocomplete="new-password">`, "Without it the file holds no usable keys. ShelfSync can't recover it for you.")}</div>
        <div class="test-row is-flat">${mockBtn("Export", "download", "Would save shelfsync-export-2026-10-26.ssbak. Nothing was saved.", "is-primary")}${mockBtn("Import a file", "upload", "Would open the Windows file picker. Nothing was imported.")}</div></div></section>
      <section class="card" aria-labelledby="bk-k"><div class="card__head"><h2 class="card__title is-sm" id="bk-k">What's kept</h2></div><div class="card__body">
        ${state === "empty" ? `<p class="muted">No backups yet. The first runs tonight at 02:00.</p>` : `<p>Last database backup at <span class="num">${time(K.last)}</span> today, <span class="num">${K.size}</span>.</p>`}
        <div class="form-grid">${field("bk-snap", "Keep nightly snapshots for", `<div class="unit-input">${input("bk-snap", K.snapshots, 'inputmode="numeric"')}<span>days</span></div>`)}
          ${field("bk-db", "Database backups to keep", `<div class="unit-input">${input("bk-db", K.kept, 'inputmode="numeric"')}<span>daily copies</span></div>`)}</div></div>${save("backup")}</section>`;
  }
  function appPage(state) {
    const A = S.app;
    const err = state === "error" ? `<div class="card-alert">${alert("warning", "server", "Port 47615 is in use, so ShelfSync started on 47616.", "Open ShelfSync from the tray icon. The old address now reaches the other program.", null)}</div>` : "";
    const theme = st.theme;
    return `<section class="card" aria-labelledby="ap-h"><div class="card__head"><h2 class="card__title is-sm" id="ap-h">App</h2></div>${err}<div class="card__body form-stack">
        <fieldset class="radio-list is-inline"><legend class="field__label">Theme</legend>
          ${[["system", "Same as Windows", "monitor"], ["light", "Light", "sun"], ["dark", "Dark", "moon"]].map(([v, l, ic]) => `<label class="radio-row"><input type="radio" name="app-theme" value="${v}" ${theme === v ? "checked" : ""}>${icon(ic)}<span>${l}</span></label>`).join("")}</fieldset>
        ${sw("a-start", "Start with Windows", A.startWithWindows, "ShelfSync starts in the tray when you sign in to Windows.")}
        ${sw("a-notify", "Notifications", A.notifications, "A Windows notification when Review needs you or an update goes partial.")}
        <div class="form-grid">${field("a-port", "Port", input("a-port", A.port, 'inputmode="numeric"'), "If it's taken at start, ShelfSync uses the next free port up to 47624.")}
          ${field("a-logs", "Keep logs for", `<div class="unit-input">${input("a-logs", A.logDays, 'inputmode="numeric"')}<span>days</span></div>`)}</div>
        <div class="danger-zone"><div><p><strong>Reset access token</strong></p><p class="muted">Makes a new token for signing in to this page. ${RESET_LINE}</p></div>
          <button class="btn is-danger" type="button" id="a-reset">${icon("key-round")}Reset access token</button></div>
      </div>${save("app")}</section>`;
  }
  function settings(state) {
    const sub = st.sub;
    const nav = `<nav class="sub-nav" aria-label="Settings"><ul>${SUBNAV.map(([k, l, ic]) => `<li><a class="sub-nav__item" href="#/settings/${k}" ${k === sub ? 'aria-current="page"' : ""}>${icon(ic)}${l}</a></li>`).join("")}</ul></nav>`;
    const title = SUBNAV.find((x) => x[0] === sub)[1];
    let content;
    if (state === "loading") content = `<div class="stack" aria-busy="true">${[1, 2].map(() => `<section class="card"><div class="card__body">${sk("25%", "t-lg")}<div class="gap-4"></div><div class="form-grid">${[1, 2, 3, 4].map(() => `<div>${sk("40%")}<div class="gap-2"></div>${sk("100%", "t-lg")}</div>`).join("")}</div></div></section>`).join("")}</div>`;
    else content = `<div class="stack">${{ stores: storesPage, storage: storagePage, rules: rulesPage, updates: updatesPage, backup: backupPage, app: appPage }[sub](state)}</div>`;
    // the sub-page's own heading takes focus when the sub-nav changes page (finding 2)
    return `<div class="page">${head("Settings")}<div class="settings-grid">${nav}<div class="settings-main"><h2 class="settings-title" tabindex="-1" data-nav-focus>${title}</h2>${content}</div></div></div>`;
  }
  function wireSettings(state) {
    wireSecrets();
    $$("[data-help]").forEach((b) => b.addEventListener("click", () => SS.openHelp(b)));
    $$('input[name="app-theme"]').forEach((r) => r.addEventListener("change", () => { st.theme = r.value; render(false); $(`input[name="app-theme"][value="${r.value}"]`).focus(); }));
    const auto = $("#r-auto");
    if (auto && auto.getAttribute("aria-disabled") === "true") auto.addEventListener("click", (e) => { e.preventDefault(); toast("Auto-apply", auto.dataset.locked, true); });
    $("#r-defender")?.addEventListener("change", (e) => {
      const box = e.currentTarget;
      if (box.checked) return;
      box.checked = true; // stays on unless confirmed
      SS.confirm({ opener: box, title: "Turn off the Windows Defender scan?", lead: "New ZIPs would be uploaded and written to your stores without a scan. A ZIP with a threat would no longer be held.",
        note: "You can turn it back on here at any time.", confirm: "Turn off the scan", danger: true, done: "Would turn off the scan. Nothing was saved." });
    });
    $("#bk-secrets")?.addEventListener("change", (e) => { $("#bk-pass").hidden = !e.target.checked; if (e.target.checked) $("#bk-pp").focus(); });
    $("#a-reset")?.addEventListener("click", (e) => SS.confirm({ opener: e.currentTarget, title: "Reset the access token?", lead: "ShelfSync makes a new access token and the old one stops working.",
      note: RESET_LINE, confirm: "Reset access token", danger: true, done: "Would reset the token. Nothing was changed." }));
    $$('input[name="db-changed"]').forEach((r) => r.addEventListener("change", () => { st.extra.db = r.value; }));
    // Roll back app (decision 2026-10-26): the data stays when the update didn't change the database; if it did, the
    // backup from just before the update comes back and later changes are lost. Both wordings are shown through the mockup switch.
    $("#u-rollback")?.addEventListener("click", (e) => {
      const U = S.updates, migrated = (st.extra.db || "no") === "yes";
      const at = `${longDate(U.installed)} at ${time(U.installed)}`;
      SS.confirm({ opener: e.currentTarget, title: `Roll back ShelfSync to ${U.previous}?`,
        lead: `ShelfSync switches back to ${U.previous}, which is still installed beside ${U.version}, and restarts.`,
        // decision 131: the newer version can be installed again; changes lost to the restored backup can't be brought back
        body: migrated ? alert("warning", "database", `${U.version} changed the database.`, `ShelfSync restores the backup taken just before the update, on ${at}. Changes made since then are lost and can't be brought back.`) : "",
        note: `${migrated ? "" : `${U.version} didn't change the database, so your data stays as it is. `}You can install ${U.version} again from Settings › Updates.`,
        confirm: `Roll back to ${U.previous}`, danger: migrated, done: "Would roll the app back. Nothing was changed." });
    });
  }
  SS.screens.settings = { title: "Settings", render: settings, wire: wireSettings };

  /* ======================= First-run wizard (UI-WIZ) ======================= */
  const wiz = { stores: [{ code: "GF", name: "GPLFamily", url: "https://www.gplfamily.example" }], form: { name: "PluginWay", url: "https://www.pluginway.example", code: "PW" }, storage: { bucket: "shelfsync-sample-bucket", region: "eu-west-2" },
    typed: {}, saved: {} };
  const W = B.wizard;
  // A key or secret typed in the wizard goes to Windows Credential Manager when you leave the step (Continue, Back or the
  // rail). It never comes back to the page (06 section 3), so coming back shows it masked as Saved, with Replace (finding 4).
  const wizSecret = (id, label, placeholder = "") => wiz.saved[id]
    ? `<div class="field secret-field" data-secret="${id}"><span class="field__label" id="${id}-l">${label}</span>
      <div class="secret-field__row"><span class="mono secret-field__value" aria-labelledby="${id}-l">••••••••</span><span class="band-pill is-success">${icon("circle-check")}Saved</span>
        <button class="btn is-compact" type="button" data-replace="${id}">${icon("key-round")}Replace</button></div>
      <div class="secret-field__edit" hidden><label class="sr-only" for="${id}-new">New ${label.toLowerCase()}</label>
        <input class="input mono" id="${id}-new" type="password" autocomplete="off" spellcheck="false" placeholder="Paste the new value">
        <button class="btn is-compact is-primary" type="button" data-secret-save="${id}">Save</button><button class="btn is-compact" type="button" data-secret-cancel="${id}">Cancel</button></div></div>`
    : field(id, label, `<input class="input mono" id="${id}" type="password" autocomplete="off" spellcheck="false" placeholder="${placeholder}" data-wsecret="${id}">`);
  function wizard(state) {
    const step = st.wizStep;
    const rail = `<ol class="step-rail-wiz" aria-label="Setup steps">${W.steps.map((s, k) => `<li class="${k < step ? "is-done" : k === step ? "is-current" : ""}" ${k === step ? 'aria-current="step"' : ""}>
      ${k < step ? `<a href="#/wizard?step=${k + 1}"><span class="wiz-n">${icon("check")}</span>${s}<span class="sr-only">, done</span></a>` : `<span><span class="wiz-n num">${k + 1}</span>${s}</span>`}</li>`).join("")}</ol>`;
    const stores = state === "empty" ? [] : wiz.stores;
    let body = "", canContinue = true, title = "";
    if (step === 0) {
      title = "Add your stores";
      const err = state === "error" ? alert("danger", "triangle-alert", "PluginWay runs WooCommerce 5.6. ShelfSync needs 5.8 or newer.", "Update WooCommerce on PluginWay, then test again. Setup can't continue until every store passes.", { label: "Test again", icon: "plug", mock: "Would test PluginWay again. Nothing was sent." }) : "";
      if (state === "error") canContinue = false;
      body = `<p class="wiz-lead">ShelfSync needs each store's address and a Shop Manager key. It only reads until you approve a change.</p>
        ${stores.length ? `<ul class="wiz-stores">${stores.map((s) => `<li>${storeBadge(s.code, true)}<strong>${s.name}</strong><span class="mono muted">${esc(s.url)}</span><span class="band-pill is-success">${icon("circle-check")}Connected</span></li>`).join("")}</ul>`
          : `<p class="empty__text wiz-empty">${icon("store")}Add your first store to start.</p>`}
        ${err}
        <fieldset class="wiz-form"><legend class="sec-title">${stores.length ? "Add another store" : "Add a store"}</legend><div class="form-grid">
          ${field("w-name", "Store name", input("w-name", wiz.form.name, 'data-wf="name"'))}
          ${field("w-code", "Two-letter code", input("w-code", wiz.form.code, 'data-wf="code" maxlength="2"'), "Shown with a shape and colour wherever this store appears.")}
          <div class="field span-2">${`<label class="field__label" for="w-url">Store address</label>${input("w-url", wiz.form.url, 'type="url" data-wf="url" spellcheck="false"')}`}</div>
          ${wizSecret("w-ck", "Consumer key", "ck_…")}
          ${wizSecret("w-cs", "Consumer secret", "cs_…")}
        </div><div class="test-row is-flat"><button class="btn" type="button" data-mock="Would test the store and add it. Nothing was sent.">${icon("plug")}Test and add</button>
          <button class="btn is-ghost" type="button" data-help>${icon("book-open")}Shop Manager key guide</button></div></fieldset>`;
      if (!stores.length) canContinue = false;
    } else if (step === 1) {
      title = "Connect storage";
      body = `<p class="wiz-lead">The S3 bucket ShelfSync uploads ZIPs to. Use a key that can write, and a separate read-only key.</p><div class="form-grid">
        ${field("w-bucket", "Bucket", input("w-bucket", wiz.storage.bucket, 'data-ws="bucket" spellcheck="false"', "mono"))}
        ${field("w-region", "Region", input("w-region", wiz.storage.region, 'data-ws="region" spellcheck="false"', "mono"))}
        ${wizSecret("w-ak", "Access key ID (read and write)")}
        ${wizSecret("w-sk", "Secret access key (read and write)")}
        ${wizSecret("w-rak", "Access key ID (read-only)")}
        ${wizSecret("w-rsk", "Secret access key (read-only)")}
      </div><button class="btn is-ghost" type="button" data-help>${icon("book-open")}S3 access policy guide</button>`;
    } else if (step === 2) {
      title = "Test the connections";
      const rows = [["GF", "GPLFamily", "Connected in 182 ms. WooCommerce 9.3.2."], ["PW", "PluginWay", state === "error" ? null : "Connected in 241 ms. WooCommerce 9.1.4."], ["S3", "Amazon S3", "Wrote, read back and deleted the test file in 96 ms."]];
      if (state === "error") canContinue = false;
      body = `<p class="wiz-lead">Each store is read once. For the bucket, ShelfSync writes a tiny test file under <span class="mono">shelfsync-test/</span> with the read and write key, reads it back with the read-only key, then deletes it: about 4 small S3 requests, a tiny AWS charge.</p><ul class="wiz-tests">${rows.map(([c, name, ok]) => `<li>${c === "S3" ? s3Badge : storeBadge(c, true)}<strong>${name}</strong>
        ${ok ? `<span class="test-result">${icon("circle-check")}<span>${ok}</span></span>` : `<span class="test-result is-bad">${icon("triangle-alert")}<span>PluginWay returned no downloadable products.</span></span>`}</li>`).join("")}</ul>
        ${state === "error" ? alert("danger", "triangle-alert", "PluginWay returned no downloadable products.", "Check that the Shop Manager key belongs to the right store. Setup can't continue until every store passes.", { label: "Test again", icon: "plug", mock: "Would test PluginWay again. Nothing was sent." }) : ""}`;
    } else if (step === 3) {
      title = "Build the catalog";
      const loading = state === "loading";
      const prog = (c, name, total) => { const done = loading ? Math.round(total * (c === "GF" ? 1 : 0.58)) : total; const pct = Math.round((done / total) * 100);
        return `<li>${storeBadge(c, true)}<div class="wiz-prog"><p><strong>${name}</strong> <span class="num muted">${n(done)} of ${n(total)} products read</span></p>
          <div class="progress" role="progressbar" aria-label="Reading ${name}" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct}%"></span></div></div></li>`; };
      if (loading) canContinue = false;
      body = `<p class="wiz-lead">ShelfSync reads every downloadable product on each store, read-only, and links twins by their address slug.</p>
        <ul class="wiz-tests">${prog("GF", "GPLFamily", W.catalog.GF)}${prog("PW", "PluginWay", W.catalog.PW)}</ul>
        ${loading ? `<p class="muted" role="status">Reading PluginWay. You can leave this page; it carries on.</p>` : alert("success", "circle-check", `<span class="num">${n(W.catalog.total)}</span> products in the catalog.`, `<span class="num">${n(W.catalog.linked)}</span> twins linked by slug. 9 products are on one store only.`)}`;
    } else if (step === 4) {
      title = "Check what Cleanup found";
      body = `<p class="wiz-lead">ShelfSync found these on your stores. Nothing has been changed. You can fix them now or later in Cleanup.</p>
        <ul class="wiz-issues">${B.cleanup.map((g) => `<li>${icon(g.icon)}<span><strong class="num">${g.count}</strong> ${g.kind.toLowerCase()}</span></li>`).join("")}</ul>
        <a class="btn" href="#/cleanup">${icon("brush-cleaning")}Open Cleanup now</a>`;
    } else {
      title = "Teach ShelfSync your current files";
      // D-9: teaching is on by default, so "Teach and finish" is the main action and skipping is the secondary one
      body = `<p class="wiz-lead">ShelfSync reads the start of each product's current file in S3 (a range read, so the whole ZIP isn't downloaded) and saves what it looks like inside. The next ZIP for that product can then be Certain.</p>
        <ul class="plain-list muted"><li><span class="num">2,398</span> current files</li><li>Saved as "learned from current file" on each product</li>
          <li>About <span class="num">2,400</span> small S3 read requests. AWS charges a tiny amount for them.</li></ul>`;
    }
    const last = step === W.steps.length - 1;
    const foot = `<div class="wiz-foot">${step > 0 ? `<a class="btn" href="#/wizard?step=${step}">${icon("arrow-left")}Back</a>` : ""}<span class="spacer"></span>
      ${!canContinue ? `<p class="muted wiz-why">${state === "loading" ? "Continue when the catalog is built." : state === "empty" ? "Add a store to continue." : "Fix the store above to continue."}</p>` : ""}
      ${last ? `<a class="btn" href="#/dashboard" id="wiz-skip">Skip for now</a><a class="btn is-primary" href="#/dashboard" id="wiz-teach">${icon("fingerprint-pattern")}Teach and finish</a>`
        : canContinue ? `<a class="btn is-primary" href="#/wizard?step=${step + 2}">Continue${icon("chevron-right")}</a>` : `<button class="btn is-primary" type="button" aria-disabled="true" disabled>Continue${icon("chevron-right")}</button>`}</div>`;
    return `<div class="wizard"><div class="wiz-top"><h1 class="page-title wiz-title" tabindex="-1">Set up ShelfSync</h1><p class="page-sub">Step <span class="num">${step + 1}</span> of 6. Back never loses what you typed.</p>${SS.sampleTag}</div>
      ${rail}<section class="card wiz-card" aria-labelledby="wiz-h"><div class="card__body"><h2 class="card__title" id="wiz-h" tabindex="-1" data-nav-focus>${title}</h2>${body}</div>${foot}</section></div>`;
  }
  function wireWizard() {
    $$("[data-wf]").forEach((i) => i.addEventListener("input", () => { wiz.form[i.dataset.wf] = i.value; }));
    $$("[data-ws]").forEach((i) => i.addEventListener("input", () => { wiz.storage[i.dataset.ws] = i.value; }));
    $$("[data-help]").forEach((b) => b.addEventListener("click", () => SS.openHelp(b)));
    $$("[data-wsecret]").forEach((i) => i.addEventListener("input", () => { wiz.typed[i.dataset.wsecret] = i.value.length > 0; }));
    // leaving the step stores what was typed (the mockup only remembers that something was typed, never the value)
    $$('.wizard a[href^="#/"]').forEach((a) => a.addEventListener("click", () => { for (const k in wiz.typed) if (wiz.typed[k]) wiz.saved[k] = true; }));
    wireSecrets($(".wizard"));
    // Teach and finish starts teaching; the Dashboard and the strip then show its progress (finding 35)
    $("#wiz-teach")?.addEventListener("click", () => { st.teach = "running"; toast("Teach and finish", "Would start reading the start of each current file in S3 and saving the fingerprints. Its progress shows on the Dashboard and in the status strip. Nothing was sent.", true); });
  }
  SS.screens.wizard = { title: "Set up ShelfSync", render: wizard, wire: wireWizard };
})();
