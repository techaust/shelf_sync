/* P3.5 capture helper: redraws the current mockup page at 2x and posts it as a PNG.
 *
 * Loaded into the pane's page with javascript_tool; never part of the mockup.
 *   await SSCapture.shot({ name: "01-dashboard-light.png", port: 8766 })            // full page height
 *   await SSCapture.shot({ name: "x14-confirm-light.png", port: 8766, mode: "viewport" }) // 1440 x 900 only
 *   await SSCapture.shot({ name: "fidelity-x.png", keepBar: true })                       // keep the mock bar
 *
 * The owner's set leaves out the "Mockup controls" bar: it is hidden on the live page for the
 * moment of measuring and cloning, removed from the clone, then put back as it was. The mockup's
 * files are never changed; the README records each shot's state instead.
 *
 * How: clone the rendered DOM (with live form state), inline every stylesheet with its
 * fonts as data URLs, inline the icon sprite and the logo, wrap the clone in an SVG
 * foreignObject the size of the page, draw that onto a canvas at scale 2, and POST the PNG
 * to receiver.py on 127.0.0.1. No packages; nothing leaves 127.0.0.1.
 */
(function () {
  "use strict";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const cache = new Map();

  const blobToDataURL = (blob) =>
    new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(blob); });

  async function dataURL(url) {
    if (cache.has(url)) return cache.get(url);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`fetch ${url}: ${r.status}`);
    const blob = await r.blob();
    const typed = url.endsWith(".svg") ? new Blob([blob], { type: "image/svg+xml" })
      : url.endsWith(".woff2") ? new Blob([blob], { type: "font/woff2" }) : blob;
    const d = await blobToDataURL(typed);
    cache.set(url, d);
    return d;
  }

  // every rule of every same-origin sheet, with url(...) turned into data URLs
  async function collectCSS() {
    let css = "";
    for (const sheet of document.styleSheets) {
      let rules;
      try { rules = sheet.cssRules; } catch { continue; }
      const base = sheet.href || location.href;
      let text = Array.from(rules, (r) => r.cssText).join("\n");
      const urls = new Set();
      text.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (_, __, u) => { if (!u.startsWith("data:") && !u.startsWith("#")) urls.add(u); return _; });
      for (const u of urls) {
        const abs = new URL(u, base).href;
        const d = await dataURL(abs);
        text = text.split(u).join(d);
      }
      css += text + "\n";
    }
    return css;
  }

  async function spriteSymbols() {
    const uses = document.querySelectorAll("use");
    const files = new Set();
    uses.forEach((u) => { const h = u.getAttribute("href") || ""; const f = h.split("#")[0]; if (f) files.add(new URL(f, location.href).href); });
    let out = "";
    for (const f of files) {
      const t = await (await fetch(f, { cache: "no-store" })).text();
      const doc = new DOMParser().parseFromString(t, "image/svg+xml");
      doc.querySelectorAll("symbol").forEach((s) => { out += new XMLSerializer().serializeToString(s); });
    }
    return out;
  }

  function syncFormState(src, dst) {
    const a = src.querySelectorAll("input, select, textarea");
    const b = dst.querySelectorAll("input, select, textarea");
    a.forEach((el, i) => {
      const c = b[i];
      if (!c) return;
      if (el.tagName === "INPUT") {
        if (el.type === "checkbox" || el.type === "radio") { if (el.checked) c.setAttribute("checked", ""); else c.removeAttribute("checked"); }
        else c.setAttribute("value", el.value);
      } else if (el.tagName === "SELECT") {
        Array.from(c.options).forEach((o, k) => { if (el.options[k].selected) o.setAttribute("selected", ""); else o.removeAttribute("selected"); });
      } else c.textContent = el.value;
    });
  }

  async function build(mode, keepBar) {
    // the full viewport width (1440): a full-page image has no scrollbar, so the page is measured
    // for a moment with the scrollbar hidden (and the mock bar, unless kept), then put back as it was
    const W = window.innerWidth;
    const root = document.documentElement;
    const bar = keepBar ? null : document.querySelector(".mock-bar");
    const prevBar = bar ? bar.style.display : "";
    const prev = root.style.overflow;
    let H, clone;
    try {
      root.style.overflow = "hidden";
      if (bar) bar.style.display = "none";
      H = mode === "viewport" ? window.innerHeight : Math.max(root.scrollHeight, document.body.scrollHeight);
      clone = root.cloneNode(true);
      syncFormState(root, clone);
    } finally {
      root.style.overflow = prev;
      if (bar) bar.style.display = prevBar;
    }
    clone.style.overflow = prev;
    if (!clone.getAttribute("style")) clone.removeAttribute("style");
    if (bar) clone.querySelectorAll(".mock-bar").forEach((n) => n.remove());
    const css = await collectCSS();
    const symbols = await spriteSymbols();

    // modal dialogs live in the top layer; a clone can't, so it is pinned the way the UA pins :modal
    const liveDialogs = root.querySelectorAll("dialog");
    const cloneDialogs = clone.querySelectorAll("dialog");
    let modalCSS = "";
    liveDialogs.forEach((d, i) => {
      if (!d.matches(":modal")) return;
      const c = cloneDialogs[i];
      c.setAttribute("data-cap-modal", String(i));
      const bd = getComputedStyle(d, "::backdrop").backgroundColor;
      const back = document.createElement("div");
      back.setAttribute("data-cap-backdrop", "");
      back.setAttribute("style", `position:fixed;inset:0;background:${bd};z-index:2147483646`);
      c.parentNode.insertBefore(back, c);
    });
    // zero specificity and placed ahead of the page's CSS, like the browser's own :modal rules,
    // so the page's dialog rules (the help panel's full height, the dialog widths) still win
    modalCSS = ":where(dialog[data-cap-modal]){position:fixed;inset-block:0;" +
      "max-width:calc(100% - 6px - 2em);max-height:calc(100% - 6px - 2em);overflow:auto;visibility:visible}\n" +
      "dialog[data-cap-modal]{z-index:2147483647}\n";

    clone.querySelectorAll("script, link, noscript").forEach((n) => n.remove());
    clone.querySelectorAll("img").forEach((n) => n.removeAttribute("loading"));
    for (const img of clone.querySelectorAll("img[src]")) {
      const src = img.getAttribute("src");
      if (!src.startsWith("data:")) img.setAttribute("src", await dataURL(new URL(src, location.href).href));
    }
    clone.querySelectorAll("use").forEach((u) => {
      const h = u.getAttribute("href") || u.getAttribute("xlink:href") || "";
      if (h.includes("#")) u.setAttribute("href", "#" + h.split("#")[1]);
    });

    const style = document.createElement("style");
    // inside an SVG image, links don't match :link / :any-link, so the browser's own underline is lost;
    // it is put back at zero specificity, ahead of the page's CSS, so every page rule still wins
    style.textContent = ":where(a[href]){text-decoration:underline}\n" + modalCSS + css +
      "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}\n";
    const head = clone.querySelector("head") || clone.insertBefore(document.createElement("head"), clone.firstChild);
    head.appendChild(style);

    const body = clone.querySelector("body");
    const holder = document.createElement("div");
    holder.setAttribute("aria-hidden", "true");
    holder.innerHTML = `<svg xmlns="${SVG_NS}" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden">${symbols}</svg>`;
    body.insertBefore(holder.firstChild, body.firstChild);

    // :root rules match the SVG root inside the image, so it carries the html element's attributes
    const rootAttrs = Array.from(root.attributes).filter((a) => !/^xmlns/.test(a.name))
      .map((a) => ` ${a.name}="${a.value.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"`).join("");
    const html = new XMLSerializer().serializeToString(clone);
    const svg = `<svg xmlns="${SVG_NS}"${rootAttrs} width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
      `<foreignObject x="0" y="0" width="${W}" height="${H}">${html}</foreignObject></svg>`;
    return { svg, W, H };
  }

  async function render({ mode = "full", scale = 2, keepBar = false } = {}) {
    window.scrollTo(0, 0);
    await document.fonts.ready;
    const { svg, W, H } = await build(mode, keepBar);
    const img = new Image();
    img.decoding = "sync";
    const loaded = new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error("SVG image failed to load")); });
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    await loaded;
    await img.decode().catch(() => {});
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(W * scale);
    canvas.height = Math.round(H * scale);
    const ctx = canvas.getContext("2d");
    // draw twice: the first pass makes sure the embedded fonts are decoded before the kept pass
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    await new Promise((r) => setTimeout(r, 150));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
    return { blob, W, H, px: [canvas.width, canvas.height], svgBytes: svg.length };
  }

  async function shot({ name, port = 8766, mode = "full", scale = 2, keepBar = false }) {
    if (!/^[a-z0-9-]+\.png$/.test(name)) throw new Error("bad name");
    const { blob, W, H, px, svgBytes } = await render({ mode, scale, keepBar });
    const r = await fetch(`http://127.0.0.1:${port}/shot?name=${encodeURIComponent(name)}`, { method: "POST", headers: { "Content-Type": "image/png" }, body: blob });
    return { status: r.status, reply: await r.text(), layout: [W, H], px, pngBytes: blob.size, svgBytes, hash: location.hash, bar: !!keepBar, theme: document.documentElement.dataset.theme };
  }

  window.SSCapture = { shot, render, build };
})();
