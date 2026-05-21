/**
 * run-examples.ts
 *
 * Executes every `.ts` file under `examples/` using tsx, captures stdout/stderr,
 * and writes `<example>.txt` into `docs/output-snapshots/`. Snapshots are
 * deterministic-friendly: each line is trimmed of trailing whitespace and a
 * trailing newline is enforced.
 *
 * Exit codes:
 *   0  — all examples ran cleanly, snapshots written
 *   1  — at least one example exited non-zero (build break)
 *   2  — argument / IO error
 */
import { spawn } from "node:child_process";
import { readdir, mkdir, writeFile, stat } from "node:fs/promises";
import { resolve, dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const EXAMPLES_DIR = join(ROOT, "examples");
const SNAPSHOTS_DIR = join(ROOT, "docs", "output-snapshots");
const TIMEOUT_MS = 30_000;

interface RunResult {
  rel: string;
  exitCode: number;
  output: string;
  durationMs: number;
}

async function walk(dir: string): Promise<string[]> {
  const out: string[] = [];
  const entries = await readdir(dir, { withFileTypes: true });
  for (const e of entries) {
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      out.push(...(await walk(full)));
    } else if (e.isFile() && e.name.endsWith(".ts")) {
      out.push(full);
    }
  }
  return out.sort();
}

function runOne(file: string): Promise<RunResult> {
  return new Promise((resolveFn) => {
    const started = Date.now();
    const rel = relative(EXAMPLES_DIR, file);
    const child = spawn("npx", ["tsx", file], {
      cwd: ROOT,
      env: { ...process.env, NO_COLOR: "1", FORCE_COLOR: "0" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const chunks: Buffer[] = [];
    child.stdout.on("data", (b) => chunks.push(b as Buffer));
    child.stderr.on("data", (b) => chunks.push(b as Buffer));
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
    }, TIMEOUT_MS);
    child.on("close", (code) => {
      clearTimeout(timer);
      const output = Buffer.concat(chunks).toString("utf8");
      resolveFn({
        rel,
        exitCode: code ?? -1,
        output,
        durationMs: Date.now() - started,
      });
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolveFn({
        rel,
        exitCode: -1,
        output: `child error: ${(err as Error).message}\n`,
        durationMs: Date.now() - started,
      });
    });
  });
}

function normalize(out: string): string {
  return (
    out
      .split(/\r?\n/)
      .map((l) => l.replace(/\s+$/, ""))
      .join("\n")
      .replace(/\n+$/g, "") + "\n"
  );
}

async function main(): Promise<void> {
  try {
    await stat(EXAMPLES_DIR);
  } catch {
    console.error(`examples directory missing: ${EXAMPLES_DIR}`);
    process.exit(2);
  }
  await mkdir(SNAPSHOTS_DIR, { recursive: true });

  const files = await walk(EXAMPLES_DIR);
  if (files.length === 0) {
    console.warn("[run-examples] no .ts files under examples/");
    return;
  }

  let failures = 0;
  for (const f of files) {
    const r = await runOne(f);
    const snapshotPath = join(SNAPSHOTS_DIR, `${r.rel}.txt`);
    await mkdir(dirname(snapshotPath), { recursive: true });
    await writeFile(snapshotPath, normalize(r.output), "utf8");
    const status = r.exitCode === 0 ? "OK " : "FAIL";
    console.log(`[run-examples] ${status} ${r.rel} (${r.durationMs}ms)`);
    if (r.exitCode !== 0) failures++;
  }

  if (failures > 0) {
    console.error(`[run-examples] ${failures} example(s) failed`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
