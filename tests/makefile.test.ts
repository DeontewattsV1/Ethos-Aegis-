import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const MAKEFILE_PATH = join(import.meta.dirname, "../Makefile");
const makefileContent = readFileSync(MAKEFILE_PATH, "utf-8");

// Parse all target names from the .PHONY declaration.
function parsePhonyTargets(content: string): string[] {
  const match = content.match(/^\.PHONY:\s*(.+)$/m);
  if (!match) return [];
  return match[1]!.trim().split(/\s+/);
}

// Check whether a target definition exists in the Makefile.
function hasTarget(content: string, target: string): boolean {
  // A Makefile target starts at the beginning of a line as "name:"
  return new RegExp(`^${target}:`, "m").test(content);
}

describe("Makefile — removed upgrade targets", () => {
  it("does not define an upgrade target", () => {
    expect(hasTarget(makefileContent, "upgrade")).toBe(false);
  });

  it("does not define an upgrade-dry target", () => {
    expect(hasTarget(makefileContent, "upgrade-dry")).toBe(false);
  });

  it("does not list upgrade in the .PHONY declaration", () => {
    const phonyTargets = parsePhonyTargets(makefileContent);
    expect(phonyTargets).not.toContain("upgrade");
  });

  it("does not list upgrade-dry in the .PHONY declaration", () => {
    const phonyTargets = parsePhonyTargets(makefileContent);
    expect(phonyTargets).not.toContain("upgrade-dry");
  });

  it("does not reference scripts/upgrade.ts", () => {
    expect(makefileContent).not.toContain("scripts/upgrade.ts");
  });

  it("does not advertise upgrade in the help output", () => {
    // The help target previously printed upgrade and upgrade-dry entries.
    expect(makefileContent).not.toContain("make upgrade");
  });
});

describe("Makefile — retained targets", () => {
  const expectedTargets = ["install", "demo", "docs", "verify", "test", "repl", "clean", "help"];

  for (const target of expectedTargets) {
    it(`still defines the ${target} target`, () => {
      expect(hasTarget(makefileContent, target)).toBe(true);
    });
  }

  it("lists all expected targets in the .PHONY declaration", () => {
    const phonyTargets = parsePhonyTargets(makefileContent);
    const expected = ["install", "demo", "docs", "verify", "test", "repl", "clean", "help"];
    for (const t of expected) {
      expect(phonyTargets).toContain(t);
    }
  });

  it("the docs target runs the three-step pipeline (sync then run then sync)", () => {
    // The docs target must run sync-readme.ts twice so the second pass
    // injects fresh output snapshots into the README.
    const syncCount = (makefileContent.match(/sync-readme\.ts/g) ?? []).length;
    expect(syncCount).toBeGreaterThanOrEqual(2);
  });

  it("the test target invokes vitest with --coverage flag", () => {
    expect(makefileContent).toContain("vitest run --coverage");
  });

  it("the repl target description no longer mentions .dot commands", () => {
    // The REPL help text was simplified to "interactive REPL with library preloaded"
    // (removing ".dot commands (.help inside)" wording from the old version).
    expect(makefileContent).not.toContain(".dot commands");
    expect(makefileContent).toContain("repl");
  });
});
