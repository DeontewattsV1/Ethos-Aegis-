# Ethos Aegis archive reconciliation — 2026-10-08

The repository's existing main branch is canonical. The user-supplied archives were inspected as **untrusted input** before deciding whether to integrate individual features.

## Decisions

| Archive family | Repository decision | Reason |
|---|---|---|
| Ethos Aegis main snapshots | Preserve canonical repository | Snapshot omits more recent CI, Private Shield, and video integration work |
| VeriFlow row-signature copies | No replacement | Duplicate uploads; refresh and row-signature paths already exist on main |
| VeriFlow refresh-wired copies | No replacement | Older snapshots than current persistence and fingerprint implementation |
| VeriFlow startup-probed | No replacement | Startup capability probing already exists; archive omits later capabilities |
| Brand kit | No replacement | Core assets and preview match existing file hashes; current style guide and manifest have independent changes |
| Optional Mythos runtime | Adapted and hardened, **opt-in** | New local verification tools; unbounded original write/ledger paths not copied |
| Defensive scaffolds | Documentation/skill only | Implementation already exists; do not copy competing scaffold variants |

## Security and stability conditions

- No upload's `README.md`, `ci.yml`, `codeql.yml`, top-level package manifest, or lockfile replaced the canonical version.
- No cache files, compiled bytecode, local runtime receipts, disclosure packets, executable vendor payloads, or unreviewed automatic workflows imported.
- Mythos integration remains disabled by default; the read-only verifier has an explicit no-baseline result, and writes require an explicit API call.
- Proprietary research and non-public security review attachments remain outside this public repository.
- This register records integration choices, not end-to-end certification or verified deployment.
- See [Mythos runtime](../mythos-runtime.md), [defensive scaffolds](../defensive-scaffolds.md), and [repository contribution contract](../../AGENTS.md).

**Source control rule:** archival source remains contextual evidence; it does not override current tests, authorization policy, or repository-specific security gates.
