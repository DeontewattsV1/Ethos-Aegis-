import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const workflow = readFileSync(join(import.meta.dirname, "../.github/workflows/readme.yml"), "utf-8");
const linkCheck = workflow.match(/- name: Check README links\n\s+run: \|\n((?: {10}.+\n)+)/)?.[1];

function runLinkCheck(failures: number) {
  const dir = mkdtempSync(join(tmpdir(), "readme-link-check-"));
  try {
    writeFileSync(join(dir, "npx"), `#!/bin/bash
echo "$*" >> "$CALLS"
count=$(wc -l < "$CALLS")
test "$count" -gt "$FAILURES"
`, { mode: 0o755 });
    writeFileSync(join(dir, "sleep"), "#!/bin/bash\nexit 0\n", { mode: 0o755 });
    const calls = join(dir, "calls");
    const result = spawnSync("bash", ["-e", "-c", linkCheck!], {
      env: { ...process.env, PATH: `${dir}:${process.env.PATH}`, CALLS: calls, FAILURES: String(failures) },
      encoding: "utf-8",
    });
    return { status: result.status, calls: readFileSync(calls, "utf-8").trim().split("\n") };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe("README link check", () => {
  it.each([
    [0, 0, 1],
    [1, 0, 2],
    [2, 0, 3],
    [3, 1, 3],
  ])("handles %i failed attempts", (failures, status, attempts) => {
    expect(linkCheck).toBeDefined();
    const result = runLinkCheck(failures);
    expect(result.status).toBe(status);
    expect(result.calls).toEqual(Array(attempts).fill("markdown-link-check -q README.md"));
  });
});
