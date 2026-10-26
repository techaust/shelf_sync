/* SAMPLE DATA for the P3.4 mockup, part B. All made up, like data.js: no live store, OmniSync or research output
   was read. The catalog is 2398 generated rows (a seeded generator, so it is the same on every load), with the
   part A products placed among them at the versions Review and Upload use. Store URLs use the reserved .example
   domain so they can never point at a real site. */
"use strict";

window.SAMPLE_B = (() => {
  const NOW = Date.UTC(2026, 9, 26, 4, 14, 0);
  const min = (m) => NOW - m * 60000;
  const day = (d, h = 0) => NOW - d * 86400000 - h * 3600000;

  // seeded generator (mulberry32), so the 2398 rows never change between loads
  let seed = 20261026;
  const rnd = () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const pick = (a) => a[Math.floor(rnd() * a.length)];

  const first = ["Aurora", "Basalt", "Cedar", "Driftwood", "Ember", "Fjord", "Granite", "Halcyon", "Indigo", "Juniper", "Kestrel", "Linden", "Meridian", "Northgate", "Onyx", "Pinecrest", "Quartz", "Redwood", "Saffron", "Tidewater", "Umber", "Vantage", "Willow", "Yarrow", "Zephyr", "Alder", "Birch", "Cobalt", "Dune", "Elmwood", "Flint", "Garnet", "Heron", "Ivory", "Jasper", "Kelpie", "Larch", "Maple", "Nimbus", "Orchid",
    "Arbor", "Beacon", "Canopy", "Delta", "Equinox", "Fable", "Glacier", "Hollow", "Inlet", "Jetty", "Keystone", "Lumina", "Marlow", "Nectar", "Oakmoss", "Prism", "Quill", "Ridgeline", "Solstice", "Thistle", "Upland", "Verve", "Wren", "Atlas", "Bramble", "Cinder", "Dapple", "Everly", "Fern", "Gable", "Hearth", "Iris", "Kindle", "Lattice", "Mosaic", "Nova", "Otter", "Pebble", "Rook", "Sable"];
  const pluginWords = ["Forms", "Booking", "Slider", "Gallery", "SEO", "Invoices", "Checkout Fields", "Wishlist", "Product Filters", "Backup", "Page Builder", "Popups", "Reviews", "Memberships", "Subscriptions", "Events", "Translate", "Cache", "Security", "Analytics", "Mega Menu", "Testimonials", "Quick View", "Bundles", "Points and Rewards", "Pre-Orders", "Bookings", "Size Charts", "Table Rates", "Variation Swatches"];
  const themeWords = ["", "Studio", "Shop", "Magazine", "Agency", "Restaurant", "Portfolio", "Fitness", "Hotel", "Law", "Blog", "Store", "Wedding", "Travel", "Education", "Medical", "Construction", "Salon"];
  const editions = ["", "", "", " Pro", " Premium", " Plus"];
  const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  const ver = () => `${1 + Math.floor(rnd() * 9)}.${Math.floor(rnd() * 15)}.${Math.floor(rnd() * 12)}`;

  // part A products, at the versions the other screens use. stores: which stores list it; pw: PW version if it differs
  const fixed = [
    { name: "Copperline", type: "Theme", slug: "copperline", updated: day(3, 2), v: "5.2.0", health: "stale" },
    { name: "Avenra", type: "Theme", slug: "avenra", v: "3.1.7" },
    { name: "Fluxform Pro", type: "Plugin", slug: "fluxform-pro", v: "4.8.0" },
    { name: "Brightcart Checkout Fields", type: "Plugin", slug: "brightcart-checkout-fields", v: "1.9.4" },
    { name: "WooCommerce Wishlist", type: "Plugin", slug: "woocommerce-wishlist", v: "3.3.2" },
    { name: "Vexel Addons for Elementor", type: "Plugin", slug: "vexel-addons-for-elementor", v: "2.11.4" },
    { name: "Vexel Addons for Elementor Pro", type: "Plugin", slug: "vexel-addons-pro", v: "1.8.0" },
    { name: "Mailroom SMTP Pro", type: "Plugin", slug: "mailroom-smtp-pro", v: "2.9.6" },
    { name: "Mailroom SMTP", type: "Plugin", slug: "mailroom-smtp", v: "3.0.0", stores: ["PW"] },
    { name: "Mailroom Logs Addon", type: "Plugin", slug: "mailroom-logs-addon", v: "1.2.0", stores: ["GF"] },
    { name: "Lumen Booking", type: "Plugin", slug: "lumen-booking", v: "4.12.1" },
    { name: "Stackmart", type: "Theme", slug: "stackmart", prev: "6.3.2", updated: min(11), v: "6.4.0", pw: "6.3.2", health: "partial" },
    { name: "Rankwise SEO Premium", type: "Plugin", slug: "rankwise-seo-premium", prev: "21.2.4", updated: min(58), v: "21.3.0", health: "stale" },
    { name: "Quillstack Page Builder Pro (Extended licence, unlimited sites)", type: "Plugin", slug: "quillstack-page-builder-pro", prev: "7.14.1", updated: min(41), v: "7.14.2" },
    { name: "Sitekit Backup Pro", type: "Plugin", slug: "sitekit-backup-pro", prev: "4.0.1", updated: min(97), v: "4.0.2", slots: 2 },
    { name: "Harbor Child", type: "Theme", slug: "harbor-child", prev: "1.1.8", updated: min(3), v: "1.2.0" },
    { name: "Cartflux Product Filters", type: "Plugin", slug: "cartflux-product-filters", prev: "2.6.0", updated: min(26), v: "2.6.1" },
    { name: "Oakfield Restaurant", type: "Theme", slug: "oakfield", prev: "3.0.9", updated: min(83), v: "3.1.0", stores: ["GF"] },
    { name: "Ledgerline Invoices for WooCommerce", type: "Plugin", slug: "ledgerline-invoices", prev: "5.9.0", updated: min(132), v: "5.9.3" },
    { name: "Tessera Slider", type: "Plugin", slug: "tessera-slider", updated: min(122), v: "6.1.3", health: "outside" },
    { name: "Tessera Gallery", type: "Plugin", slug: "tessera-gallery-legacy", v: "1.9.0" },
    // the three near-miss twin pairs (Cleanup), each half on one store
    { name: "Avenra Child", type: "Theme", slug: "avenra-child", v: "1.1.0", stores: ["GF"], health: "nearmiss" },
    { name: "Avenra Child", type: "Theme", slug: "avenra-child-2", v: "1.1.0", stores: ["PW"], health: "nearmiss" },
    { name: "Pixelpress Portfolio", type: "Theme", slug: "pixelpress-portfolio", v: "2.0.4", stores: ["GF"], health: "nearmiss" },
    { name: "Pixelpress Portfolio", type: "Theme", slug: "pixel-press-portfolio", v: "2.0.4", stores: ["PW"], health: "nearmiss" },
    { name: "Northwind Forms Pro", type: "Plugin", slug: "northwind-forms-pro", v: "3.6.1", stores: ["GF"], health: "nearmiss" },
    { name: "Northwind Forms Pro", type: "Plugin", slug: "northwind-form-pro", v: "3.6.1", stores: ["PW"], health: "nearmiss" },
  ];

  const TOTAL = 2398;
  const used = new Set(fixed.map((f) => f.slug));
  const rows = [];
  const mk = (f) => {
    const stores = f.stores || ["GF", "PW"];
    const ids = {};
    for (const s of stores) ids[s] = 10000 + Math.floor(rnd() * 89999);
    return {
      id: f.slug, name: f.name, type: f.type, slug: f.slug, stores, ids,
      v: { GF: stores.includes("GF") ? f.v : null, PW: stores.includes("PW") ? (f.pw || f.v) : null },
      prev: f.prev || null, slots: f.slots || 1, health: f.health || "instep", updated: f.updated ?? day(Math.floor(rnd() * 120), Math.floor(rnd() * 23)),
    };
  };
  // spread the fixed rows through the list
  const gap = Math.floor(TOTAL / fixed.length);
  let fi = 0;
  while (rows.length < TOTAL) {
    if (fi < fixed.length && rows.length === fi * gap + 7) { rows.push(mk(fixed[fi++])); continue; }
    const isTheme = rnd() < 0.26;
    let name, slug;
    do { // pick again until the slug is new
      const tw = pick(themeWords);
      name = isTheme ? `${pick(first)}${tw ? " " + tw : ""}${pick(editions)}` : `${pick(first)} ${pick(pluginWords)}${pick(editions)}`;
      slug = slugify(name);
    } while (used.has(slug));
    used.add(slug);
    rows.push(mk({ name, type: isTheme ? "Theme" : "Plugin", slug, v: ver(), slots: rnd() < 0.04 ? 2 : 1 }));
  }
  rows.sort((a, b) => a.name.localeCompare(b.name, "en-GB"));

  const filters = (r) => ({
    all: true,
    theme: r.type === "Theme",
    plugin: r.type === "Plugin",
    notinstep: r.health !== "instep" && r.health !== "nearmiss",
    onestore: r.stores.length === 1,
    week: NOW - r.updated < 7 * 86400000,
  });

  // Product detail: Copperline in full; every other row gets the same template from its catalog row
  const copperline = {
    canonical: "copperline",
    storeCards: [
      { code: "GF", productId: 18342, state: "instep", read: min(14) },
      { code: "PW", productId: 7719, state: "instep", read: min(14) },
    ],
    slots: [
      { name: "Download", ids: { GF: 3, PW: 1 }, current: "copperline-5.2.0.zip", previous: "copperline-5.1.4.zip" },
    ],
    fingerprints: [
      { kind: "Folder", value: "copperline/", source: "confirmed by you", at: day(44) },
      { kind: "Header name", value: "Copperline", source: "confirmed by you", at: day(44) },
      { kind: "Author", value: "Northbeam Studio", source: "learned from current file", at: day(61) },
    ],
    history: [
      { at: day(3, 2), what: "Updated", from: "copperline-5.1.4.zip", to: "copperline-5.2.0.zip", where: "GF and PW", who: "you" },
      { at: day(18, 5), what: "Updated", from: "copperline-5.1.2.zip", to: "copperline-5.1.4.zip", where: "GF and PW", who: "you" },
      { at: day(26, 1), what: "Changed outside ShelfSync, accepted", from: "copperline-5.1.1.zip", to: "copperline-5.1.2.zip", where: "PW", who: "outside" },
      { at: day(61), what: "Learned the fingerprint from the current file", where: "Catalog", who: "you" },
    ],
    stale: [{ code: "PW", key: "latest_version_copperline-classic", value: "4.2.0" }],
    snapshots: [
      { at: day(0, 2.2), files: "copperline-5.2.0.zip" },
      { at: day(1, 2.2), files: "copperline-5.2.0.zip" },
      { at: day(4, 2.2), files: "copperline-5.1.4.zip" },
      { at: day(19, 2.2), files: "copperline-5.1.2.zip", missing: true },
    ],
    s3: ["copperline-5.2.0.zip", "copperline-5.1.4.zip"],
  };

  // Cleanup: 7 issues in 4 groups (CAT-03, CAT-07, APL-09, SYNC-02)
  const cleanup = [
    { id: "twins", kind: "Near-miss twins", noun: ["near-miss twin", "near-miss twins"], icon: "link", count: 3,
      reason: "Each pair has the same title on both stores, but the slugs differ, so they weren't linked. ShelfSync never links these on its own.",
      fix: "Link each pair as one product.", bulk: "Link all 3",
      items: [
        { a: { code: "GF", slug: "avenra-child" }, b: { code: "PW", slug: "avenra-child-2" }, title: "Avenra Child", why: "WordPress added a -2 suffix on PluginWay" },
        { a: { code: "GF", slug: "pixelpress-portfolio" }, b: { code: "PW", slug: "pixel-press-portfolio" }, title: "Pixelpress Portfolio", why: "The slugs differ by one character" },
        { a: { code: "GF", slug: "northwind-forms-pro" }, b: { code: "PW", slug: "northwind-form-pro" }, title: "Northwind Forms Pro", why: "The slugs differ by one character" },
      ] },
    { id: "stale", kind: "Stale version keys", noun: ["stale version key", "stale version keys"], icon: "database", count: 2,
      reason: "These products still carry a latest_version key for an old slug. Some themes read it and show the wrong version.",
      fix: "Remove the stale keys. If the store's API can't remove one, it's emptied instead.", bulk: "Remove both keys",
      items: [
        { product: "Copperline", code: "PW", key: "latest_version_copperline-classic", value: "4.2.0" },
        { product: "Rankwise SEO Premium", code: "GF", key: "latest_version_rankwise-seo", value: "20.9.1" },
      ] },
    { id: "outside", kind: "Changed outside ShelfSync", noun: ["changed outside", "changed outside"], icon: "triangle-alert", count: 1,
      reason: "Someone changed this download in WP admin after ShelfSync's last write.",
      fix: "Accept the store's change, or put ShelfSync's file back.", bulk: null,
      items: [
        { product: "Tessera Slider", code: "PW", slot: "Download", from: "tessera-slider-6.1.3.zip", to: "tessera-slider-6.1.3-patched.zip", at: min(122) },
      ] },
    { id: "notours", kind: "File not uploaded by ShelfSync", noun: ["file not uploaded by ShelfSync", "files not uploaded by ShelfSync"], icon: "hard-drive", count: 1,
      reason: "oakfield-restaurant-legacy.zip wasn't uploaded by ShelfSync, so it's never deleted automatically. Delete it in Cleanup if you're sure.",
      fix: "Delete it from S3 if no store needs it. No store's download points at it today.", bulk: null,
      items: [{ file: "oakfield-restaurant-legacy.zip", size: "64.2 MB", modified: day(212) }] },
  ];

  // Activity log: what, where, before and after, who (you, auto-rule, rule, outside ShelfSync)
  const activity = [
    { at: min(3), what: "Updated the download", product: "Harbor Child", where: "GF", from: "harbor-child-1.1.8.zip", to: "harbor-child-1.2.0.zip", who: "you", why: "harbor-child" },
    { at: min(3), what: "Updated the download", product: "Harbor Child", where: "PW", from: "harbor-child-1.1.8.zip", to: "harbor-child-1.2.0.zip", who: "you", why: "harbor-child" },
    { at: min(4), what: "Uploaded", product: "Harbor Child", where: "S3", from: null, to: "harbor-child-1.2.0.zip", who: "you", why: "harbor-child" },
    { at: min(11), what: "Update failed: HTTP 524. Nothing was changed there.", product: "Stackmart", where: "PW", from: "stackmart-6.3.2.zip", to: "stackmart-6.4.0.zip", who: "you", failed: true, why: "stackmart" },
    { at: min(11), what: "Updated the download", product: "Stackmart", where: "GF", from: "stackmart-6.3.2.zip", to: "stackmart-6.4.0.zip", who: "you", why: "stackmart" },
    { at: min(19), what: "Deleted the old file", product: "Cartflux Product Filters", where: "S3", from: "cartflux-product-filters-2.5.9.zip", to: null, who: "rule" },
    { at: min(19), what: "Kept sitekit-backup-pro-4.0.0.zip: GPLFamily's Legacy slot still offers it.", product: "Sitekit Backup Pro", where: "S3", from: null, to: null, who: "rule" },
    { at: min(26), what: "Set latest_version", product: "Cartflux Product Filters", where: "GF", from: "2.6.0", to: "2.6.1", who: "you" },
    { at: min(122), what: "Changed outside ShelfSync", product: "Tessera Slider", where: "PW", from: "tessera-slider-6.1.3.zip", to: "tessera-slider-6.1.3-patched.zip", who: "outside" },
    { at: day(0, 7), what: "Saved a fingerprint (confirmed by you)", product: "Brightcart Checkout Fields", where: "Catalog", from: null, to: "brightcart-checkout-fields/", who: "you" },
    { at: day(1, 3), what: "Dismissed: file doesn't fit the product", product: "Sitekit Backup Pro", where: "Catalog", from: null, to: null, who: "you", undo: true },
    { at: day(1, 5), what: "Set the file manually", product: "Ledgerline Invoices for WooCommerce", where: "GF", from: "ledgerline-invoices-5.9.0.zip", to: "ledgerline-invoices-5.9.3.zip", who: "you" },
    { at: day(3, 2), what: "Updated the download", product: "Copperline", where: "GF", from: "copperline-5.1.4.zip", to: "copperline-5.2.0.zip", who: "you", why: "copperline" },
    { at: day(3, 2), what: "Updated the download", product: "Copperline", where: "PW", from: "copperline-5.1.4.zip", to: "copperline-5.2.0.zip", who: "you", why: "copperline" },
    { at: day(4, 6), what: "Restored to the 21 October snapshot", product: "Quillstack Page Builder Pro (Extended licence, unlimited sites)", where: "PW", from: "quillstack-page-builder-pro-7.14.0-r2.zip", to: "quillstack-page-builder-pro-7.14.0.zip", who: "you" },
    { at: day(12, 4), what: "Rolled back", product: "Oakfield Restaurant", where: "GF", from: "oakfield-3.0.9.zip", to: "oakfield-3.0.8.zip", who: "you" },
    { at: day(23, 1), what: "Linked as twins", product: "Lumen Booking", where: "GF and PW", from: null, to: "lumen-booking", who: "you", undo: true },
  ];

  const settings = {
    stores: [
      { code: "GF", name: "GPLFamily", url: "https://www.gplfamily.example", ck: "ck_••••a91f", cs: "cs_••••07c2", spacing: "0.15", button: "Download", wc: "9.3.2", products: 2394, active: true },
      { code: "PW", name: "PluginWay", url: "https://www.pluginway.example", ck: "ck_••••3be0", cs: "cs_••••d415", spacing: "0.15", button: "Download", wc: "9.1.4", products: 2393, active: true },
    ],
    storage: { endpoint: "s3.amazonaws.com", region: "eu-west-2", bucket: "shelfsync-sample-bucket", rw: "AKIA••••7Q2M", rwSecret: "••••••••k3Zp", ro: "AKIA••••R8XD", roSecret: "••••••••w1Tq", template: '[amazon_s3 object="{key}"]', keep: 1 },
    rules: {
      edition: ["pro", "premium", "plus", "ultimate", "extended", "addon", "add-on", "lite", "free", "core", "child"],
      prefixes: ["YITH", "Jet", "Nexa"],
      bundled: ["plugins/", "bundled/", "inc/plugins/"],
      brakeFails: 3, brakeCount: 30, sync: 15,
      limits: [["Unpacked size per upload", "2 GB"], ["Each nested ZIP", "300 MB"], ["Nesting depth", "3"], ["Entries", "20,000"]],
    },
    updates: { version: "1.1.0", latest: "1.2.0", token: "github_pat_••••3kd9", expires: Date.UTC(2026, 10, 5), checked: min(42), previous: "1.0.3", installed: day(7, 13.6) },
    backup: { last: day(0, 2.2), kept: 7, snapshots: 30, size: "38.4 MB" },
    app: { port: 47615, startWithWindows: true, notifications: true, logDays: 30 },
  };

  const wizard = {
    steps: ["Stores", "Storage", "Test", "Catalog", "Cleanup", "Teach"],
    catalog: { GF: 2394, PW: 2393, linked: 2389, total: 2398 },
  };

  return { NOW, rows, filters, copperline, cleanup, activity, settings, wizard, min, day };
})();
