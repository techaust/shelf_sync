// Run in CI before the Playwright output is uploaded (the repository is public): fails if anything in
// playwright-report/ or test-results/ holds a sign-in address with a ticket, a Bearer value (an Authorization
// header), a ticket in a JSON body or the run's install token. The HTML report keeps its data as a base64 zip inside index.html, so that zip is opened and
// every file in it is read too (Node's zlib only; no package). Traces are off (playwright.config.ts), so there is
// no trace archive to open.
//
//   node e2e/check-output.mjs            (from frontend/)
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { inflateRawSync } from "node:zlib";

const FOLDERS = ["playwright-report", "test-results"];
const token = process.env.SHELFSYNC_E2E_TOKEN ?? "";
// A ticket or token is URL-safe base64 of 16 characters or more (a real one is 43). The patterns need a value of
// that shape, so test source shown around a failure (which names the header but holds no value) isn't a finding.
const VALUE = "[A-Za-z0-9_-]{16,}";
const PATTERNS = [
  new RegExp(`#t=${VALUE}`), // a sign-in address
  new RegExp(`%23t%3D${VALUE}`, "i"), // the same, URL-encoded
  new RegExp(`bearer\\s+${VALUE}`, "i"), // a Bearer value: a recorded Authorization header, or anywhere else
  /"ticket"\s*:\s*"[A-Za-z0-9_-]{16,}"/, // a ticket in a recorded JSON body
];

function* files(folder) {
  let names = [];
  try {
    names = readdirSync(folder);
  } catch {
    return; // no output folder: nothing to check
  }
  for (const name of names) {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else yield path;
  }
}

/** The files inside a zip held in a buffer: [name, contents] pairs, read through the central directory. */
function* unzip(zip) {
  const end = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0) throw new Error("not a zip");
  const count = zip.readUInt16LE(end + 10);
  let at = zip.readUInt32LE(end + 16);
  for (let i = 0; i < count; i += 1) {
    const method = zip.readUInt16LE(at + 10);
    const size = zip.readUInt32LE(at + 20);
    const nameLength = zip.readUInt16LE(at + 28);
    const extraLength = zip.readUInt16LE(at + 30);
    const commentLength = zip.readUInt16LE(at + 32);
    const local = zip.readUInt32LE(at + 42);
    const name = zip.subarray(at + 46, at + 46 + nameLength).toString("utf8");
    const dataStart = local + 30 + zip.readUInt16LE(local + 26) + zip.readUInt16LE(local + 28);
    const raw = zip.subarray(dataStart, dataStart + size);
    yield [name, method === 8 ? inflateRawSync(raw) : raw];
    at += 46 + nameLength + extraLength + commentLength;
  }
}

function findings(where, text) {
  const found = PATTERNS.filter((pattern) => pattern.test(text)).map((pattern) => `${where}: matches ${pattern}`);
  if (token && text.includes(token)) found.push(`${where}: holds the install token`);
  return found;
}

const problems = [];
let checked = 0;
for (const folder of FOLDERS) {
  for (const path of files(folder)) {
    const bytes = readFileSync(path);
    const text = bytes.toString("utf8");
    checked += 1;
    problems.push(...findings(path, text));
    const embedded = /<template id="playwrightReportBase64">data:application\/zip;base64,([A-Za-z0-9+/=]+)/.exec(text);
    if (embedded?.[1]) {
      for (const [name, contents] of unzip(Buffer.from(embedded[1], "base64"))) {
        checked += 1;
        problems.push(...findings(`${path} > ${name}`, contents.toString("utf8")));
      }
    }
  }
}

if (problems.length > 0) {
  process.stderr.write(`The Playwright output holds sign-in material, so it isn't uploaded:\n${problems.join("\n")}\n`);
  process.exit(1);
}
process.stdout.write(`Checked ${checked} files in ${FOLDERS.join(" and ")}: no sign-in material.\n`);
