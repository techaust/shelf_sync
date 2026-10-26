/* SAMPLE DATA for the P3.4 mockup. Every product, vendor, file, version, count and time here is made up.
   Nothing is read from the live stores, OmniSync or the research scripts. Product and studio names are invented
   to look like real WordPress themes and plugins; no real customer or person is named.
   Times are offsets from SAMPLE_NOW and are shown in this PC's local time zone, as the app will. */
"use strict";

window.SAMPLE = (() => {
  // "Now" for the sample: Monday 26 October 2026, 04:14 UTC.
  const NOW = Date.UTC(2026, 9, 26, 4, 14, 0);
  const min = (m) => NOW - m * 60000;

  // Store identifiers (05 section 2.3). The dot colours are per-store settings in the app (owner-picked, stored as
  // identifiers), so in the mockup they are data, not design tokens: the two values 05 section 2.3 approves.
  const stores = [
    { code: "GF", name: "GPLFamily", shape: "circle", dot: { light: "#4d4d99", dark: "#a3a3e6" }, latency: 182 },
    { code: "PW", name: "PluginWay", shape: "square", dot: { light: "#007b80", dark: "#3cc8cb" }, latency: 241 },
  ];
  const s3 = { name: "Amazon S3", latency: 96 };

  const catalogSize = 2398;

  const counts = { review: 10, partial: 1, cleanup: 7 };

  // 14 days, oldest first (13 to 26 October 2026). Weekends are 17-18 and 24-25.
  // ramp: trust ramp at 37 / 50, so auto-apply is off and every update is approved by you.
  // done: the ramp finished on 20 October; auto-rule applies Certain ZIPs from then on.
  const chart = {
    ramp: { auto: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], you: [9, 12, 7, 11, 2, 0, 8, 13, 6, 10, 12, 3, 0, 14] },
    done: { auto: [0, 0, 0, 0, 0, 0, 0, 9, 11, 8, 12, 5, 2, 17], you: [9, 12, 7, 11, 2, 0, 8, 4, 2, 3, 1, 0, 0, 6] },
  };

  // Latest updates (Dashboard). who: "you" | "auto"; result per store: "done" | "failed".
  const latest = [
    { at: min(3), product: "Harbor Child", slug: "harbor-child", from: "1.1.8", to: "1.2.0", stores: { GF: "done", PW: "done" }, who: "you", whoRamp: "you" },
    { at: min(11), product: "Stackmart", slug: "stackmart", from: "6.3.2", to: "6.4.0", stores: { GF: "done", PW: "failed" }, who: "you", whoRamp: "you" },
    { at: min(26), product: "Cartflux Product Filters", slug: "cartflux-product-filters", from: "2.6.0", to: "2.6.1", stores: { GF: "done", PW: "done" }, who: "auto", whoRamp: "you" },
    { at: min(41), product: "Quillstack Page Builder Pro (Extended licence, unlimited sites)", slug: "quillstack-page-builder-pro", from: "7.14.1", to: "7.14.2", stores: { GF: "done", PW: "done" }, who: "auto", whoRamp: "you" },
    { at: min(58), product: "Rankwise SEO Premium", slug: "rankwise-seo-premium", from: "21.2.4", to: "21.3.0", stores: { GF: "done", PW: "done" }, who: "auto", whoRamp: "you" },
    { at: min(83), product: "Oakfield Restaurant", slug: "oakfield", from: "3.0.9", to: "3.1.0", stores: { GF: "done" }, who: "you", whoRamp: "you" },
    { at: min(97), product: "Sitekit Backup Pro", slug: "sitekit-backup-pro", from: "4.0.1", to: "4.0.2", stores: { GF: "done", PW: "done" }, who: "auto", whoRamp: "you" },
    { at: min(132), product: "Ledgerline Invoices for WooCommerce", slug: "ledgerline-invoices", from: "5.9.0", to: "5.9.3", stores: { GF: "done", PW: "done" }, who: "you", whoRamp: "you" },
  ];

  // Upload batch: 12 JobRows. steps: inspect, scan, match, s3, GF, PW.
  // step state: "pending" | "running" | "done" | "held" | "failed"
  const S = (inspect, scan, match, s3, gf, pw) => ({ inspect, scan, match, s3, GF: gf, PW: pw });
  const batch = [
    { file: "avenra-3.2.1.zip", size: "8.4 MB", product: "Avenra", band: "certain",
      ramp: { steps: S("done", "done", "done", "pending", "pending", "pending"), result: { kind: "review", text: "Waiting in Review: trust ramp, would apply to GF and PW" } },
      done: { steps: S("done", "done", "done", "done", "done", "done"), result: { kind: "done", who: "auto", text: "Applied to GF and PW by auto-rule" } } },
    { file: "fluxform-pro-4.8.2.zip", size: "3.1 MB", product: "Fluxform Pro", band: "likely",
      steps: S("done", "done", "done", "pending", "pending", "pending"), result: { kind: "review", text: "Waiting in Review: Likely match" } },
    { file: "copperline-4.9.3.zip", size: "21.7 MB", product: "Copperline", band: "certain",
      steps: S("done", "done", "held", "pending", "pending", "pending"), result: { kind: "held", text: "Held: downgrade. Your stores have 5.2.0; this ZIP is 4.9.3." } },
    { file: "pixelhaven-gallery-pro-1.4.0.zip", size: "2.2 MB", product: null, band: null,
      steps: S("done", "held", "pending", "pending", "pending", "pending"), result: { kind: "threat", text: "Held: threat found (Backdoor:PHP/WebShell.A). This ZIP wasn't uploaded and can only be discarded." } },
    { file: "stackmart-6.4.0.zip", size: "14.9 MB", product: "Stackmart", band: "certain",
      steps: S("done", "done", "done", "done", "done", "failed"), result: { kind: "partial", text: "PluginWay didn't respond (HTTP 524, Cloudflare timeout). Nothing was changed there.", action: "Retry PluginWay" } },
    { file: "rankwise-seo-premium-21.3.1.zip", size: "6.8 MB", product: "Rankwise SEO Premium", band: "certain",
      steps: S("done", "done", "done", "running", "pending", "pending"), result: { kind: "running", text: "Uploading to S3", pct: 64 } },
    { file: "quillstack-page-builder-pro-extended-licence-unlimited-sites-7.14.3.zip", size: "38.2 MB", product: null, band: null,
      steps: S("done", "running", "pending", "pending", "pending", "pending"), result: { kind: "running", text: "Scanning with Windows Defender", pct: 30 } },
    { file: "sitekit-backup-pro-4.0.3.zip", size: "5.5 MB", product: "Sitekit Backup Pro", band: "certain",
      steps: S("done", "done", "done", "done", "running", "pending"), result: { kind: "running", text: "Writing to GPLFamily", pct: 80 } },
    { file: "harbor-child-1.2.0.zip", size: "0.4 MB", product: "Harbor Child", band: "certain",
      steps: S("done", "done", "done", "done", "done", "done"), result: { kind: "done", who: "you", text: "Applied to GF and PW, approved by you" } },
    { file: "lumen-booking-5.0.0.zip", size: "11.3 MB", product: "Lumen Booking", band: "certain",
      steps: S("done", "held", "pending", "pending", "pending", "pending"), result: { kind: "notscanned", text: "Held: not scanned. Windows Defender couldn't check this ZIP (the scan timed out after 120 s)." } },
    { file: "tessera-gallery-2.2.0.zip", size: "1.9 MB", product: null, band: "nomatch",
      steps: S("done", "done", "held", "pending", "pending", "pending"), result: { kind: "review", text: "Waiting in Review: no match" } },
    { file: "oakfield-restaurant-bundle-3.2.0.zip", size: "1.1 GB", product: null, band: null,
      steps: S("failed", "pending", "pending", "pending", "pending", "pending"), result: { kind: "failed", text: "Can't open oakfield-restaurant-bundle-3.2.0.zip: the unpacked size is over the 2 GB limit (2.6 GB). Nothing was uploaded." } },
  ];

  // Review queue. kind: downgrade | threat | notscanned | ramp | likely | unsure | nomatch
  const R = (pts, text) => ({ pts, text });
  const review = [
    {
      id: "copperline", file: "copperline-4.9.3.zip", size: "21.7 MB", at: min(6), kind: "downgrade", band: "certain",
      zipVersion: "4.9.3", productGuess: "Copperline",
      inside: { main: { type: "Theme", name: "Copperline", folder: "copperline/", version: "4.9.3", author: "Northbeam Studio" },
        child: { name: "Copperline Child", folder: "copperline-child/", version: "1.0.4" },
        bundled: [{ name: "Quillstack Builder", folder: "plugins/quillstack-builder.zip", version: "2.4.0" }, { name: "Tessera Slider", folder: "plugins/tessera-slider.zip", version: "6.1.3" }] },
      scan: { state: "clean", secs: 4.2, at: min(6) },
      candidates: [
        { name: "Copperline", type: "Theme", slug: "copperline", current: "5.2.0", score: 100, stores: ["GF", "PW"],
          reasons: [R(40, "Folder slug matches the product's URL slug (copperline)"), R(30, "Theme name in style.css matches the product name"), R(20, "Author matches the confirmed fingerprint (Northbeam Studio)"), R(10, "File name matches an approved file name")] },
      ],
    },
    {
      id: "pixelhaven", file: "pixelhaven-gallery-pro-1.4.0.zip", size: "2.2 MB", at: min(9), kind: "threat", band: null,
      zipVersion: "1.4.0", productGuess: null, threat: "Backdoor:PHP/WebShell.A",
      inside: { main: { type: "Plugin", name: "Pixelhaven Gallery Pro", folder: "pixelhaven-gallery-pro/", version: "1.4.0", author: "Pixelhaven" }, child: null, bundled: [] },
      scan: { state: "threat", secs: 2.8, at: min(9) },
      candidates: [],
    },
    {
      id: "lumen", file: "lumen-booking-5.0.0.zip", size: "11.3 MB", at: min(14), kind: "notscanned", band: "certain",
      zipVersion: "5.0.0", productGuess: "Lumen Booking", scanReason: "the scan timed out after 120 s",
      inside: { main: { type: "Plugin", name: "Lumen Booking", folder: "lumen-booking/", version: "5.0.0", author: "Lumen Works" }, child: null, bundled: [] },
      scan: { state: "notscanned", secs: 120, at: min(14) },
      candidates: [
        { name: "Lumen Booking", type: "Plugin", slug: "lumen-booking", current: "4.12.1", score: 92, stores: ["GF", "PW"],
          reasons: [R(40, "Folder slug matches the product's URL slug (lumen-booking)"), R(30, "Plugin name in the header matches the product name"), R(22, "Author matches the confirmed fingerprint (Lumen Works)")] },
      ],
    },
    {
      id: "avenra", file: "avenra-3.2.1.zip", size: "8.4 MB", at: min(18), kind: "ramp", band: "certain",
      zipVersion: "3.2.1", productGuess: "Avenra",
      inside: { main: { type: "Theme", name: "Avenra", folder: "avenra/", version: "3.2.1", author: "Fieldnote Themes" },
        child: { name: "Avenra Child", folder: "avenra-child/", version: "1.1.0" }, bundled: [] },
      scan: { state: "clean", secs: 3.1, at: min(18) },
      candidates: [
        { name: "Avenra", type: "Theme", slug: "avenra", current: "3.1.7", score: 100, stores: ["GF", "PW"],
          reasons: [R(40, "Folder slug matches the product's URL slug (avenra)"), R(30, "Theme name in style.css matches the product name"), R(20, "Author matches the confirmed fingerprint (Fieldnote Themes)"), R(10, "File name matches an approved file name")] },
      ],
    },
    {
      id: "fluxform", file: "fluxform-pro-4.8.2.zip", size: "3.1 MB", at: min(22), kind: "likely", band: "likely",
      zipVersion: "4.8.2", productGuess: "Fluxform Pro",
      inside: { main: { type: "Plugin", name: "Fluxform", folder: "fluxform-pro/", version: "4.8.2", author: "Fluxform" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 1.6, at: min(22) },
      candidates: [
        { name: "Fluxform Pro", type: "Plugin", slug: "fluxform-pro", current: "4.8.0", score: 70, stores: ["GF", "PW"],
          reasons: [R(40, "Folder slug matches the product's URL slug (fluxform-pro)"), R(25, "Plugin name matches after removing the edition word"), R(20, "Version 4.8.2 follows the stores' 4.8.0"), R(-15, "Edition word differs: the header says Fluxform, the product is Fluxform Pro")] },
      ],
    },
    {
      id: "brightcart", file: "brightcart-checkout-fields-1.9.6.zip", size: "0.9 MB", at: min(25), kind: "likely", band: "likely",
      zipVersion: "1.9.6", productGuess: "Brightcart Checkout Fields",
      inside: { main: { type: "Plugin", name: "Brightcart Checkout Field Editor", folder: "brightcart-checkout-fields/", version: "1.9.6", author: "Brightcart" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 0.9, at: min(25) },
      candidates: [
        { name: "Brightcart Checkout Fields", type: "Plugin", slug: "brightcart-checkout-fields", current: "1.9.4", score: 76, stores: ["GF", "PW"],
          reasons: [R(40, "Folder slug matches the product's URL slug (brightcart-checkout-fields)"), R(18, "Plugin name is close to the product name"), R(18, "Author matches the vendor on both stores")] },
      ],
    },
    {
      id: "nexa", file: "nexa-wishlist-premium-3.4.0.zip", size: "1.4 MB", at: min(31), kind: "likely", band: "likely",
      zipVersion: "3.4.0", productGuess: "WooCommerce Wishlist",
      inside: { main: { type: "Plugin", name: "Nexa WooCommerce Wishlist Premium", folder: "nexa-woocommerce-wishlist-premium/", version: "3.4.0", author: "Nexa" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 1.2, at: min(31) },
      candidates: [
        { name: "WooCommerce Wishlist", type: "Plugin", slug: "woocommerce-wishlist", current: "3.3.2", score: 68, stores: ["GF", "PW"],
          reasons: [R(35, "Plugin name matches after removing the vendor prefix (Nexa) and the edition word (premium)"), R(20, "Version 3.4.0 follows the stores' 3.3.2"), R(13, "Author matches the vendor on both stores")] },
      ],
    },
    {
      id: "vexel", file: "vexel-addons-for-elementor-2.12.0.zip", size: "4.6 MB", at: min(37), kind: "likely", band: "likely",
      zipVersion: "2.12.0", productGuess: "Vexel Addons for Elementor",
      inside: { main: { type: "Plugin", name: "Vexel Addons for Elementor", folder: "vexel-addons/", version: "2.12.0", author: "Vexel" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 2.0, at: min(37) },
      candidates: [
        { name: "Vexel Addons for Elementor", type: "Plugin", slug: "vexel-addons-for-elementor", current: "2.11.4", score: 74, stores: ["GF", "PW"],
          reasons: [R(30, "Plugin name in the header matches the product name"), R(24, "Author matches the vendor on both stores"), R(20, "Version 2.12.0 follows the stores' 2.11.4")] },
        { name: "Vexel Addons for Elementor Pro", type: "Plugin", slug: "vexel-addons-pro", current: "1.8.0", score: 43, stores: ["GF", "PW"],
          reasons: [R(30, "Plugin name in the header is close to the product name"), R(24, "Author matches the vendor on both stores"), R(4, "Folder slug shares the prefix vexel-addons"), R(-15, "Edition word differs: the product adds pro")] },
      ],
    },
    {
      id: "mailroom", file: "mailroom-smtp-pro-3.0.1.zip", size: "2.7 MB", at: min(46), kind: "unsure", band: "unsure",
      zipVersion: "3.0.1", productGuess: "Mailroom SMTP Pro",
      inside: { main: { type: "Plugin", name: "Mailroom", folder: "mailroom/", version: "3.0.1", author: "Postbox Labs" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 1.4, at: min(46) },
      candidates: [
        { name: "Mailroom SMTP Pro", type: "Plugin", slug: "mailroom-smtp-pro", current: "2.9.6", score: 49, stores: ["GF", "PW"],
          reasons: [R(25, "Plugin name is close to the product name"), R(20, "Author matches the vendor on both stores"), R(-10, "Folder slug (mailroom) differs from the product's URL slug"), R(14, "File name contains the product's slug")] },
        { name: "Mailroom SMTP", type: "Plugin", slug: "mailroom-smtp", current: "3.0.0", score: 30, stores: ["PW"],
          reasons: [R(25, "Plugin name is close to the product name"), R(20, "Author matches the vendor on PluginWay"), R(-15, "Edition word differs: the ZIP's file name adds pro")] },
        { name: "Mailroom Logs Addon", type: "Plugin", slug: "mailroom-logs-addon", current: "1.2.0", score: 6, stores: ["GF"],
          reasons: [R(15, "Author matches the vendor on GPLFamily"), R(6, "Name shares the word Mailroom"), R(-15, "Edition word differs: the product is an addon")] },
      ],
    },
    {
      id: "tessera", file: "tessera-gallery-2.2.0.zip", size: "1.9 MB", at: min(52), kind: "nomatch", band: "nomatch",
      zipVersion: "2.2.0", productGuess: null,
      inside: { main: { type: "Plugin", name: "Tessera Gallery", folder: "tessera-gallery/", version: "2.2.0", author: "Tessera" }, child: null, bundled: [] },
      scan: { state: "clean", secs: 1.1, at: min(52) },
      candidates: [],
    },
  ];

  // "Why?" (MAT-07, 05 section 5 WhyPanel): every signal and its points, per matched product. The four Review
  // products reuse their candidate reasons; the rest are written here. Points add up to each total.
  const why = {
    "harbor-child": { product: "Harbor Child", band: "certain", reasons: [R(40, "Folder slug matches the product's URL slug (harbor-child)"), R(30, "Theme name in style.css matches the product name"), R(20, "Parent theme in style.css matches the product's parent (Harbor)"), R(10, "File name matches an approved file name")] },
    stackmart: { product: "Stackmart", band: "certain", reasons: [R(40, "Folder slug matches the product's URL slug (stackmart)"), R(30, "Theme name in style.css matches the product name"), R(20, "Author matches the confirmed fingerprint (Fieldnote Themes)"), R(10, "File name matches an approved file name")] },
    "rankwise-seo-premium": { product: "Rankwise SEO Premium", band: "certain", reasons: [R(40, "Folder slug matches the product's URL slug (rankwise-seo-premium)"), R(30, "Plugin name in the header matches the product name"), R(20, "Author matches the confirmed fingerprint (Rankwise)"), R(10, "File name matches an approved file name")] },
    "sitekit-backup-pro": { product: "Sitekit Backup Pro", band: "certain", reasons: [R(40, "Folder slug matches the product's URL slug (sitekit-backup-pro)"), R(30, "Plugin name in the header matches the product name"), R(20, "Author matches the confirmed fingerprint (Sitekit)"), R(10, "File name matches an approved file name")] },
  };
  review.forEach((it) => { const c = it.candidates[0]; if (c && it.band) why[c.slug] = { product: c.name, band: it.band === "certain" ? "certain" : it.band, reasons: c.reasons }; });
  batch.forEach((j) => { if (j.product && j.band && j.band !== "nomatch") j.why = Object.keys(why).find((k) => why[k].product === j.product); });

  return { NOW, stores, s3, catalogSize, counts, chart, latest, batch, review, why, lastSync: min(14), nextSnapshotHourLocal: 2 };
})();
