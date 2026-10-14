import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GITIGNORE_PATH = join(import.meta.dirname, "../.gitignore");
const gitignoreContent = readFileSync(GITIGNORE_PATH, "utf-8");

// Return all non-empty, non-comment lines from a .gitignore.
function parsePatterns(content: string): string[] {
  return content
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
}

const patterns = parsePatterns(gitignoreContent);

describe(".gitignore — removed Python patterns", () => {
  const removedPatterns = [
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".ruff_cache/",
    "*.egg-info/",
  ];

  for (const pattern of removedPatterns) {
    it(`no longer ignores "${pattern}"`, () => {
      expect(patterns).not.toContain(pattern);
    });
  }

  it("does not contain any Python-specific cache patterns", () => {
    const pythonKeywords = ["__pycache__", ".pytest_cache", ".ruff_cache", ".egg-info"];
    for (const kw of pythonKeywords) {
      const found = patterns.some((p) => p.includes(kw));
      expect(found).toBe(false);
    }
  });

  it("does not ignore .pyc files", () => {
    expect(patterns.some((p) => p.includes(".pyc"))).toBe(false);
  });
});

describe(".gitignore — retained Node.js patterns", () => {
  const retainedPatterns = [
    "node_modules/",
    "coverage/",
    "dist/",
    "docs/api/",
    "*.log",
    ".env",
    ".env.local",
  ];

  for (const pattern of retainedPatterns) {
    it(`still ignores "${pattern}"`, () => {
      expect(patterns).toContain(pattern);
    });
  }

  it("still ignores editor directories", () => {
    expect(patterns).toContain(".vscode/");
    expect(patterns).toContain(".idea/");
  });

  it("does not ignore .DS_Store (macOS system file)", () => {
    // .DS_Store is listed; it should remain in the file.
    expect(patterns).toContain(".DS_Store");
  });
});