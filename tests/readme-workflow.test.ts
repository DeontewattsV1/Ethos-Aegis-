import { describe, expect, it } from "vitest";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const workflow = readFileSync(join(import.meta.dirname, "../.github/workflows/readme.yml"), "utf-8");
const linkCheck = workflow.match(/- name: Check README links\n        run: \|\n((?:          .*\n)+)/)?.[1];

function runLinkCheck(succeedOn: number) {
  expect(linkCheck).toBeDefined();
  const script = `
    count=0
    npx() {
      [ "$*" = "markdown-link-check -q README.md" ] || exit 2
      count=$((count + 1))
      echo "check $count"
      [ "$count" -eq "$SUCCESS_ON" ]
    }
    sleep() { echo "sleep $1"; }
    ${linkCheck}
  `;
  return spawnSync("bash", ["-e", "-c", script], {
    encoding: "utf-8",
    env: { ...process.env, SUCCESS_ON: String(succeedOn) },
  });
}

describe("README link check retries", () => {
  it("stops immediately on success", () => {
    const result = runLinkCheck(1);
    expect(result.status).toBe(0);
    expect(result.stdout).toBe("check 1\n");
  });

  it("retries a transient failure", () => {
    const result = runLinkCheck(2);
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("sleep 15\ncheck 2\n");
    expect(result.stdout).not.toContain("check 3");
  });

  it("fails after three unsuccessful checks", () => {
    const result = runLinkCheck(0);
    expect(result.status).toBe(1);
    expect(result.stdout.match(/check \d/g)).toEqual(["check 1", "check 2", "check 3"]);
    expect(result.stdout.match(/sleep 15/g)).toHaveLength(2);
  });
});
