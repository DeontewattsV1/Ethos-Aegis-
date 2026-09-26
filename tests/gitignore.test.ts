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

describe(".gitignore — Python project hygiene", () => {
  const requiredPatterns = [
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.py[cod]",
    ".pytest_cache/",
    ".ruff_cache/",
    "*.egg-info/",
  ];

  for (const pattern of requiredPatterns) {
    it(`ignores Python-generated artifact "${pattern}"`, () => {
      expect(patterns).toContain(pattern);
    });
  }
});

describe(".gitignore — retained Node.js and local-tool patterns", () => {
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

  it("still ignores .DS_Store (macOS system file)", () => {
    expect(patterns).toContain(".DS_Store");
  });
});
