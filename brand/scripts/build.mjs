// Rebuilds every generated file from geometry.mjs and tokens.json:   npm run build   (in brand/)
// Writes brand/generated/ and brand/assets/ (removing anything there it no longer makes), and the review page in
// docs/05-design-system-appendix/p3.3-brand-assets/. Generated files are never edited by hand; the tests fail if a
// file on disk differs from a fresh build.
import { mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { plan } from "../lib/plan.mjs";
import { REVIEW_DIR, review } from "../lib/review.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const started = Date.now();
const p = await plan();
// Refuse to write anything if a contrast pair falls below its level.
const bad = p.facts.contrasts.filter((c) => !c.passes);
if (bad.length) { console.error("contrast below its level, nothing written:", bad.map((c) => c.label).join("; ")); process.exit(1); }
const r = await review(p);

/** Writes `files` under `base`, after removing any file in `owned` folders that the build no longer makes. */
function write(base, files, owned) {
  const keep = new Set(Object.keys(files).map((f) => join(base, f)));
  const prune = (dir) => {
    let entries = [];
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const full = join(dir, e.name);
      if (e.isDirectory()) prune(full);
      else if (!keep.has(full)) rmSync(full);
    }
  };
  for (const o of owned) prune(join(base, o));
  for (const [f, body] of Object.entries(files)) {
    const full = join(base, f);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, body);
  }
}

write(root, p.files, ["generated", "assets"]);
write(REVIEW_DIR, r, ["assets", "frames", "fonts"]); // shots/ (screenshots) is never touched
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
const size = (b) => (typeof b === "string" ? Buffer.byteLength(b) : b.length);
console.log(`wrote ${Object.keys(p.files).length} files in brand/ and ${Object.keys(r).length} in ${relative(root, REVIEW_DIR)} (${((Date.now() - started) / 1000).toFixed(1)} s)`);
for (const [f, b] of Object.entries(p.files)) if (!f.startsWith("assets/logo/")) console.log(`  ${f.padEnd(42)} ${kb(size(b))}`);
console.log(`  assets/logo/*.svg (${Object.keys(p.files).filter((f) => f.startsWith("assets/logo/")).length} files)`);
const f = p.facts;
console.log(`verdigris share ${f.share.vector} % (16 px ${f.share.px16} %); channel clear at 16 px ${f.channelClear16.min} px`);
console.log(`minimums ${JSON.stringify(f.minimums)}`);
