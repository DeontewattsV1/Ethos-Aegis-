# Upgrade mode and the powerful REPL

Two living-docs surfaces designed for exploration and maintenance:

1. **`make upgrade`** — a single command that bumps dependencies within their
   declared semver ranges, regenerates the README and snapshots, and re-runs
   the test + lint passes. Pure additive: it does not alter source files.
2. **`npm run repl`** — an interactive REPL with the `EventEmitter` library
   pre-loaded, plus `.demo`, `.scenario`, `.tap`, `.history`, and `.reset`
   commands for fast exploration.

## `make upgrade`

```bash
make upgrade           # bump within semver + regenerate docs + test + lint
make upgrade-dry       # show what would change without modifying anything
```

What it does, in order:

| Step | Command | Why |
|---|---|---|
| 1 | `npm outdated --json` | Snapshot what's behind. Always runs (even on dry-run). |
| 2 | `npm update --save` | Bump within existing semver ranges. Major bumps require a manual `npm install --save <pkg>@latest`. |
| 3 | `npm install` | Reconcile `package-lock.json` so CI's `npm ci` won't reject it. |
| 4 | `npm run docs` | Full 3-step docs pipeline (sync → run → sync) — verifies new versions don't change example output or break the snapshot contract. |
| 5 | `npm run test` | vitest with coverage. |
| 6 | `npm run lint` | `tsc --noEmit`. |

The script exits non-zero on the first failure, and prints a summary at the
end showing how many deps remained out of range (major bumps that must be
reviewed by hand).

### Why bother with this?

Without `make upgrade`, dependency hygiene is "edit `package.json`, run
`npm install`, hope nothing breaks." With it, every dependency bump is
also a verification that the living-docs contract still holds — examples
still execute, snapshots still match, types still check. A single command
puts all the cross-checks in one place.

## `npm run repl`

Drops you into a Node REPL where `EventEmitter` and `emitter` are already
in scope. The prompt is `ldt>`.

```text
$ npm run repl
living-docs-template REPL
=========================
Pre-loaded: `EventEmitter`, `emitter`
Type `.help` for the full command list.

ldt>
```

### Commands

| Command | Effect |
|---|---|
| `.help` | List all dot-commands (built-in REPL command, also shows the ones below). |
| `.scenarios` | List the named scenarios you can run with `.scenario <name>`. |
| `.scenario <name>` | Run one scenario against a fresh `EventEmitter`. Built-in scenarios: `subscribe`, `once`, `off`, `error`, `all`. |
| `.demo` | Shorthand for `.scenario subscribe` on the *preloaded* emitter (so its effects show up in `.history`). |
| `.tap` | Toggle live logging of every `emit()` call on the preloaded emitter. |
| `.history` | Show the last 20 emits on the preloaded emitter (newest last). |
| `.reset` | Discard the preloaded emitter, create a fresh one, clear history. |

### Example sessions

**Trace what an emit chain does:**

```text
ldt> .tap
tap is now ON
ldt> emitter.on("hello", n => `hi ${n}`)
[Function: unsubscribe]
ldt> emitter.emit("hello", "ada")
[tap] hello ada
1
ldt> .history
  2026-05-21T14:32:07.123Z  hello ada
```

**Explore listener lifetimes without writing test code:**

```text
ldt> .scenario once
Running scenario "once": once('tick') fires for the first emit only.
  once tick=1
ldt> .scenario off
Running scenario "off": on(), then off(), then emit — no listener fires.
  tick=1
  (no second tick logged — unsubscribed)
```

**Run every scenario against fresh emitters in one shot:**

```text
ldt> .scenario all
Running scenario "all": Run every named scenario in order on a fresh emitter each time.
— subscribe: on('hello') + 3 emits — the most basic subscribe loop.
  hello, ada
  hello, grace
  hello, linus
— once: once('tick') fires for the first emit only.
  once tick=1
— off: on(), then off(), then emit — no listener fires.
  tick=1
  (no second tick logged — unsubscribed)
— error: on('error') captures a thrown listener error.
  caught: boom
```

### How it stays in sync with the library

The REPL imports directly from `./src/index.js` via `tsx`, so any change
to `src/emitter.ts` is reflected on the next `npm run repl` with no build
step. The scenarios in `repl.ts` exercise the same surface area as the
files in `examples/basic/` — they are mini-examples kept in the REPL for
ergonomics rather than for documentation, so they intentionally do not
have output snapshots.

## How to extend

| You want to… | Edit |
|---|---|
| Add a new scenario to the REPL | The `scenarios` object in `repl.ts`. Each entry is `{ description, run(em) }`. The `.scenario` command discovers it automatically. |
| Add a step to `make upgrade` | The `runStep(...)` chain at the bottom of `scripts/upgrade.ts`. |
| Skip the test pass in a one-off `make upgrade` | `npx tsx scripts/upgrade.ts --skip-tests` (skips both `npm test` and `npm run lint`). |
| Skip docs regeneration too | `npx tsx scripts/upgrade.ts --skip-docs --skip-tests`. |
