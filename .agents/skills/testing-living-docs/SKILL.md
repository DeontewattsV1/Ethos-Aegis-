---
name: testing-living-docs
description: How to verify the living-docs contract end-to-end — sync-readme/run-examples/validate-docs idempotency, drift detection, and vitest. Use when testing changes to scripts/ or the EventEmitter, or when verifying that the README is in sync with examples/.
---

# Testing the living-docs harness

This repo enforces a one-way contract: `examples/*.ts -> sync-readme.ts -> README.md code blocks` and `examples/*.ts -> run-examples.ts -> docs/output-snapshots/<dir>/<basename>.ts.txt`. A stale README is a CI failure, not a doc-debt item.

## Commands

- `npm ci` — fresh install
- `make verify` — runs `run-examples.ts` then `validate-docs.ts` (does NOT mutate README); expects `7 example(s), 0 warning(s)`
- `make docs` — full 3-step pipeline: `sync-readme.ts && run-examples.ts && sync-readme.ts`. The third pass injects fresh output snapshots into README's `<!-- output:... -->` blocks. The two-step version (without the trailing sync) cannot clear drift and was fixed in PR #3.
- `npm test` — vitest with v8 coverage; the suite locks in `off()`-after-`once()` semantics (Symbol-tagged wrapper) and `emit()` counting throwing listeners
- `npx tsc --noEmit` — type-check only, no build emit

## How to verify the contract

1. **Fresh clone + `make verify`**: clone, `npm ci`, then `make verify`. Expect exit 0, `7 example(s)`, and `docs/output-snapshots/{basic,advanced,interactive}/*.ts.txt` populated.
2. **New example auto-surfaces**: drop a new `examples/<dir>/<name>.ts` plus a `<!-- example:<dir>/<name>.ts -->` and `<!-- output:<dir>/<name>.ts -->` marker pair anywhere in README. Run `make docs`. The fenced block under the example marker should fill with the file's source, the output block should contain whatever the example prints, and `docs/output-snapshots/<dir>/<name>.ts.txt` should exist.
3. **Idempotency**: `npx tsx scripts/sync-readme.ts` twice on a clean tree; `git diff --quiet -- README.md` after the second pass must return 0. This is what keeps `docs.yml` from committing back forever.
4. **Drift detection**: mutate any `examples/*.ts` and run `npx tsx scripts/validate-docs.ts` WITHOUT syncing first. Must exit 1 with `README code block for examples/<path> is out of sync with source file. Run 'npm run docs'.`. Revert with `git checkout -- <file>` afterward.

## Snapshot filename convention

`docs/output-snapshots/<dir>/<basename>.ts.txt` — note the literal `.ts.txt` (the source filename including extension, then `.txt` appended). Not `<basename>.txt`.

## CI workflows

- `docs.yml` — on push to non-main or `workflow_dispatch`, runs the 2nd sync-readme pass; on push to main, commits results back with a message starting `docs: refresh README snippets` (self-trigger guard depends on that prefix).
- `examples.yml` — runs every file in `examples/` as a Node process; non-zero exit fails CI.
- `readme.yml` — markdown-link-check + marker existence check; warns (does not fail) on snapshots older than 7 days.

## Node version

Use Node 20.x (devcontainer + CI use this). Local sessions may run 22.x without issues but pin to 20 for parity.

## When you change the EventEmitter

- The `off()` Symbol-tag pattern (a module-private `Symbol("ldt.originalListener")` attached to the `once()` wrapper) is what makes `bus.off(event, originalListener)` work for `once()`-registered listeners. Don't break this — it's covered by `tests/emitter.test.ts:101`.
- `emit()` increments `notified` before invoking the listener, so listeners that throw are still counted (locked in by `tests/emitter.test.ts:112`).
- Set-based dedup is intentional: subscribing the same function reference twice is a no-op.
