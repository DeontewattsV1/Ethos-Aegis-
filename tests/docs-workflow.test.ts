import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const WORKFLOW_PATH = join(import.meta.dirname, "../.github/workflows/docs.yml");
const workflowContent = readFileSync(WORKFLOW_PATH, "utf-8");

// Mirror GitHub Actions string functions for semantic testing.
function ghContains(haystack: string, needle: string): boolean {
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

function ghStartsWith(haystack: string, needle: string): boolean {
  return haystack.toLowerCase().startsWith(needle.toLowerCase());
}

const SENTINEL = "docs refresh README snippets";

describe("docs.yml — infinite-loop guard condition", () => {
  it("uses contains() not startsWith() in the job if condition", () => {
    // The PR changed startsWith → contains. Verify the current file has contains.
    expect(workflowContent).toContain("!contains(github.event.head_commit.message");
  });

  it("does not use startsWith() for the infinite-loop guard", () => {
    // Ensure the old startsWith guard was fully replaced.
    const lines = workflowContent.split("\n");
    const ifLine = lines.find((l) => l.includes("!startsWith") && l.includes("head_commit.message"));
    expect(ifLine).toBeUndefined();
  });

  it("contains the correct sentinel string in the if condition", () => {
    expect(workflowContent).toContain(SENTINEL);
  });

  it("the commit-back step uses a message that the contains() guard will match", () => {
    // The bot commit message must contain the sentinel so the next push
    // does not re-trigger the job (infinite-loop prevention).
    const commitMsgMatch = workflowContent.match(/git commit -m "([^"]+)"/);
    expect(commitMsgMatch).not.toBeNull();
    const commitMsg = commitMsgMatch![1]!;
    expect(ghContains(commitMsg, SENTINEL)).toBe(true);
  });

  it("the bot commit message satisfies contains() but NOT startsWith() — demonstrating why contains was chosen", () => {
    // This test documents the regression prevented by using contains instead of startsWith.
    // The bot commit message is: "docs refresh README snippets + output snapshots"
    // It starts with the sentinel, so both would catch it. However, if a human
    // writes "fix: docs refresh README snippets update" in a merge commit,
    // startsWith would miss it while contains would still catch it.
    const humanMergeMsg = "Merge: docs refresh README snippets were regenerated";
    expect(ghContains(humanMergeMsg, SENTINEL)).toBe(true);
    expect(ghStartsWith(humanMergeMsg, SENTINEL)).toBe(false);
  });

  it("contains() correctly allows non-bot commits to pass through", () => {
    const normalCommits = [
      "feat: add new example",
      "fix: correct typo in README",
      "chore: update dependencies",
      "docs: regenerate API docs",
    ];
    for (const msg of normalCommits) {
      expect(ghContains(msg, SENTINEL)).toBe(false);
    }
  });

  it("contains() correctly blocks the bot commit message", () => {
    const botCommitMsg = "docs refresh README snippets + output snapshots";
    expect(ghContains(botCommitMsg, SENTINEL)).toBe(true);
  });

  it("contains() is case-insensitive per GitHub Actions semantics", () => {
    // GitHub Actions contains() is case-insensitive. Our helper mirrors this.
    const upperCaseMsg = "DOCS REFRESH README SNIPPETS + output snapshots";
    expect(ghContains(upperCaseMsg, SENTINEL)).toBe(true);
  });

  it("sentinel embedded mid-message is caught by contains but not startsWith", () => {
    // Key regression test: a commit message where the sentinel appears in
    // the middle (not at the start) should be blocked by contains but would
    // have been missed by the old startsWith guard.
    const embeddedMsg = "automated: docs refresh README snippets via CI";
    expect(ghContains(embeddedMsg, SENTINEL)).toBe(true);
    expect(ghStartsWith(embeddedMsg, SENTINEL)).toBe(false);
  });

  it("the regenerate job has correct permissions declared", () => {
    // docs.yml grants contents:write so the commit-back step can push.
    expect(workflowContent).toContain("contents: write");
  });

  it("the workflow triggers on workflow_dispatch", () => {
    expect(workflowContent).toContain("workflow_dispatch:");
  });

  it("the workflow uses concurrency to cancel in-progress runs", () => {
    expect(workflowContent).toContain("cancel-in-progress: true");
  });

  it("commit-back step only runs on main branch push", () => {
    // The commit-back step must be guarded so it only pushes to main,
    // preventing spurious pushes from feature branches.
    expect(workflowContent).toContain("refs/heads/main");
  });
});