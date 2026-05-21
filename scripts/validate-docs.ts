/**
 * validate-docs.ts
 *
 * Verifies that:
 *   1. Every `<!-- example:path -->` marker in README.md resolves to a real
 *      file under examples/.
 *   2. Every `examples/**\/*.ts` has a matching snapshot in
 *      `docs/output-snapshots/`.
 *   3. The README fenced block immediately after each `<!-- example:... -->`
 *      marker matches the file byte-for-byte (after trim).
 *   4. (Optional) Each snapshot is younger than STALE_DAYS days; older
 *      snapshots emit a warning but do not fail.
 *
 * Exit code 0 if all hard checks pass; 1 otherwise.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { resolve, dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const README = join(ROOT, "README.md");
const EXAMPLES_DIR = join(ROOT, "examples");
const SNAPSHOTS_DIR = join(ROOT, "docs", "output-snapshots");
const STALE_DAYS = 7;

const EXAMPLE_RE = /<!--\s*example:([^\s>]+)\s*-->\s*\n```[a-zA-Z0-9]*\n([\s\S]*?)\n```/g;

async function walk(dir: string): Promise<string[]> {
  const out: string[] = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const full = join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(full)));
    else if (e.isFile() && e.name.endsWith(".ts")) out.push(full);
  }
  return out.sort();
}

async function main(): Promise<void> {
  const errors: string[] = [];
  const warnings: string[] = [];

  const readme = await readFile(README, "utf8");

  // Check 1+3 — every marker resolves and content matches the source file.
  const markers = [...readme.matchAll(EXAMPLE_RE)];
  for (const m of markers) {
    const relPath = m[1]!;
    const block = m[2]!;
    const file = join(EXAMPLES_DIR, relPath);
    try {
      const src = (await readFile(file, "utf8")).trimEnd();
      if (block.trim() !== src.trim()) {
        errors.push(
          `README code block for examples/${relPath} is out of sync with source file. Run 'npm run docs'.`,
        );
      }
    } catch {
      errors.push(`README references missing example file: examples/${relPath}`);
    }
  }

  // Check 2 — every example .ts has a snapshot.
  const files = await walk(EXAMPLES_DIR);
  for (const f of files) {
    const rel = relative(EXAMPLES_DIR, f);
    const snap = join(SNAPSHOTS_DIR, `${rel}.txt`);
    try {
      const s = await stat(snap);
      const ageDays = (Date.now() - s.mtimeMs) / 86_400_000;
      if (ageDays > STALE_DAYS) {
        warnings.push(`snapshot stale (${ageDays.toFixed(1)}d): ${rel}.txt`);
      }
    } catch {
      errors.push(`missing snapshot for example: ${rel} (expected docs/output-snapshots/${rel}.txt)`);
    }
  }

  for (const w of warnings) console.warn(`WARN: ${w}`);
  for (const e of errors) console.error(`ERROR: ${e}`);

  if (errors.length > 0) {
    console.error(`[validate-docs] ${errors.length} error(s)`);
    process.exit(1);
  }
  console.log(
    `[validate-docs] OK — ${markers.length} marker(s), ${files.length} example(s), ${warnings.length} warning(s)`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
