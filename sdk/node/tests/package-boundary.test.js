"use strict";

// Exercise the library from a package-shaped directory outside the source
// checkout. No local Python core is copied into the consumer's npm install.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

test("packaged Node SDK does not assume an adjacent Ethos Aegis checkout", async (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "ethos-node-package-"));
  t.after(() => fs.rmSync(sandbox, {recursive: true, force: true}));

  const packageDir = path.join(
    sandbox, "node_modules", "@deontewattsv1", "ethos-aegis-sdk", "src"
  );
  fs.mkdirSync(packageDir, {recursive: true});
  fs.copyFileSync(require.resolve("../src/index.js"), path.join(packageDir, "index.js"));

  const packaged = require(path.join(packageDir, "index.js"));
  const client = new packaged.AegisClient();
  assert.equal(client._root, null, "installed module must not infer node_modules as a repoRoot");

  // Explicit bad checkout roots fail at construction rather than importing an
  // unrelated module or forwarding an unchecked payload.
  assert.throws(
    () => new packaged.AegisClient({repoRoot: sandbox}),
    (error) => error instanceof packaged.AegisTransportError &&
      /repoRoot must point to a checkout/.test(error.message)
  );

  // HTTP-only construction must remain independent of the embedded core.
  assert.equal(new packaged.AegisClient({transport: "http"})._transport, "http");

  // A separate, clean Python environment makes the package's actual
  // missing-core error deterministic without touching repo files.
  const venv = path.join(sandbox, "python-env");
  execFileSync(process.env.PYTHON || "python3", ["-m", "venv", venv], {
    stdio: "pipe",
    timeout: 30_000,
  });
  const interpreter = process.platform === "win32"
    ? path.join(venv, "Scripts", "python.exe")
    : path.join(venv, "bin", "python");

  const withoutCore = new packaged.AegisClient({pythonBin: interpreter});
  await assert.rejects(
    () => withoutCore.adjudicate("safe test text"),
    (error) => error instanceof packaged.AegisTransportError &&
      /Python core is unavailable/.test(error.message) &&
      /repoRoot/.test(error.message)
  );
});
