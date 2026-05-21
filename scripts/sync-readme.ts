/**
 * sync-readme.ts
 *
 * Walks README.md looking for region markers:
 *
 *   <!-- example:basic/01-subscribe.ts -->
 *   ```ts
 *   ...stale content...
 *   ```
 *
 * Replaces the fenced block body with the live contents of
 * `examples/<path>`. Idempotent — running twice in a row produces no diff.
 *
 * Also handles output-snapshot markers:
 *
 *   <!-- output:basic/01-subscribe.ts -->
 *   ```
 *   ...captured stdout...
 *   ```
 *
 * And the `<!-- last-verified: ISO -->` stamp.
 */
import { readFile, writeFile, access } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const README = join(ROOT, "README.md");
const EXAMPLES_DIR = join(ROOT, "examples");
const SNAPSHOTS_DIR = join(ROOT, "docs", "output-snapshots");

const EXAMPLE_RE = /(<!--\s*example:([^\s>]+)\s*-->\s*\n)```[a-zA-Z0-9]*\n([\s\S]*?)\n```/g;
const OUTPUT_RE = /(<!--\s*output:([^\s>]+)\s*-->\s*\n)```[a-zA-Z0-9]*\n([\s\S]*?)\n```/g;
const LAST_VERIFIED_RE = /<!--\s*last-verified:[^>]*-->/g;

async function exists(p: string): Promise<boolean> {
  try {
    await access(p, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function main(): Promise<void> {
  if (!(await exists(README))) {
    console.error(`README not found at ${README}`);
    process.exit(1);
  }

  const original = await readFile(README, "utf8");
  let updated = original;
  let exampleReplacements = 0;
  let outputReplacements = 0;
  const errors: string[] = [];

  updated = await replaceAsync(updated, EXAMPLE_RE, async (_match, header, path, _body) => {
    const file = join(EXAMPLES_DIR, path);
    if (!(await exists(file))) {
      errors.push(`example marker references missing file: examples/${path}`);
      return _match;
    }
    const snippet = (await readFile(file, "utf8")).trimEnd();
    exampleReplacements++;
    return `${header}\`\`\`ts\n${snippet}\n\`\`\``;
  });

  updated = await replaceAsync(updated, OUTPUT_RE, async (match, header, path, _body) => {
    const file = join(SNAPSHOTS_DIR, `${path}.txt`);
    if (!(await exists(file))) {
      // Snapshot may not exist yet on first sync; leave block untouched.
      return match;
    }
    const snippet = (await readFile(file, "utf8")).replace(/\s+$/, "");
    outputReplacements++;
    return `${header}\`\`\`\n${snippet}\n\`\`\``;
  });

  // Last-verified stamp.
  //   - During local `make docs` runs we only refresh the stamp when content actually
  //     changed, so re-running locally is idempotent and doesn't churn git.
  //   - In CI (or when LDT_FORCE_STAMP=1) we always refresh, so the README reflects
  //     the most recent successful verification.
  const contentChanged = updated !== original;
  const forceStamp = process.env.LDT_FORCE_STAMP === "1";
  if ((contentChanged || forceStamp) && LAST_VERIFIED_RE.test(updated)) {
    const stamp = new Date().toISOString();
    updated = updated.replace(LAST_VERIFIED_RE, `<!-- last-verified: ${stamp} -->`);
  }

  if (errors.length > 0) {
    for (const e of errors) console.error(`ERROR: ${e}`);
    process.exit(2);
  }

  const changed = updated !== original;
  if (changed) {
    await writeFile(README, updated, "utf8");
  }

  console.log(
    `[sync-readme] example blocks: ${exampleReplacements}, output blocks: ${outputReplacements}, changed: ${changed}`,
  );
}

async function replaceAsync(
  input: string,
  re: RegExp,
  replacer: (match: string, ...groups: string[]) => Promise<string>,
): Promise<string> {
  const matches: { match: string; groups: string[]; index: number }[] = [];
  for (const m of input.matchAll(re)) {
    matches.push({ match: m[0], groups: m.slice(1) as string[], index: m.index ?? 0 });
  }
  if (matches.length === 0) return input;

  let result = "";
  let cursor = 0;
  for (const { match, groups, index } of matches) {
    result += input.slice(cursor, index);
    result += await replacer(match, ...groups);
    cursor = index + match.length;
  }
  result += input.slice(cursor);
  return result;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
