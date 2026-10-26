// Lists every Claude Code run in ShelfSync since a date, with the model and effort its own log recorded,
// and flags anything outside docs/12-models-and-usage.md: a model other than Opus, Sonnet or Haiku 5.5,
// effort xhigh/max, or the lead on an effort other than medium or high (high is listed, so the owner can
// check it was a key step). It also lists the skills each run loaded and flags a builder, designer, analyst
// or reviewer run that loaded none (skills are mandatory: docs/09-tooling.md section 3).
// Adapted from techaust_platform/tools/model-audit.mjs.
// Usage: node tools/model-audit.mjs [YYYY-MM-DD]   (default: today). Exit code 1 if anything is flagged.
// Dates are Windows local dates and times are shown in local time with the zone name (CLAUDE.md, Time).
// Reads only the local logs in ~/.claude/projects/<this repo>/; prints no message content.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const MODELS = new Set(["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]);
const EFFORTS = new Set(["low", "medium", "high"]);

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = join(homedir(), ".claude", "projects", repo.replace(/[^A-Za-z0-9]/g, "-"));
// The logs store UTC; compare and print in local time, so a run just after local midnight counts for that day.
const localDay = (ts) => new Date(ts).toLocaleDateString("en-CA");
const localTime = (ts) => {
  const d = new Date(ts);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const zone = new Intl.DateTimeFormat("en-IN", { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName");
  return `${localDay(ts)} ${time} ${zone?.value ?? ""}`.trim();
};
const since = process.argv[2] ?? localDay(Date.now());
if (!/^\d{4}-\d{2}-\d{2}$/.test(since)) {
  console.error("Usage: node tools/model-audit.mjs [YYYY-MM-DD]");
  process.exit(2);
}
if (!existsSync(root)) {
  console.log(`No logs found in ${root}`);
  process.exit(0);
}

const files = [];
const walk = (dir) => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (entry.name.endsWith(".jsonl")) files.push(path);
  }
};
walk(root);

const runs = [];
for (const file of files) {
  const isAgent = basename(dirname(file)) === "subagents";
  let agent = "lead";
  if (isAgent) {
    try {
      agent = JSON.parse(readFileSync(file.replace(/\.jsonl$/, ".meta.json"), "utf8")).agentType ?? "agent";
    } catch {
      agent = "agent";
    }
  }
  const models = new Set();
  const efforts = new Set();
  const skills = new Set();
  let first = "";
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (!line.includes('"type":"assistant"')) continue;
    let entry;
    try {
      entry = JSON.parse(line);
    } catch {
      continue;
    }
    if (entry.type !== "assistant" || !entry.timestamp || localDay(entry.timestamp) < since) continue;
    const model = entry.message?.model;
    if (!model || model === "<synthetic>") continue;
    models.add(model);
    if (entry.effort) efforts.add(entry.effort);
    for (const part of Array.isArray(entry.message?.content) ? entry.message.content : [])
      if (part?.type === "tool_use" && part.name === "Skill" && part.input?.skill)
        skills.add(part.input.skill);
    if (!first) first = entry.timestamp;
  }
  if (!models.size) continue;
  const problems = [];
  for (const m of models) if (!MODELS.has(m)) problems.push(`model ${m} not allowed`);
  for (const e of efforts) if (!EFFORTS.has(e)) problems.push(`effort ${e} not allowed`);
  if (!isAgent && [...efforts].some((e) => e !== "medium" && e !== "high")) problems.push("lead not on medium or high");
  if (!isAgent && [...models].some((m) => m !== "claude-opus-5-5")) problems.push("lead not on Opus 5.5");
  let note = !isAgent && efforts.has("high") ? "  NOTE: lead ran at high (key step?)" : "";
  if (["Explore", "Plan", "general-purpose", "claude"].includes(agent))
    note += "  NOTE: built-in agent (allowed only as a code-review/security-review helper; check it only read)";
  if (["builder", "designer", "analyst", "reviewer"].includes(agent) && !skills.size)
    problems.push("no skill loaded");
  const id = basename(file, ".jsonl");
  runs.push({ first, agent, id, models: [...models], efforts: [...efforts], skills: [...skills], problems, note });
}

runs.sort((a, b) => a.first.localeCompare(b.first));
console.log(`Runs since ${since}: ${runs.length}`);
for (const r of runs) {
  const used = `${r.models.join(",")} / ${r.efforts.join(",") || "?"}`;
  const flag = r.problems.length ? `  FLAG: ${r.problems.join("; ")}` : "";
  const sk = r.skills.length ? `  skills: ${r.skills.join(", ")}` : "  skills: none";
  console.log(`${localTime(r.first)}  ${r.agent.padEnd(12)} ${used}${sk}  (${r.id})${flag}${r.note}`);
}
const flagged = runs.filter((r) => r.problems.length).length;
console.log(flagged ? `${flagged} run(s) flagged.` : "All runs within the plan.");
process.exit(flagged ? 1 : 0);
