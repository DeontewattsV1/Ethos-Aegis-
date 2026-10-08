# Integration verification

Base: `ed3a1f55cace022f4d49cba7190dcaefa16606f0` (current main at integration).

| Check | Result |
|---|---|
| Full Python core and SDK tests | 372 passed, 4 skipped (optional provider packages) |
| Node SDK tests | 29 passed |
| TypeScript repository tests | 62 passed |
| TypeScript type check and build | Passed; restored the existing REPL cyan helper reference |
| Seven TypeScript examples | Executed successfully; outputs match tracked snapshots |
| Documentation validation | Passed; local links resolve |
| New Python source lint and toolkit type check | Passed |
| High-severity Bandit scan of new toolkit/intake | Passed |
| Python core and SDK wheels | Built; Ghidra Java script included in core wheel |
| Installed-wheel CLI walkthrough | Passed |
| Workflow YAML, Windows-compatible paths, SVG XML | Passed |
| Three MP4/GIF recordings | Rendered, decoded and hashes checked |

The restricted runtime rejects the tsx CLI's IPC socket. Examples were executed
with the same tsx loader via `node --import=tsx`; each output matches the existing
snapshot. `scripts/validate-docs.ts` was run with that loader too. Repository
verification scripts and policy were not weakened.

TypeScript checks used the available cached dependencies. A new network dependency
installation against the lockfile was not performed locally. GitHub CI remains
required on the published revision.

Live TruffleHog/Sherlock/Ghidra smoke tests, an installed Ghidra/JDK compile, device
proxy/radio captures, Go/Rust builds and hosted authentication/isolation validation
were not performed. The local tool recordings exercise actual normalization and
scope logic with synthetic evidence. Go/Rust remain reference SDKs.

Cubic CLI/MCP was unavailable; no Cubic result is claimed. Existing repository CI
and remote reviews must be evaluated before merge. No merge was performed.
