/**
 * scripts/upgrade.ts
 *
 * One-shot dependency bump + docs/test/lint sweep.
 *
 * Flow:
 *   1. `npm outdated --json`               → list what's behind
 *   2. `npm update --save`                 → bump within existing semver ranges
 *   3. `npm install`                       → reconcile package-lock.json
 *   4. `npm run docs`                      → regenerate README + snapshots
 *   5. `npm run test`                      → vitest with coverage
 *   6. `npm run lint`                      → tsc --noEmit
 *
 * Flags:
 *   --dry-run    : show outdated list, but do not modify anything
 *   --skip-docs  : skip the docs regeneration pass (faster, less safe)
 *   --skip-tests : skip the test + lint passes (faster, much less safe)
 *
 * Exit codes:
 *   0  : everything bumped clean (or no bumps were available)
 *   1  : a step failed; the previous output should explain
 */

import { spawnSync, type SpawnSyncReturns } from "node:child_process";
import process from "node:process";

type OutdatedRow = {
  current: string;
  wanted: string;
  latest: string;
  dependent?: string;
  location?: string;
};

type OutdatedReport = Record<string, OutdatedRow>;

const args = new Set(process.argv.slice(2));
const isDryRun = args.has("--dry-run");
const skipDocs = args.has("--skip-docs");
const skipTests = args.has("--skip-tests");

function runStep(label: string, cmd: string, cmdArgs: string[]): SpawnSyncReturns<string> {
  console.log(`\n› ${label}`);
  console.log(`  $ ${cmd} ${cmdArgs.join(" ")}`);
  const result = spawnSync(cmd, cmdArgs, { stdio: "inherit", encoding: "utf8" });
  if (result.status !== 0) {
    console.error(`\n✗ Step failed: ${label} (exit ${result.status ?? "?"})`);
    process.exit(1);
  }
  return result;
}

function listOutdated(): OutdatedReport {
  const result = spawnSync("npm", ["outdated", "--json"], { encoding: "utf8" });
  if (!result.stdout || result.stdout.trim() === "") {
    return {};
  }
  try {
    return JSON.parse(result.stdout) as OutdatedReport;
  } catch {
    return {};
  }
}

function summarize(report: OutdatedReport): string[] {
  return Object.entries(report).map(
    ([name, row]) => `  ${name}: ${row.current} → ${row.wanted} (latest: ${row.latest})`,
  );
}

console.log("Living Docs Template — upgrade");
console.log("==============================");

const before = listOutdated();
const beforeLines = summarize(before);

if (beforeLines.length === 0) {
  console.log("No outdated dependencies. Nothing to do.");
  process.exit(0);
}

console.log(`\nOutdated dependencies (${beforeLines.length}):`);
beforeLines.forEach((line) => console.log(line));

if (isDryRun) {
  console.log("\nDry-run mode — no changes made.");
  process.exit(0);
}

runStep("Bumping within semver ranges", "npm", ["update", "--save"]);
runStep("Reconciling package-lock.json", "npm", ["install"]);

if (!skipDocs) {
  runStep("Regenerating docs", "npm", ["run", "docs"]);
}

if (!skipTests) {
  runStep("Running tests", "npm", ["run", "test"]);
  runStep("Running lint", "npm", ["run", "lint"]);
}

const after = listOutdated();
const stillOutdated = summarize(after);

console.log("\n=== Upgrade summary ===");
console.log(`Started outdated: ${beforeLines.length}`);
console.log(`Still outdated  : ${stillOutdated.length} (major bumps require manual review)`);

if (stillOutdated.length > 0) {
  console.log("\nRemaining (out of semver range — review manually):");
  stillOutdated.forEach((line) => console.log(line));
  console.log("\nTo bump one of these explicitly:");
  console.log("  npm install --save <name>@latest");
}

console.log("\nDone.");
