/* ShelfSync mockup, P3.4: a clickable shell. Nothing is saved and nothing is sent (no fetch, no storage).
   Part A screens live here (Dashboard, Upload, Review); part B screens register through window.SS from screens-b.js.
   Routes: #/dashboard, #/upload, #/review, #/catalog, #/product?id=, #/cleanup, #/activity, #/settings/<sub>, #/wizard?step=.
   Mockup params in the hash: state=normal|loading|empty|error, theme=light|dark, ramp=ramp|done, disk=low. */
"use strict";
(() => {
  const D = window.SAMPLE;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
  const icon = (n, cls = "") => `<svg class="i ${cls}" aria-hidden="true" focusable="false"><use href="icons/sprite.svg#${n}"/></svg>`;
  const store = (code) => D.stores.find((s) => s.code === code);
  const dot = (s) => `<span class="store-dot is-${s.shape}" style="--dot-l:${s.dot.light};--dot-d:${s.dot.dark}" aria-hidden="true"></span>`;
  const storeBadge = (code, boxed = false) => {
    const s = store(code);
    return `<span class="store-badge${boxed ? " is-boxed" : ""}" title="${esc(s.name)}">${dot(s)}${s.code}<span class="sr-only"> (${esc(s.name)})</span></span>`;
  };
  // one Intl.DateTimeFormat per option set, made once (formatters are slow to build)
  const FMT = new Map();
  const fmt = (o) => { const k = JSON.stringify(o); if (!FMT.has(k)) FMT.set(k, new Intl.DateTimeFormat("en-GB", o)); return FMT.get(k); };
  // the zone's long name from Intl (e.g. "India Standard Time"), as the lead asked in 1b
  const TZ = fmt({ timeZoneName: "long" }).formatToParts(D.NOW).find((p) => p.type === "timeZoneName").value;
  const time = (t) => fmt({ hour: "2-digit", minute: "2-digit" }).format(t);
  const ago = (t) => {
    const m = Math.round((D.NOW - t) / 60000);
    return m < 60 ? `${m} min ago` : `${Math.floor(m / 60)} h ${m % 60} min ago`;
  };
  const n = (x) => x.toLocaleString("en-GB");
  // running text that names a file, folder prefix or store key: set those parts in Plex Mono (CLAUDE.md conventions)
  const MONO_RE = /([\w.-]+\.(?:zip|ssbak|csv)\b|\blatest_version[\w-]*|\bshelfsync-test\/|\{key\})/g;
  const mt = (s) => esc(s).replace(MONO_RE, '<span class="mono">$1</span>');
  const sampleTag = `<span class="sample-tag">${icon("flask-conical")}Sample data</span>`;

  /* ---------- state ---------- */
  const SCREENS = ["dashboard", "upload", "review", "catalog", "product", "cleanup", "activity", "settings", "wizard"];
  const SET_SUBS = ["stores", "storage", "rules", "updates", "backup", "app"];
  const PART_A = ["dashboard", "upload", "review"];
  const st = {
    route: "dashboard",
    states: Object.fromEntries(SCREENS.map((s) => [s, "normal"])),
    theme: "system",
    ramp: "ramp",
    paused: false,
    pausedAt: null,
    collapsed: null, // null = automatic (collapsed below 1280 px)
    sel: D.review[0].id,
    pick: {}, // selected candidate index per review item
    shortcuts: true,
    chartTable: false,
    sub: "stores", // Settings sub-page
    productId: "copperline",
    wizStep: 0,
    lowDisk: false, // ERR-04, a mockup switch
    brake: false, // the auto-apply brake has tripped (a mockup switch; decision 2026-10-26: the strip says "Auto-apply paused")
    teach: "off", // teaching from current files: off | running | done (set by "Teach and finish" or the mock switch)
    extra: {}, // part B params that live in the hash (catalog search and filter, activity range)
  };
  // Settings > App has no empty state: every setting has a value from the first start (the switch says so)
  const noEmpty = () => st.route === "settings" && st.sub === "app";
  const screenState = () => (noEmpty() && st.states[st.route] === "empty" ? "normal" : st.states[st.route]);

  function readHash() {
    const [path, q = ""] = location.hash.replace(/^#\/?/, "").split("?");
    const [first, sub] = path.split("/");
    const route = SCREENS.includes(first) ? first : "dashboard";
    // only known keys with known values are read; anything else is ignored and drops out when the hash is rewritten (finding 32)
    const p = new URLSearchParams(q);
    st.route = route;
    if (route === "settings" && SET_SUBS.includes(sub)) st.sub = sub;
    const B = window.SAMPLE_B;
    if (route === "product" && p.get("id") && B.rows.some((r) => r.id === p.get("id"))) st.productId = p.get("id");
    if (route === "wizard" && /^[1-6]$/.test(p.get("step") || "")) st.wizStep = Number(p.get("step")) - 1;
    st.lowDisk = p.get("disk") === "low" ? true : p.has("disk") ? false : st.lowDisk;
    if (p.has("q")) st.extra.q = p.get("q").slice(0, 100);
    if (["all", "theme", "plugin", "notinstep", "onestore", "week"].includes(p.get("f"))) st.extra.f = p.get("f");
    if (["today", "7d", "30d", "all"].includes(p.get("range"))) st.extra.range = p.get("range");
    if (["off", "running", "done"].includes(p.get("teach"))) st.teach = p.get("teach");
    if (["normal", "loading", "empty", "error"].includes(p.get("state"))) st.states[route] = p.get("state");
    if (["light", "dark"].includes(p.get("theme"))) st.theme = p.get("theme");
    if (["ramp", "done"].includes(p.get("ramp"))) st.ramp = p.get("ramp");
    st.brake = p.get("brake") === "1" ? true : p.has("brake") ? false : st.brake;
    if (st.brake) st.ramp = "done"; // the brake can only trip once auto-apply is on, so after the trust ramp
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (screenState() !== "normal") p.set("state", screenState());
    if (st.theme !== "system") p.set("theme", st.theme);
    if (st.ramp !== "ramp") p.set("ramp", st.ramp);
    if (st.lowDisk) p.set("disk", "low");
    if (st.brake) p.set("brake", "1");
    if (st.teach !== "off") p.set("teach", st.teach);
    if (st.route === "product") p.set("id", st.productId);
    if (st.route === "wizard") p.set("step", String(st.wizStep + 1));
    if (st.route === "catalog") { if (st.extra.q) p.set("q", st.extra.q); if (st.extra.f && st.extra.f !== "all") p.set("f", st.extra.f); }
    if (st.route === "activity" && st.extra.range && st.extra.range !== "7d") p.set("range", st.extra.range);
    const q = p.toString();
    const path = st.route === "settings" ? `settings/${st.sub}` : st.route;
    history.replaceState(null, "", `#/${path}${q ? "?" + q : ""}`);
  }

  /* ---------- theme ---------- */
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  function applyTheme() {
    const dark = st.theme === "dark" || (st.theme === "system" && sysDark.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }
  sysDark.addEventListener("change", applyTheme);

  /* ---------- derived data ---------- */
  const isEmpty = () => screenState() === "empty";
  const counts = () => (isEmpty() ? { review: 0, partial: 0, cleanup: 0 }
    : { ...D.counts, review: st.ramp === "ramp" ? D.counts.review : D.counts.review - 1, cleanup: SS.cleanupGroups ? SS.cleanupGroups().reduce((a, g) => a + g.count, 0) : D.counts.cleanup });
  const brakeOn = () => st.brake || (st.route === "settings" && st.sub === "rules" && screenState() === "error");
  const chartData = () => D.chart[st.ramp];
  const todayAuto = () => (isEmpty() ? 0 : chartData().auto.at(-1));
  const todayYou = () => (isEmpty() ? 0 : chartData().you.at(-1));
  const DOWN = { dashboard: "PW", upload: "S3", review: "GF", catalog: "GF", product: "PW", cleanup: "PW", activity: "PW" };
  const downStore = () => {
    if (screenState() !== "error") return null;
    if (st.route === "settings") return { stores: "GF", storage: "S3" }[st.sub] || null;
    return DOWN[st.route] || null;
  };

  /* ---------- shell ---------- */
  const NAV = [
    { id: "dashboard", label: "Dashboard", icon: "layout-dashboard" },
    { id: "upload", label: "Upload", icon: "upload" },
    { id: "review", label: "Review", icon: "inbox", count: "review" },
    { id: "catalog", label: "Catalog", icon: "library" },
    { id: "cleanup", label: "Cleanup", icon: "brush-cleaning", count: "cleanup" },
    { id: "activity", label: "Activity", icon: "history" },
    "sep",
    { id: "settings", label: "Settings", icon: "settings" },
  ];
  function renderNav() {
    const c = counts();
    $("#nav").innerHTML = NAV.map((it) => {
      if (it === "sep") return `<li aria-hidden="true"><div class="side-nav__sep"></div></li>`;
      const num = it.count ? c[it.count] : null;
      const label = num ? `${it.label}, ${num} ${it.count === "review" ? "waiting" : "issues"}` : it.label;
      return `<li><a class="nav-item" href="#/${it.id}" ${st.route === it.id || (st.route === "product" && it.id === "catalog") ? 'aria-current="page"' : ""} title="${esc(label)}" aria-label="${esc(label)}">
        ${icon(it.icon)}<span class="nav-item__label">${it.label}</span>${num ? `<span class="nav-count" aria-hidden="true">${num}</span>` : ""}</a></li>`;
    }).join("");
    $("#nav-meta").textContent = isEmpty() ? "" : `${n(D.catalogSize)} products in the catalog`;
  }
  // ERR-01 / ERR-03 reasons, the same ones the screens' inline alerts give
  const DOWN_REASON = {
    GF: "HTTP 401 (the Shop Manager key was refused)",
    PW: "HTTP 524 (Cloudflare timeout)",
    S3: "AccessDenied (the access key isn't allowed to write to this bucket)",
  };
  function renderHealth() {
    const down = downStore();
    // a healthy chip is a status read-out; a red one is a button that opens the reason and one action (finding 18)
    const chip = (code, badge, name, okText, downText) => {
      const isDown = down === code;
      if (!isDown) return `<span class="health-chip" title="${esc(name)}: connected, ${okText}">${badge}${icon("circle-check")}<span class="health-chip__lat">${okText}</span><span class="sr-only">connected</span></span>`;
      return `<button class="health-chip is-down" type="button" id="hc-${code}" data-health="${code}" aria-expanded="false" title="${esc(name)}: ${downText.toLowerCase()}. Show the reason">
        ${badge}${icon("triangle-alert")}<span class="health-chip__lat">${downText}</span><span class="sr-only">. Show the reason</span></button>`;
    };
    // "no stores yet" (Catalog, Settings > Stores): no store is connected, so no store chip is shown
    const noStores = isEmpty() && (st.route === "catalog" || (st.route === "settings" && st.sub === "stores"));
    const chips = noStores ? [] : D.stores.map((s) => chip(s.code, storeBadge(s.code), s.name, `${s.latency} ms`, "Can't reach"));
    chips.push(chip("S3", `<span class="store-badge">${icon("hard-drive")}S3</span>`, D.s3.name, `${D.s3.latency} ms`, "Refused"));
    $("#health").innerHTML = chips.join("");
  }
  function healthPopover(btn) {
    const code = btn.dataset.health;
    if (code === "S3") {
      SS.popover(btn, { title: `S3 refused access: ${esc(DOWN_REASON.S3)}.`, html: `<p>Uploads are held.</p>
        <a class="btn is-compact" href="#/settings/storage">${icon("settings")}Open Storage settings</a>` });
      return;
    }
    const s = store(code);
    SS.popover(btn, { title: `${esc(s.name)} can't be reached: ${esc(DOWN_REASON[code])}.`, html: `<p>Updates for it are waiting.</p>
      <button class="btn is-compact" type="button" data-mock="Would test the ${esc(s.name)} connection. Nothing was sent.">${icon("plug")}Test connection</button>` });
  }
  function renderPause() {
    $("#pause-btn").innerHTML = st.paused ? `${icon("play")}Resume` : `${icon("pause")}Pause everything`;
    $("#pause-btn").classList.toggle("is-paused", st.paused);
  }
  function renderStrip() {
    const brake = brakeOn();
    const ramp = st.ramp === "ramp" && !brake;
    const pct = ramp ? (37 / 50) * 100 : 100;
    const items = [];
    // the reason sits in a tooltip that opens on hover and on keyboard focus, and is the item's description for screen readers
    const tipItem = (cls, body, tip, href) => `<${href ? `a href="${href}"` : 'span tabindex="0"'} class="status-strip__item has-tip ${cls}" aria-describedby="strip-tip">${body}<span class="tip" role="tooltip" id="strip-tip">${tip}</span></${href ? "a" : "span"}>`;
    if (st.paused) items.push(`<span class="status-strip__item is-paused">${icon("pause")}<span class="s-long">Paused by you at ${time(st.pausedAt)}. Nothing runs until you resume.</span><span class="s-short">Paused by you at ${time(st.pausedAt)}<span class="sr-only">. Nothing runs until you resume.</span></span></span>`);
    else if (brake) items.push(tipItem("is-brake", `${icon("pause")}Auto-apply <strong>paused</strong>`, "Paused by the brake: more than 30 updates in 10 minutes. Check the latest updates in Activity, then resume it in Settings › Rules.", "#/settings/rules"));
    else if (ramp) items.push(tipItem("", `${icon("bot")}Auto-apply <strong>off</strong>`, "Auto-apply stays off until the trust ramp reaches 50."));
    else items.push(`<span class="status-strip__item">${icon("bot")}Auto-apply <strong>on</strong></span>`);
    items.push(`<span class="status-strip__item">Trust ramp <strong class="num">${ramp ? "37 / 50" : "50 / 50"}</strong><span class="ramp-meter" aria-hidden="true"><span style="width:${pct}%"></span></span></span>`);
    items.push(`<span class="status-strip__item">${icon("refresh-cw")}<span class="s-long">Last sync</span><span class="s-short">Synced</span> <strong>${time(D.lastSync)}</strong>${st.paused || brake ? "" : `<span class="strip-extra"> (${ago(D.lastSync)})</span>`}</span>`);
    // teaching from current files (D-9): its progress, which waits while everything is paused (finding 35)
    if (st.teach === "running") items.push(`<a class="status-strip__item strip-teach" href="#/activity">${icon("fingerprint-pattern")}${st.paused
      ? `Teaching <strong>waits while paused</strong>` : `Teaching <strong class="num">${n(TEACH.done)} / ${n(TEACH.total)}</strong>`}</a>`);
    // the last two items can each shrink to an icon toggletip (a real button described by its tip) when space runs out
    const tipBtn = (ic, label, tipId) => `<button type="button" class="tip-btn" aria-label="${label}" aria-describedby="${tipId}" hidden>${icon(ic)}</button>`;
    items.push(`<span class="status-strip__item strip-snapshot has-tip">${icon("clock", "tip-icon")}${tipBtn("clock", "Next snapshot", "snap-tip")}<span class="tip-text"><span class="s-long">Next snapshot</span><span class="s-short">Next</span> <strong>02:00</strong></span><span class="tip" role="tooltip" id="snap-tip">Next snapshot at 02:00</span></span>`);
    items.push(`<span class="status-strip__item status-strip__zone has-tip">${icon("globe", "tip-icon")}${tipBtn("globe", "Time zone", "zone-tip")}<span class="tip-text">${TZ}</span><span class="tip" role="tooltip" id="zone-tip">Times in ${TZ}</span></span>`);
    $("#strip").innerHTML = items.join("");
    fitStrip();
  }
  // The strip is one line at every width (05 section 5). When its items don't fit, it compacts in steps until they do:
  // 1 drops the relative time and the ramp meter; 2 uses short labels ("Synced", "Snapshot", the paused line without
  // its second sentence, which stays for screen readers); 3 shows the zone as a globe whose name is in a tooltip.
  function fitStrip() {
    const s = $("#strip");
    if (!s || !s.offsetParent) return;
    // one line = every item overlaps the same row (items differ in height, so tops alone can't be compared)
    const oneLine = () => { const r = [...s.children].map((c) => c.getBoundingClientRect()); return Math.max(...r.map((x) => x.top)) < Math.min(...r.map((x) => x.bottom)); };
    const steps = ["is-c1", "is-c2", "is-c3", "is-c4"];
    s.classList.remove(...steps);
    const compact = () => { // step 3 shrinks the snapshot item, step 4 the zone; their text stays for screen readers
      $(".strip-snapshot .tip-btn", s).hidden = !s.classList.contains("is-c3");
      $(".status-strip__zone .tip-btn", s).hidden = !s.classList.contains("is-c4");
    };
    compact();
    for (const step of steps) {
      if (oneLine()) break;
      s.classList.add(step);
      compact();
    }
  }
  addEventListener("resize", fitStrip);
  // toggletip: a click on an icon button opens or closes its tip; Esc closes it (the Esc handler below hides every tip)
  $("#strip").addEventListener("click", (e) => {
    const b = e.target.closest(".tip-btn");
    if (!b) return;
    const item = b.closest(".has-tip"), open = !item.classList.contains("is-open");
    $$("#strip .has-tip.is-open").forEach((t) => t.classList.remove("is-open"));
    item.classList.toggle("is-open", open);
    item.classList.remove("tip-off");
  });
  function applyCollapse() {
    const auto = !matchMedia("(min-width: 80rem)").matches;
    const c = st.collapsed === null ? auto : st.collapsed;
    $("#shell").classList.toggle("is-collapsed", c);
    const b = $("#collapse-btn");
    b.setAttribute("aria-expanded", String(!c));
    b.querySelector("use").setAttribute("href", `icons/sprite.svg#${c ? "panel-left-open" : "panel-left-close"}`);
    b.querySelector(".collapse-btn__label").textContent = c ? "Expand menu" : "Collapse menu";
    b.setAttribute("aria-label", c ? "Expand menu" : "Collapse menu");
    fitStrip(); // the strip's width changed with the nav
  }

  /* ---------- shared pieces ---------- */
  const BAND = {
    certain: { tone: "success", icon: "circle-check", label: "Certain" },
    likely: { tone: "info", icon: "circle-dot", label: "Likely" },
    unsure: { tone: "warning", icon: "circle-help", label: "Unsure" },
    nomatch: { tone: "neutral", icon: "search-x", label: "No match" },
    held: { tone: "held", icon: "shield-alert", label: "Held" },
    threat: { tone: "danger", icon: "shield-x", label: "Threat found" },
    notscanned: { tone: "warning", icon: "shield-question", label: "Not scanned" },
    partial: { tone: "danger", icon: "triangle-alert", label: "Partial" },
    applied: { tone: "success", icon: "circle-check", label: "Applied" },
  };
  const pill = (k) => { const b = BAND[k]; return `<span class="band-pill is-${b.tone}">${icon(b.icon)}${b.label}</span>`; };
  // WhyPanel (05 section 5, MAT-07): a "Why?" button on every match; the popover lists each signal and its points
  const whyBtn = (key) => `<button class="btn is-ghost is-compact why-btn" type="button" data-why="${esc(key)}" aria-expanded="false"
    aria-label="Why ${esc(BAND[D.why[key].band].label)}: ${esc(D.why[key].product)}">${icon("circle-help")}Why?</button>`;
  function whyPopover(btn) {
    const w = D.why[btn.dataset.why];
    const total = w.reasons.reduce((a, r) => a + r.pts, 0);
    SS.popover(btn, {
      title: `Why ${BAND[w.band].label}: ${esc(w.product)}`,
      html: `<ul class="why-list">${[...w.reasons].sort((x, y) => y.pts - x.pts).map((r) => `<li class="${r.pts >= 0 ? "is-plus" : "is-minus"}"><b class="num">${r.pts >= 0 ? "+" : "−"}${Math.abs(r.pts)}</b><span>${mt(r.text)}</span></li>`).join("")}</ul>
        <p class="why-total">Total <strong class="num">${total}</strong> points</p>`,
    });
  }
  const pageHead = (title, sub) => `<div class="page-head"><div><h1 class="page-title" tabindex="-1">${title}</h1>${sub ? `<p class="page-sub">${sub}</p>` : ""}</div><div class="page-head__end">${sampleTag}</div></div>`;
  const alert = (tone, ic, title, body, action) => `<div class="alert is-${tone}" role="${tone === "danger" ? "alert" : "status"}">${icon(ic)}
    <div><p class="alert__title">${title}</p>${body ? `<p>${body}</p>` : ""}</div>${!action ? "" : action.href ? `<a class="btn is-compact alert__action" href="${action.href}">${action.icon ? icon(action.icon) : ""}${action.label}</a>`
      : `<button class="btn is-compact alert__action" type="button" data-mock="${esc(action.mock)}">${action.icon ? icon(action.icon) : ""}${action.label}</button>`}</div>`;
  const sk = (w, cls = "t") => `<span class="sk ${cls}" style="width:${w}"></span>`;
  const dropZone = (compact, meta) => `<section class="drop-zone${compact ? " is-compact" : ""}${st.lowDisk ? " is-paused" : ""}" aria-labelledby="dz-title">
    <span class="drop-zone__icon">${icon("file-up", "i-lg")}</span>
    <div><h2 class="drop-zone__title" id="dz-title">${compact ? "Drop ZIPs here" : "Drop ZIPs to update your stores"}</h2>
    <p class="drop-zone__hint">${compact ? "One ZIP or fifty. Each gets its own row below." : "One ZIP or fifty. Each is inspected, scanned with Windows Defender and matched before anything changes on a store."}</p></div>
    ${compact && meta ? `<span class="drop-zone__meta">${meta}</span>` : ""}
    ${st.lowDisk ? `<p class="drop-zone__paused">${icon("triangle-alert")}Uploads are paused: low disk space.</p>` : `<button class="btn${compact ? "" : " is-primary"}" type="button" data-mock="Would open the Windows file picker for .zip files. Nothing was added.">${icon("folder-open")}Browse files</button>`}
  </section>`;

  /* ---------- Dashboard ---------- */
  function greeting() {
    const h = Number(fmt({ hour: "numeric", hourCycle: "h23" }).format(D.NOW));
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }
  function kpis(state) {
    if (state === "loading") {
      return `<div class="card kpi-strip" aria-busy="true">${[1, 2, 3, 4].map(() => `<div class="kpi-tile">${sk("6rem")}${sk("3rem", "t-lg")}${sk("80%")}${sk("5rem")}</div>`).join("")}</div>`;
    }
    const c = counts();
    const a = todayAuto(), y = todayYou();
    const empty = state === "empty";
    const tiles = [
      { href: "#/review", ic: "inbox", label: "Waiting in Review", num: c.review, cls: c.review ? "is-attention" : "",
        detail: empty ? "Nothing waiting." : st.ramp === "ramp" ? "3 held, 1 trust-ramp check, 6 need a match" : "3 held, 6 need a match", link: "Open Review" },
      { href: "#/activity", ic: "triangle-alert", label: "Partial", num: c.partial, cls: c.partial ? "is-danger" : "",
        detail: empty ? "Every store is in step." : "Stackmart 6.4.0: PluginWay didn't update (HTTP 524). Nothing was deleted.", link: "Open Activity" },
      { href: "#/cleanup", ic: "brush-cleaning", label: "Cleanup", num: c.cleanup, cls: "",
        detail: empty || !c.cleanup ? "No issues." : SS.cleanupGroups().map((g) => `${g.count} ${g.noun[g.count === 1 ? 0 : 1]}`).join(", "), link: "Open Cleanup" },
      { href: "#/activity", ic: "circle-check", label: "Applied today", num: a + y, cls: "",
        detail: empty ? "No updates yet today." : `${y} by you, ${a} by auto-rule${st.ramp === "ramp" ? " (trust ramp 37 / 50)" : ""}`, link: "Open Activity" },
    ];
    return `<div class="card kpi-strip">${tiles.map((t) => `<a class="kpi-tile ${t.cls}" href="${t.href}">
      <span class="kpi-tile__label">${icon(t.ic)}${t.label}</span><span class="kpi-tile__num">${t.num}</span>
      <span class="kpi-tile__detail">${t.detail}</span><span class="kpi-tile__link">${t.link}${icon("chevron-right")}</span></a>`).join("")}</div>`;
  }
  function latestCard(state) {
    const head = `<div class="card__head"><div><h2 class="card__title">Latest updates</h2><p class="muted" style="font-size:var(--text-sm)">Times in ${TZ}</p></div><a class="card__link" href="#/activity">View all in Activity${icon("chevron-right")}</a></div>`;
    if (state === "loading") {
      return `<section class="card" aria-busy="true">${head}<div class="card__body" style="display:grid;gap:var(--space-5)">${[1, 2, 3, 4, 5, 6].map(() => `<div style="display:grid;grid-template-columns:4rem 1fr 7rem 7rem;gap:var(--space-4)">${sk("100%")}${sk("70%")}${sk("100%")}${sk("100%")}</div>`).join("")}</div></section>`;
    }
    if (state === "empty") {
      return `<section class="card">${head}<div class="empty"><span class="empty__icon">${icon("history", "i-lg")}</span>
        <p class="empty__text">No updates yet. Every update ShelfSync applies to a store appears here.</p>
        <p class="empty__sub">Drop a ZIP above to make the first one.</p></div></section>`;
    }
    const rows = D.latest.map((r) => {
      const who = st.ramp === "ramp" ? r.whoRamp : r.who;
      const ticks = D.stores.map((s) => {
        const v = r.stores[s.code];
        if (v === "done") return `<span class="tick is-done">${storeBadge(s.code)}${icon("circle-check")}<span class="sr-only">updated</span></span>`;
        if (v === "failed") return `<span class="tick is-failed">${storeBadge(s.code)}${icon("triangle-alert")}Failed</span>`;
        return `<span class="tick is-none" title="Not on ${esc(s.name)}">${storeBadge(s.code)}<span aria-hidden="true">–</span><span class="sr-only">not on this store</span></span>`;
      }).join("");
      return `<tr><td class="num">${time(r.at)}</td>
        <td><span class="trunc" title="${esc(r.product)}">${esc(r.product)}</span><span class="mono muted trunc">${esc(r.slug)}</span></td>
        <td><span class="vchange"><span class="muted">${r.from}</span>${icon("arrow-right")}<span class="sr-only">to</span>${r.to}</span></td>
        <td><span class="ticks">${ticks}</span></td>
        <td><span class="who">${who === "auto" ? `${icon("bot")}Auto-rule` : `${icon("user-check")}You`}</span></td></tr>`;
    }).join("");
    return `<section class="card">${head}<div class="table-wrap"><table class="data-table">
      <colgroup><col style="width:4.5rem"><col><col style="width:7.5rem"><col style="width:9.5rem"><col style="width:6.5rem"></colgroup>
      <thead><tr><th scope="col">Time</th><th scope="col">Product</th><th scope="col">Version</th><th scope="col">Stores</th><th scope="col">Approved by</th></tr></thead>
      <tbody>${rows}</tbody></table></div></section>`;
  }
  function connCard(state) {
    const down = downStore();
    const head = `<div class="card__head"><h2 class="card__title is-sm">Connections</h2><a class="card__link" href="#/settings">Settings${icon("chevron-right")}</a></div>`;
    if (state === "loading") return `<section class="card" aria-busy="true">${head}<div class="card__body" style="display:grid;gap:var(--space-4)">${sk("90%")}${sk("85%")}${sk("70%")}</div></section>`;
    const err = down === "PW" ? alert("danger", "triangle-alert", "PluginWay can't be reached: HTTP 524 (Cloudflare timeout).", "Updates for it are waiting.", { label: "Test connection", icon: "refresh-cw", mock: "Would test the PluginWay connection. Nothing was sent." }) : "";
    const row = (badge, name, sub, ok, lat) => `<li class="conn-row"><span class="conn-row__name">${badge}<span>${name}<small>${sub}</small></span></span>
      ${ok ? pill("applied").replace("Applied", "Connected") : `<span class="band-pill is-danger">${icon("triangle-alert")}Can't reach</span>`}<span class="conn-row__lat">${ok ? `${lat} ms` : "–"}</span></li>`;
    return `<section class="card">${head}${err}<ul class="conn-list" style="${err ? "margin-top:var(--space-2)" : ""}">
      ${D.stores.map((s) => row(storeBadge(s.code, true), s.name, down === s.code ? `Last reached ${time(D.lastSync)}` : `Synced ${time(D.lastSync)}`, down !== s.code, s.latency)).join("")}
      ${row(`<span class="store-badge is-boxed">${icon("hard-drive")}S3</span>`, D.s3.name, "Uploads and range reads", true, D.s3.latency)}</ul></section>`;
  }
  function days() {
    const out = [];
    for (let i = 13; i >= 0; i--) out.push(D.NOW - i * 86400000);
    return out;
  }
  function chartCard(state) {
    const head = `<div class="card__head"><h2 class="card__title is-sm" id="chart-title">Updates, last 14 days</h2></div>`;
    if (state === "loading") return `<section class="card" aria-busy="true">${head}<div class="card__body">${sk("50%")}<div style="display:flex;align-items:flex-end;gap:var(--space-2);height:10rem;margin-top:var(--space-4)">${[40, 70, 30, 55, 20, 10, 45, 80, 35, 60, 75, 25, 10, 90].map((h) => `<span class="sk" style="flex:1;height:${h}%"></span>`).join("")}</div></div></section>`;
    if (state === "empty") return `<section class="card">${head}<div class="empty"><span class="empty__icon">${icon("chart-column", "i-lg")}</span><p class="empty__text">No updates in the last 14 days.</p><p class="empty__sub">Each day's updates appear here, split into auto-rule and you.</p></div></section>`;
    const d = chartData(), ds = days();
    const tot = d.auto.map((a, i) => a + d.you[i]);
    const sumA = d.auto.reduce((x, y) => x + y, 0), sumY = d.you.reduce((x, y) => x + y, 0);
    const max = Math.max(...tot), step = 5, top = Math.ceil(max / step) * step || step;
    const W = 340, H = 196, L = 28, R = 4, T = 22, B = 30, pw = W - L - R, ph = H - T - B;
    const band = pw / 14, bw = Math.min(16, band - 6), r = 3, gap = 2;
    const y = (v) => T + ph - (v / top) * ph;
    const dayLab = (t) => fmt({ day: "numeric", month: "short" }).format(t);
    const longDay = (t) => fmt({ weekday: "short", day: "numeric", month: "short" }).format(t);
    let grid = "", axis = "", cols = "";
    for (let v = 0; v <= top; v += step) {
      grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      axis += `<text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
    }
    ds.forEach((t, i) => {
      const cx = L + band * i + band / 2, x = cx - bw / 2;
      if (i % 3 === 1 || i === 13) axis += `<text x="${cx}" y="${H - B + 16}" text-anchor="middle">${i === 13 ? "Today" : dayLab(t)}</text>`;
      const a = d.auto[i], u = d.you[i];
      let marks = "";
      const segTop = (y0, h, rounded) => rounded
        ? `M${x} ${y0 + h}V${y0 + r}Q${x} ${y0} ${x + r} ${y0}H${x + bw - r}Q${x + bw} ${y0} ${x + bw} ${y0 + r}V${y0 + h}Z`
        : `M${x} ${y0 + h}V${y0}H${x + bw}V${y0 + h}Z`;
      if (a) { const h = (a / top) * ph; marks += `<path class="seg-auto" d="${segTop(y(a), h, !u)}"/>`; }
      if (u) { const h = (u / top) * ph - (a ? gap : 0); marks += `<path class="seg-you" d="${segTop(y(a + u), h, true)}"/>`; }
      const label = `${longDay(t)}: ${tot[i]} update${tot[i] === 1 ? "" : "s"}, ${a} by auto-rule, ${u} by you`;
      cols += `<g class="col" tabindex="${i === 13 ? 0 : -1}" role="img" aria-label="${label}" data-i="${i}"><rect class="hit" x="${L + band * i + 1}" y="${T}" width="${band - 2}" height="${ph}" rx="3"/>${marks}</g>`;
      if (i === 13) cols += `<text class="total" x="${cx}" y="${y(tot[i]) - 6}" text-anchor="middle">${tot[i]}</text>`;
    });
    const table = `<div class="chart-table" id="chart-table" ${st.chartTable ? "" : "hidden"}><table class="data-table"><caption class="sr-only">Updates per day, last 14 days</caption>
      <thead><tr><th scope="col">Day</th><th scope="col" class="n">Auto-rule</th><th scope="col" class="n">You</th><th scope="col" class="n">Total</th></tr></thead>
      <tbody>${ds.map((t, i) => `<tr><td>${longDay(t)}</td><td class="n">${d.auto[i]}</td><td class="n">${d.you[i]}</td><td class="n">${tot[i]}</td></tr>`).join("")}</tbody></table></div>`;
    return `<section class="card" aria-labelledby="chart-title">${head}<div class="card__body">
      <ul class="chart-legend" aria-label="Legend"><li><span class="sw is-auto" aria-hidden="true"></span>Auto-rule <span class="num">${sumA}</span></li><li><span class="sw is-you" aria-hidden="true"></span>You <span class="num">${sumY}</span></li></ul>
      <div class="chart-14d" id="chart"><svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Updates per day for the last 14 days, stacked by who approved them. Use the arrow keys to move between days.">
        <text class="ylab" x="0" y="10" text-anchor="start" aria-hidden="true">Updates</text>
        <g class="grid" aria-hidden="true">${grid}</g><g class="axis" aria-hidden="true">${axis}</g>
        <line class="baseline" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" aria-hidden="true"/>${cols}</svg>
        <div class="chart-tip" id="chart-tip" hidden></div></div>
      ${st.ramp === "ramp" ? `<p class="chart-foot"><span>${icon("info")} Auto-rule stays at 0 until the trust ramp reaches 50.</span></p>` : ""}
      <div class="chart-foot"><span>Days in ${TZ}</span><button class="btn is-ghost is-compact" type="button" id="chart-table-btn" aria-expanded="${st.chartTable}" aria-controls="chart-table">${icon("table")}${st.chartTable ? "Hide table" : "Show as table"}</button></div>
      ${table}</div></section>`;
  }
  // sample progress for teaching (made up): 412 of 2,398 current files read
  const TEACH = { done: 412, total: 2398 };
  function teachRow(state) {
    if (st.teach === "off" || state === "loading" || state === "empty") return "";
    if (st.teach === "done") return `<section class="card teach-row is-done" aria-labelledby="teach-title">${icon("circle-check", "res-icon-success")}
      <div><h2 class="teach-row__title" id="teach-title">Teaching finished</h2><p class="muted">${n(TEACH.total)} current files read. Each product now has a fingerprint "learned from current file".</p></div>
      <a class="card__link" href="#/activity">Open Activity${icon("chevron-right")}</a></section>`;
    const pct = Math.round((TEACH.done / TEACH.total) * 100);
    return `<section class="card teach-row" aria-labelledby="teach-title">${icon("fingerprint-pattern")}
      <div class="teach-row__main"><h2 class="teach-row__title" id="teach-title">Teaching ShelfSync your current files</h2>
        <p class="muted">${st.paused ? "Waits while paused. It carries on when you resume." : `<span class="num">${n(TEACH.done)}</span> of <span class="num">${n(TEACH.total)}</span> current files read. You can keep working.`}</p>
        <div class="progress" role="progressbar" aria-label="Teaching from current files" aria-valuenow="${pct}" aria-valuetext="${n(TEACH.done)} of ${n(TEACH.total)} files" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct}%"></span></div></div>
      <a class="card__link" href="#/activity">Open Activity${icon("chevron-right")}</a></section>`;
  }
  function dashboard(state) {
    const sub = fmt({ weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(D.NOW);
    return `<div class="page">${pageHead(greeting(), sub)}${kpis(state)}${teachRow(state)}${dropZone(false)}
      <div class="dash-grid">${latestCard(state)}<div class="dash-side">${connCard(state)}${chartCard(state)}</div></div></div>`;
  }
  function wireChart() {
    const wrap = $("#chart");
    if (!wrap) return;
    const tip = $("#chart-tip"), d = chartData(), ds = days();
    const show = (g) => {
      const i = Number(g.dataset.i), t = ds[i];
      tip.replaceChildren();
      const day = document.createElement("div"); day.className = "chart-tip__day";
      day.textContent = fmt({ weekday: "long", day: "numeric", month: "long" }).format(t); tip.append(day);
      [["auto", "Auto-rule", d.auto[i]], ["you", "You", d.you[i]]].forEach(([k, l, v]) => {
        const row = document.createElement("div"); row.className = "chart-tip__row";
        const key = document.createElement("span"); key.className = "chart-tip__key"; key.style.background = `var(--chart-${k})`;
        const s = document.createElement("strong"); s.textContent = v;
        row.append(key, s, document.createTextNode(l)); tip.append(row);
      });
      tip.hidden = false;
      const wb = wrap.getBoundingClientRect(), gb = g.getBoundingClientRect();
      // beside the bar, never over it: left of bars in the right half, right of bars in the left half
      const mid = gb.left - wb.left + gb.width / 2;
      const left = mid > wb.width / 2 ? gb.left - wb.left - tip.offsetWidth - 4 : gb.right - wb.left + 4;
      tip.style.left = `${Math.max(0, left)}px`; tip.style.top = `${gb.top - wb.top + gb.height / 2 - tip.offsetHeight / 2}px`;
    };
    const cols = $$(".col", wrap);
    cols.forEach((g) => {
      g.addEventListener("pointerenter", () => show(g));
      g.addEventListener("pointerleave", () => { if (document.activeElement !== g) tip.hidden = true; });
      g.addEventListener("focus", () => show(g));
      g.addEventListener("blur", () => { tip.hidden = true; });
      g.addEventListener("keydown", (e) => {
        const i = Number(g.dataset.i);
        const to = e.key === "ArrowLeft" ? i - 1 : e.key === "ArrowRight" ? i + 1 : e.key === "Home" ? 0 : e.key === "End" ? 13 : null;
        if (to === null || to < 0 || to > 13) return;
        e.preventDefault(); g.tabIndex = -1; cols[to].tabIndex = 0; cols[to].focus();
      });
    });
    $("#chart-table-btn").addEventListener("click", () => { st.chartTable = !st.chartTable; render(false); $("#chart-table-btn").focus(); });
  }

  /* ---------- Upload ---------- */
  const STEP_LABEL = { inspect: "Inspect", scan: "Scan", match: "Match", s3: "S3" };
  const STEP_STATE = { pending: "waiting", running: "running", done: "done", held: "held", failed: "failed" };
  function jobView(j) {
    const v = j.ramp ? (st.ramp === "ramp" ? j.ramp : j.done) : j;
    const steps = { ...v.steps };
    let result = v.result;
    if (screenState() === "error" && steps.s3 === "running") {
      steps.s3 = "held";
      result = { kind: "s3held", text: "Held: S3 refused access. This ZIP uploads once access works again." };
    }
    return { steps, result };
  }
  function stepChip(key, state) {
    const s = store(key);
    const label = s ? `${dot(s)}${s.code}` : STEP_LABEL[key];
    const ic = state === "done" ? icon("circle-check") : state === "held" ? icon("shield-alert") : state === "failed" ? icon("triangle-alert") : "";
    const name = s ? s.name : STEP_LABEL[key];
    return `<li><span class="step-chip is-${state}" title="${esc(name)}: ${STEP_STATE[state]}">${ic}${label}<span class="sr-only">: ${STEP_STATE[state]}</span></span></li>`;
  }
  function resultCell(r) {
    const map = {
      done: ["circle-check", "res-icon-success"], review: ["inbox", "res-icon-muted"], held: ["shield-alert", "res-icon-danger"],
      threat: ["shield-x", "res-icon-danger"], notscanned: ["shield-question", "res-icon-warning"], partial: ["triangle-alert", "res-icon-danger"],
      failed: ["triangle-alert", "res-icon-danger"], s3held: ["shield-alert", "res-icon-danger"],
    };
    if (r.kind === "running") {
      return `<div class="line"><span class="res-text">${r.text} <span class="num muted">${r.pct}%</span></span></div>
        <div class="progress" role="progressbar" aria-label="${esc(r.text)}" aria-valuenow="${r.pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${r.pct}%"></span></div>`;
    }
    const [ic, cls] = map[r.kind];
    const link = ["review", "held", "threat", "notscanned"].includes(r.kind) ? ` <a href="#/review">Open Review</a>`
      : r.kind === "partial" ? ` <button class="btn is-compact" type="button" data-mock="Would retry the PluginWay write for stackmart-6.4.0.zip. Nothing was sent." style="margin-top:var(--space-2)">${icon("refresh-cw")}${r.action}</button>`
      : r.kind === "s3held" ? ` <a href="#/settings/storage">Open Storage settings</a>` : "";
    return `<div class="line">${icon(ic, cls)}<span class="res-text">${mt(r.text)}${link}</span></div>`;
  }
  function upload(state) {
    const total = D.batch.length;
    const views = D.batch.map(jobView);
    const k = (f) => views.filter((v) => f(v.result.kind)).length;
    const summary = [
      [icon("circle-check", "res-icon-success"), `${k((x) => x === "done")} applied`],
      [icon("refresh-cw", "res-icon-muted"), `${k((x) => x === "running")} running`],
      [icon("inbox", "res-icon-muted"), `${k((x) => ["review", "held", "threat", "notscanned", "s3held"].includes(x))} waiting in Review or held`],
      [icon("triangle-alert", "res-icon-danger"), `${k((x) => x === "partial")} partial, ${k((x) => x === "failed")} failed`],
    ];
    const meta = state === "empty" || state === "loading" ? "" : `<span class="num">${total}</span> in this batch`;
    const headRow = `<div class="job-head" aria-hidden="true"><span>File</span><span class="col-product">Product and band</span><span>Steps</span><span class="col-result">Result</span></div>`;
    let body;
    if (state === "loading") {
      body = headRow + `<ul class="job-list" aria-busy="true">${Array.from({ length: 7 }, () => `<li class="job-row"><span>${sk("85%")}<span style="display:block;height:var(--space-2)"></span>${sk("40%")}</span><span>${sk("60%")}<span style="display:block;height:var(--space-2)"></span>${sk("4.5rem", "pill")}</span><span style="display:flex;gap:var(--space-2)">${[1, 2, 3, 4, 5, 6].map(() => sk("3rem", "chip")).join("")}</span><span>${sk("90%")}</span></li>`).join("")}</ul>`;
    } else if (state === "empty") {
      body = `<div class="empty"><span class="empty__icon">${icon("file-archive", "i-lg")}</span><p class="empty__text">No ZIPs in this batch. Each ZIP you add gets a row here, with its steps and result.</p><p class="empty__sub">Drop ZIPs above, or use Browse files.</p></div>`;
    } else {
      body = headRow + `<ul class="job-list">${D.batch.map((j, i) => {
        const v = views[i];
        const held = ["held", "threat", "notscanned", "s3held"].includes(v.result.kind), failed = ["failed", "partial"].includes(v.result.kind);
        const startedMin = 2 + i * 3;
        return `<li class="job-row${held ? " is-held" : ""}${failed ? " is-failed" : ""}">
          <div class="job-row__file"><span class="mono trunc" title="${esc(j.file)}">${esc(j.file)}</span><small>${j.size}, added ${time(D.NOW - startedMin * 60000)}</small></div>
          <div class="job-row__product">${j.product ? `<span class="trunc name" title="${esc(j.product)}">${esc(j.product)}</span>${j.band ? `<span class="band-why">${pill(j.band)}${j.why ? whyBtn(j.why) : ""}</span>` : ""}` : j.band ? `<span class="muted">No product found</span>${pill(j.band)}` : `<span class="muted">${v.steps.inspect === "failed" || v.steps.scan === "held" ? "Not matched" : v.steps.scan === "done" ? "Not matched yet" : "Matched after the scan"}</span>`}</div>
          <ol class="step-rail job-row__steps" aria-label="Steps">${["inspect", "scan", "match", "s3", ...D.stores.map((s) => s.code)].map((key) => stepChip(key, v.steps[key])).join("")}</ol>
          <div class="job-row__result">${resultCell(v.result)}</div></li>`;
      }).join("")}</ul>`;
    }
    const err = state === "error" ? alert("danger", "triangle-alert", "S3 refused access: AccessDenied (the access key isn't allowed to write to this bucket).", "Uploads are held.", { label: "Open Storage settings", icon: "settings", href: "#/settings/storage" }) : "";
    return `<div class="page">${pageHead("Upload", "Each ZIP is inspected, scanned with Windows Defender and matched before anything changes on a store.")}
      ${dropZone(true, meta)}
      <section class="card" aria-labelledby="batch-title"><div class="card__head"><h2 class="card__title" id="batch-title">This batch</h2>
        ${state === "normal" || state === "error" ? `<p class="batch-summary">${summary.map(([i, t]) => `<span>${i}${t}</span>`).join("")}</p>` : ""}</div>
        ${err}${err ? `<div style="height:var(--space-4)"></div>` : ""}${body}</section></div>`;
  }

  /* ---------- Review ---------- */
  // after the trust ramp, the Certain ZIP (avenra) applies by auto-rule, so it is not in the queue
  const RV = () => (st.ramp === "ramp" ? D.review : D.review.filter((r) => r.kind !== "ramp"));
  const KIND = {
    downgrade: { pill: "held", why: "Held: downgrade" },
    threat: { pill: "threat", why: "Held: threat found" },
    notscanned: { pill: "notscanned", why: "Held: not scanned" },
    ramp: { pill: "certain", why: "Trust ramp: would apply to GF and PW" },
    likely: { pill: "likely", why: null },
    unsure: { pill: "unsure", why: null },
    nomatch: { pill: "nomatch", why: "No product scored high enough" },
  };
  const bulkItems = () => RV().filter((r) => r.kind === "likely" && r.candidates.length === 1);
  const selItem = () => RV().find((r) => r.id === st.sel) || RV()[0];
  const pickIdx = (it) => st.pick[it.id] ?? 0;
  function queueWhy(it) {
    const k = KIND[it.kind];
    if (k.why) return k.why;
    if (it.candidates.length === 1) return `${BAND[it.band].label}: ${it.candidates[0].name}`;
    return `${BAND[it.band].label}: ${it.candidates.length} candidates`;
  }
  function queueCard(state) {
    if (state === "loading") {
      return `<section class="card queue" aria-busy="true"><div class="queue__head">${sk("40%")}${sk("100%", "t-lg")}</div><div class="queue-list">${Array.from({ length: 7 }, () => `<div class="queue-item">${sk("4.5rem", "pill")}${sk("90%")}${sk("60%")}</div>`).join("")}</div></section>`;
    }
    const b = bulkItems();
    return `<section class="card queue" aria-labelledby="queue-title">
      <div class="queue__head">
        <div class="queue__head-row"><h2 class="card__title is-sm" id="queue-title">Waiting <span class="num muted">${RV().length}</span></h2>
          <label class="switch"><input type="checkbox" id="kbd-toggle" ${st.shortcuts ? "checked" : ""}>Shortcuts</label></div>
        <button class="btn queue__bulk" type="button" id="bulk-btn">${icon("list-checks")}<span>Approve all Likely with one <span class="nowrap">candidate <span class="num">(${b.length})</span></span></span></button>
      </div>
      <ul class="queue-list" role="listbox" id="queue" tabindex="0" aria-label="ZIPs waiting for a decision" aria-activedescendant="q-${selItem().id}">
        ${RV().map((it) => `<li class="queue-item" role="option" id="q-${it.id}" data-id="${it.id}" aria-selected="${it.id === selItem().id}">
          <span class="queue-item__top">${pill(KIND[it.kind].pill)}<span class="queue-item__time">${time(it.at)}</span></span>
          <span class="mono trunc queue-item__file" title="${esc(it.file)}">${esc(it.file)}</span>
          <span class="queue-item__why trunc">${esc(queueWhy(it))}</span></li>`).join("")}
      </ul></section>`;
  }
  const cmpVer = (a, b) => { const x = a.split(".").map(Number), y = b.split(".").map(Number); for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d; } return 0; };
  function detailCard(state) {
    if (state === "loading") {
      return `<section class="card detail" aria-busy="true"><div class="detail__head"><div style="flex:1;display:grid;gap:var(--space-3)">${sk("55%", "t-lg")}${sk("35%")}</div></div>
        <div class="detail__sections"><div class="detail__sec">${sk("40%")}<div style="height:var(--space-4)"></div>${sk("100%", "t-lg")}</div><div class="detail__sec">${sk("40%")}<div style="height:var(--space-4)"></div>${sk("80%")}</div>
        <div class="detail__sec is-wide">${sk("30%")}<div style="height:var(--space-4)"></div>${sk("100%")}<div style="height:var(--space-3)"></div>${sk("90%")}</div>
        <div class="detail__sec is-wide">${sk("30%")}<div style="height:var(--space-4)"></div><span class="sk" style="height:7rem"></span></div></div></section>`;
    }
    const it = selItem();
    const cand = it.candidates[pickIdx(it)];
    const alerts = [];
    if (state === "error") alerts.push(alert("danger", "triangle-alert", "GPLFamily can't be reached: HTTP 401 (the Shop Manager key was refused).", "Updates for it are waiting.", { label: "Test connection", icon: "refresh-cw", mock: "Would test the GPLFamily connection. Nothing was sent." }));
    if (it.kind === "downgrade") alerts.push(alert("danger", "shield-alert", `Held: downgrade. Your stores have ${cand.current}; this ZIP is ${it.zipVersion}.`, "Apply anyway only if you mean to go back to the older version."));
    if (it.kind === "threat") alerts.push(alert("danger", "shield-x", `Held: threat found (${it.threat}). This ZIP wasn't uploaded and can only be discarded.`));
    if (it.kind === "notscanned") alerts.push(alert("warning", "shield-question", `Held: not scanned. Windows Defender couldn't check this ZIP (${it.scanReason}).`, "Apply anyway uploads it without a scan result."));
    if (it.kind === "ramp") alerts.push(alert("info", "bot", "Trust ramp 37 / 50: this ZIP is Certain and would apply to GF and PW.", "Approving exactly this plan counts toward 50. Picking another product or discarding resets the count to 0 and flags the band cut-offs for a review."));

    // version compare
    let vc;
    if (cand) {
      const lowerZip = cmpVer(it.zipVersion, cand.current) < 0;
      const side = (label, v, lower) => `<div class="vc-side${lower ? " is-lower" : ""}"><small>${label}</small><span class="vc-num">${v}</span>${lower ? `<span class="vc-lower">${icon("triangle-alert")}Lower</span>` : ""}</div>`;
      vc = `<div class="version-compare">${side("On your stores now", cand.current, !lowerZip && false)}<span class="vc-arrow">${icon("arrow-right")}</span>${side("This ZIP", it.zipVersion, lowerZip)}</div>`;
    } else vc = `<p class="muted" style="font-size:var(--text-sm)">${it.kind === "threat" ? "Not compared: the scan held this ZIP before matching." : "No product matched, so there's nothing to compare."} This ZIP is <span class="num">${it.zipVersion}</span>.</p>`;

    const sc = it.scan;
    const scan = sc.state === "clean" ? `<p class="scan-line">${icon("shield-check", "res-icon-success")}<span><strong>No threats found</strong><br><span class="muted">Windows Defender, ${sc.secs} s, at ${time(sc.at)}</span></span></p>`
      : sc.state === "threat" ? `<p class="scan-line">${icon("shield-x", "res-icon-danger")}<span><strong>Threat found: ${esc(it.threat)}</strong><br><span class="muted">Windows Defender, at ${time(sc.at)}. Not uploaded.</span></span></p>`
      : `<p class="scan-line">${icon("shield-question", "res-icon-warning")}<span><strong>Not scanned</strong><br><span class="muted">${esc(it.scanReason)}, at ${time(sc.at)}</span></span></p>`;

    const m = it.inside;
    const insideRow = (role, x) => `<li><span class="role">${role}</span><span class="what">${x ? `${esc(x.name)}${x.type ? ` <span class="muted">${x.type.toLowerCase()}</span>` : ""}<span class="mono">${esc(x.folder)}</span>` : `<span class="muted">None</span>`}</span><span class="ver num">${x ? x.version : ""}</span></li>`;
    const inside = `<ul class="inside">${insideRow("Main", m.main)}${insideRow("Child", m.child)}${m.bundled.length ? m.bundled.map((b, i) => insideRow(i ? "" : "Bundled", b)).join("") : insideRow("Bundled", null)}</ul>`;

    let cands;
    if (it.candidates.length) {
      cands = `<ul class="cand-list" role="radiogroup" aria-label="Candidates">${it.candidates.map((c, i) => `<li class="candidate-card" role="radio" aria-checked="${i === pickIdx(it)}" tabindex="${i === pickIdx(it) ? 0 : -1}" data-i="${i}">
        <span class="cand-rank"><span class="cand-rank__n">${i + 1}</span><span class="kbd-hint" aria-hidden="true">${i + 1}</span></span>
        <div><p class="cand-name">${esc(c.name)} <span class="muted">${c.type}, <span class="mono">${esc(c.slug)}</span></span></p>
          <p class="cand-stores">${c.stores.map((code) => `<a href="#" data-mock="Would open ${esc(c.name)} on ${esc(store(code).name)} in your browser.">${storeBadge(code)} product page${icon("external-link")}</a>`).join("")}</p>
          <ul class="reasons" aria-label="Reasons">${[...c.reasons].sort((x, y) => y.pts - x.pts).map((r) => `<li class="reason ${r.pts >= 0 ? "is-plus" : "is-minus"}"><b>${r.pts >= 0 ? "+" : "−"}${Math.abs(r.pts)}</b>${esc(r.text)}</li>`).join("")}</ul></div>
        <div class="score"><span class="score__num">${c.score} <small>points</small></span><span class="score-bar" aria-hidden="true"><span style="width:${Math.max(0, c.score)}%"></span></span>${i === 0 ? pill(it.band === "certain" ? "certain" : it.band) : ""}</div></li>`).join("")}</ul>`;
    } else if (it.kind === "threat") {
      cands = `<p class="muted" style="font-size:var(--text-sm)">Not matched: the scan held this ZIP first.</p>`;
    } else {
      cands = `<div class="empty" style="padding:0">${icon("search-x", "i-lg empty__icon")}<p class="empty__text">No product scored high enough to suggest. Paste the product's address on any store to link this ZIP to it.</p></div>`;
    }

    let plan;
    if (!cand) plan = `<p class="muted" style="font-size:var(--text-sm)">${it.kind === "threat" ? "No change plan: this ZIP can only be discarded." : "The change plan appears once this ZIP is linked to a product."}</p>`;
    else {
      const newFile = `${cand.slug}-${it.zipVersion}.zip`, oldFile = `${cand.slug}-${cand.current}.zip`;
      const gfDown = state === "error";
      plan = `<ul class="change-plan"><li><span class="target">${icon("hard-drive")}S3 <small>upload</small></span><span class="files"><span class="mono">${newFile}</span></span></li>
        ${cand.stores.map((code) => `<li><span class="target">${storeBadge(code)} <small>Download slot</small></span><span class="files">${gfDown && code === "GF" ? `<span class="is-wait">${icon("triangle-alert")}Waiting: GPLFamily can't be reached</span>` : `<span class="mono is-old">${oldFile}</span>${icon("arrow-right")}<span class="sr-only">to</span><span class="mono">${newFile}</span>`}</span></li>`).join("")}</ul>
        <p class="plan-note">Nothing changes until you approve. After each write, the store is read back to check it shows the new file.</p>`;
    }

    const K = (k) => `<span class="kbd-hint" aria-hidden="true">${k}</span>`;
    const btn = (label, ic, cls, key, mock) => `<button class="btn ${cls}" type="button" data-mock="${esc(mock)}" ${key ? `aria-keyshortcuts="${key}"` : ""}>${icon(ic)}${label}${key ? K(key.toUpperCase()) : ""}</button>`;
    const target = cand ? cand.stores.join(" and ") : "";
    const acts = [];
    if (["ramp", "likely", "unsure"].includes(it.kind)) acts.push(btn("Approve and apply", "check", "is-primary", "a", `Would approve and apply ${it.file} to ${target} as ${cand.name}. Nothing was sent.`));
    if (["downgrade", "notscanned"].includes(it.kind)) acts.push(`<button class="btn" type="button" id="apply-anyway">${icon("shield-alert")}Apply anyway</button>`);
    if (it.kind !== "threat" && it.kind !== "notscanned") acts.push(btn("Paste URL", "clipboard-paste", it.kind === "nomatch" ? "is-primary" : "", "u", `Would ask for a product address to link ${it.file} to. Nothing was sent.`));
    acts.push(`<span class="spacer"></span>`);
    acts.push(btn("Discard", "x", "is-danger", "d", `Would discard ${it.file}. No store changes.${it.kind === "ramp" ? " Discarding a trust-ramp item is a disagreement, so the ramp resets to 0 / 50 and the band cut-offs are flagged for a review." : ""} Nothing was sent.`));
    const legend = `<p class="kbd-legend" aria-label="Keyboard shortcuts"><span>${K("J")}${K("K")} next, previous</span>${it.candidates.length > 1 ? `<span>${K("1")}–${K(String(it.candidates.length))} pick a candidate</span>` : ""}${["ramp", "likely", "unsure"].includes(it.kind) ? `<span>${K("A")} approve</span>` : ""}${it.kind !== "threat" && it.kind !== "notscanned" ? `<span>${K("U")} paste URL</span>` : ""}<span>${K("D")} discard</span>${st.shortcuts ? "" : "<span>Shortcuts are off</span>"}</p>`;
    const onlyDiscard = it.kind === "threat" ? `<p class="muted" style="font-size:var(--text-sm)">A ZIP with a threat can only be discarded.</p>` : "";

    return `<section class="card detail" aria-labelledby="detail-title" id="detail">
      <div class="detail__head"><div style="min-width:0"><h2 class="detail__file" id="detail-title">${esc(it.file)}</h2>
        <p class="detail__meta">${it.size}, added by you at ${time(it.at)} ${TZ} (${ago(it.at)})</p></div>${pill(KIND[it.kind].pill)}</div>
      ${alerts.join("")}
      <div class="detail__sections" style="margin-top:var(--space-5)">
        <div class="detail__sec"><h3 class="sec-title">Version</h3>${vc}</div>
        <div class="detail__sec"><h3 class="sec-title">Scan</h3>${scan}</div>
        <div class="detail__sec is-wide"><h3 class="sec-title">Inside the ZIP</h3>${inside}</div>
        <div class="detail__sec is-wide"><h3 class="sec-title">Candidates <span class="muted num">${it.candidates.length || ""}</span></h3>${cands}</div>
        <div class="detail__sec is-wide"><h3 class="sec-title">Change plan</h3>${plan}</div>
      </div>
      <div class="actions">${onlyDiscard}${acts.join("")}</div>${legend}</section>`;
  }
  function review(state) {
    if (state === "empty") {
      return `<div class="page">${pageHead("Review")}<section class="card"><div class="empty is-center"><span class="empty__icon">${icon("inbox", "i-lg")}</span>
        <p class="empty__text">Nothing waiting. ZIPs that need a decision appear here.</p><a class="btn" href="#/upload">${icon("upload")}Open Upload</a></div></section></div>`;
    }
    const sub = state === "loading" ? "Loading the queue." : `<span class="num">${RV().length}</span> ZIPs need a decision. Nothing changes on a store until you approve.`;
    return `<div class="page">${pageHead("Review", sub)}<div class="review-grid">${queueCard(state)}${detailCard(state)}</div></div>`;
  }
  function selectReview(id, focusQueue) {
    st.sel = id;
    render(false);
    if (focusQueue) $("#queue")?.focus();
    const list = $("#queue"), li = $(`#q-${id}`);
    if (list && li) {
      if (li.offsetTop < list.scrollTop) list.scrollTop = li.offsetTop - 8;
      else if (li.offsetTop + li.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = li.offsetTop + li.offsetHeight - list.clientHeight + 8;
    }
  }
  function moveSel(delta, focusQueue) {
    const L = RV(), i = L.findIndex((r) => r.id === selItem().id);
    const j = Math.max(0, Math.min(L.length - 1, i + delta));
    if (j !== i) selectReview(L[j].id, focusQueue);
  }
  function pickCand(i) {
    const it = selItem();
    if (i >= it.candidates.length) return;
    st.pick[it.id] = i;
    render(false);
    const c = it.candidates[i];
    toast(`Picked candidate ${i + 1}: ${c.name}`, "The change plan now targets this product.", true);
  }
  function wireReview() {
    const q = $("#queue");
    if (!q) return;
    q.addEventListener("click", (e) => { const li = e.target.closest(".queue-item"); if (li) selectReview(li.dataset.id, true); });
    q.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); moveSel(1, true); }
      if (e.key === "ArrowUp") { e.preventDefault(); moveSel(-1, true); }
      if (e.key === "Home") { e.preventDefault(); selectReview(RV()[0].id, true); }
      if (e.key === "End") { e.preventDefault(); selectReview(RV().at(-1).id, true); }
    });
    $("#kbd-toggle").addEventListener("change", (e) => { st.shortcuts = e.target.checked; render(false); $("#kbd-toggle").focus(); });
    $("#bulk-btn").addEventListener("click", () => {
      const b = bulkItems();
      toast(`Would approve ${b.length} Likely ZIPs`, `${b.map((x) => x.file).join(", ")}. Each applies to its one candidate. Nothing was sent.`, true);
    });
    $("#apply-anyway")?.addEventListener("click", (e) => {
      const it = selItem(), c = it.candidates[pickIdx(it)];
      const newFile = `${c.slug}-${it.zipVersion}.zip`, oldFile = `${c.slug}-${c.current}.zip`;
      SS.confirm({
        opener: e.currentTarget,
        title: `Apply ${it.file} anyway?`,
        lead: it.kind === "downgrade" ? `Held: downgrade. Your stores have ${c.current}; this ZIP is ${it.zipVersion}.` : `Held: not scanned. Windows Defender couldn't check this ZIP (${it.scanReason}).`,
        plan: [{ target: "S3", label: "upload", to: newFile }, ...c.stores.map((code) => ({ target: code, label: "Download slot", from: oldFile, to: newFile }))],
        note: `This points ${c.stores.length === 2 ? "both stores" : "the store"} at ${newFile}. You can roll back to ${oldFile} from the product's History.`,
        confirm: "Apply anyway",
        danger: true,
        done: `Would apply ${it.file} to ${c.stores.join(" and ")}. Nothing was sent.`,
      });
    });
    $$(".candidate-card").forEach((c) => {
      c.addEventListener("click", (e) => { if (e.target.closest("a")) return; pickCand(Number(c.dataset.i)); $(`.candidate-card[data-i="${c.dataset.i}"]`)?.focus(); });
      c.addEventListener("keydown", (e) => {
        const i = Number(c.dataset.i), len = selItem().candidates.length;
        let to = null;
        if (e.key === "ArrowDown" || e.key === "ArrowRight") to = (i + 1) % len;
        if (e.key === "ArrowUp" || e.key === "ArrowLeft") to = (i - 1 + len) % len;
        if (e.key === " " || e.key === "Enter") to = i;
        if (to === null) return;
        e.preventDefault(); pickCand(to); $(`.candidate-card[data-i="${to}"]`)?.focus();
      });
    });
  }
  function flash(sel) {
    const b = $(sel);
    if (!b) return false;
    b.focus();
    b.click();
    return true;
  }
  document.addEventListener("keydown", (e) => {
    // nothing behind a modal dialog or an open popover reacts to a single key (finding 1)
    if (document.querySelector("dialog[open]") || document.querySelector(".popover")) return;
    if (st.route !== "review" || !st.shortcuts || screenState() === "loading" || screenState() === "empty") return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t.closest && t.closest("input, textarea, select, [contenteditable]")) return;
    const k = e.key.toLowerCase();
    // if focus is in the detail card (which J and K redraw), it moves to the queue instead of being lost
    const lost = () => !!$("#detail")?.contains(document.activeElement) || document.activeElement === document.body;
    if (k === "j") { e.preventDefault(); moveSel(1, lost()); toast("J: next ZIP", selItem().file, true); }
    else if (k === "k") { e.preventDefault(); moveSel(-1, lost()); toast("K: previous ZIP", selItem().file, true); }
    else if (["1", "2", "3"].includes(k)) { e.preventDefault(); const l = lost(); pickCand(Number(k) - 1); if (l) $(`.candidate-card[data-i="${Number(k) - 1}"]`)?.focus(); }
    else if (k === "a") { if (flash('#detail [aria-keyshortcuts="a"]')) e.preventDefault(); }
    else if (k === "u") { if (flash('#detail [aria-keyshortcuts="u"]')) e.preventDefault(); }
    else if (k === "d") { if (flash('#detail [aria-keyshortcuts="d"]')) e.preventDefault(); }
  });

  /* ---------- part B placeholders ---------- */
  function placeholder(id) {
    const label = NAV.find((x) => x.id === id).label;
    return `<div class="page">${pageHead(label)}<section class="card"><div class="empty is-center"><span class="empty__icon">${icon(NAV.find((x) => x.id === id).icon, "i-lg")}</span>
      <p class="empty__text">${label} is designed in part B of the mockup.</p><p class="empty__sub">Part A covers the shell, Dashboard, Upload and Review.</p><a class="btn" href="#/dashboard">Open Dashboard</a></div></section></div>`;
  }

  /* ---------- toasts ---------- */
  function toast(title, detail, mock) {
    const region = $("#toasts");
    const host = document.querySelector("dialog[open]") || document.body; // a modal dialog is in the top layer
    if (region.parentElement !== host) host.append(region);
    const el = document.createElement("div");
    el.className = `toast${mock ? " is-mock" : ""}`;
    el.innerHTML = `${icon(mock ? "flask-conical" : "info")}<div><p class="toast__title"></p><p class="muted"></p></div><button class="btn is-ghost icon-btn" type="button" aria-label="Dismiss">${icon("x")}</button>`;
    el.querySelector(".toast__title").textContent = (mock ? "Mockup: " : "") + title;
    el.querySelector(".muted").innerHTML = mt(detail); // escaped; file names in Plex Mono
    el.querySelector("button").addEventListener("click", () => el.remove());
    region.prepend(el);
    while (region.children.length > 3) region.lastChild.remove();
    setTimeout(() => el.remove(), 7000);
  }
  document.addEventListener("click", (e) => {
    const m = e.target.closest("[data-mock]");
    if (!m) return;
    e.preventDefault();
    const c = m.cloneNode(true);
    c.querySelectorAll(".kbd-hint, .sr-only").forEach((x) => x.remove()); // "Discard", not "DiscardD"
    const label = (c.textContent || "").trim().replace(/\s+/g, " ");
    toast(label || "Action", m.dataset.mock, true);
  });
  document.addEventListener("click", (e) => {
    const w = e.target.closest("[data-why]");
    if (w) { whyPopover(w); return; }
    const h = e.target.closest("[data-health]");
    if (h) healthPopover(h);
  });

  /* ---------- render ---------- */
  function syncControls() {
    $("#ctl-disk").checked = st.lowDisk;
    $("#ctl-brake").checked = st.brake;
    $("#ctl-teach").value = st.teach;
    $(`#ctl-state input[value="${screenState()}"]`).checked = true;
    // a screen without an empty state says so in the switch (finding 17)
    const emptyOpt = $('#ctl-state input[value="empty"]');
    emptyOpt.disabled = noEmpty();
    emptyOpt.nextElementSibling.textContent = noEmpty() ? "Empty: none" : "Empty";
    emptyOpt.parentElement.title = noEmpty() ? "Settings, App has no empty state: every setting has a value from the first start." : "";
    $(`#ctl-theme input[value="${st.theme}"]`).checked = true;
    $(`#ctl-ramp input[value="${st.ramp}"]`).checked = true;
  }
  function render(routeChanged) {
    SS.closePopover(false);
    SS.beforeRender(); // part B screens cancel pending debounced redraws here (finding 27)
    applyTheme();
    renderNav(); renderHealth(); renderPause(); renderStrip(); applyCollapse(); syncControls();
    const s = screenState();
    const B = SS.screens[st.route];
    const html = st.route === "dashboard" ? dashboard(s) : st.route === "upload" ? upload(s) : st.route === "review" ? review(s) : B ? B.render(s) : placeholder(st.route);
    $("#shell").classList.toggle("is-wizard", st.route === "wizard");
    $("#disk-banner").hidden = !st.lowDisk || st.route === "wizard";
    const qScroll = $("#queue")?.scrollTop || 0;
    $("#main").innerHTML = html;
    if ($("#queue")) $("#queue").scrollTop = qScroll;
    $("#main").setAttribute("aria-busy", String(s === "loading"));
    const navItem = NAV.find((x) => x.id === st.route);
    document.title = `${navItem ? navItem.label : B ? B.title : "ShelfSync"}, ShelfSync mockup (sample data)`;
    if (st.route === "dashboard") wireChart();
    if (st.route === "review") wireReview();
    if (B && B.wire) B.wire(s);
    writeHash();
    // every navigation (a new screen, a Settings sub-page, a wizard step, a product) moves focus to the new heading (finding 2)
    if (routeChanged) { window.scrollTo(0, 0); focusHeading(routeChanged === "within"); }
  }
  // a new screen focuses its page title; a move inside a screen (Settings sub-page, wizard step) focuses that part's heading
  function focusHeading(within) {
    const h = (within && $("#main [data-nav-focus]")) || $("#main .page-title") || $("#main");
    h.focus({ preventScroll: true });
  }

  $("#ctl-state").addEventListener("change", (e) => { st.states[st.route] = e.target.value; render(false); });
  $("#ctl-theme").addEventListener("change", (e) => { st.theme = e.target.value; render(false); });
  // back to the ramp means auto-apply is off, so the brake can't be tripped (finding 28); render rewrites the hash
  $("#ctl-ramp").addEventListener("change", (e) => { st.ramp = e.target.value; if (st.ramp === "ramp") st.brake = false; render(false); });
  $("#ctl-teach").addEventListener("change", (e) => setTeach(e.target.value));
  // teaching state; finishing announces once through the polite live region (the toast region) and stays on the Dashboard
  function setTeach(v) {
    const finished = st.teach === "running" && v === "done";
    st.teach = v;
    render(false);
    if (finished) toast("Teaching finished", `${n(TEACH.total)} current files read. Each product now has a fingerprint "learned from current file".`, false);
  }
  $("#ctl-disk").addEventListener("change", (e) => { st.lowDisk = e.target.checked; render(false); });
  $("#ctl-brake").addEventListener("change", (e) => { st.brake = e.target.checked; if (st.brake) st.ramp = "done"; render(false); });
  $("#pause-btn").addEventListener("click", () => { st.paused = !st.paused; st.pausedAt = D.NOW; render(false); });
  $("#help-btn").addEventListener("click", (e) => SS.openHelp(e.currentTarget));
  $("#collapse-btn").addEventListener("click", () => {
    const now = $("#shell").classList.contains("is-collapsed");
    st.collapsed = !now; applyCollapse();
  });
  matchMedia("(min-width: 80rem)").addEventListener("change", () => { st.collapsed = null; applyCollapse(); });
  let ready = false; // part B screens register after this file runs; nothing renders before they have
  // every hash change is a navigation; hashes that aren't routes (none should occur) are ignored
  window.addEventListener("hashchange", () => { if (!ready || !location.hash.startsWith("#/")) return; const prev = st.route; readHash(); render(prev === st.route ? "within" : true); });
  $(".skip-link").addEventListener("click", (e) => { e.preventDefault(); $("#main").focus(); });
  // the strip's tooltips close on Esc without moving the pointer or focus (WCAG 1.4.13), and come back after leaving
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$(".has-tip").forEach((t) => { t.classList.add("tip-off"); t.classList.remove("is-open"); }); });
  const tipsBack = () => $$(".has-tip").forEach((t) => t.classList.remove("tip-off"));
  $("#strip").addEventListener("mouseleave", tipsBack);
  $("#strip").addEventListener("focusout", tipsBack);

  // Shared helpers for part B (overlays.js, screens-b.js). Those files load after this one; the first render waits for them.
  const SS = (window.SS = {
    D, st, $, $$, esc, icon, store, dot, storeBadge, fmt, time, ago, n, TZ, sampleTag, BAND, pill, pageHead, alert, sk,
    toast, render, screenState, downStore, counts, NAV, SET_SUBS, mt, writeHash, focusHeading, brakeOn, whyBtn,
    screens: {}, confirm: () => {}, openHelp: () => {}, popover: () => {}, closePopover: () => {}, beforeRender: () => {},
    setTeach: (v) => setTeach(v),
  });
  document.addEventListener("DOMContentLoaded", () => { ready = true; readHash(); render(false); document.fonts.ready.then(fitStrip); });
})();
