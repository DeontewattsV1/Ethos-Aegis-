# Mythos Runtime — opt-in local verification

**Status:** reference utilities integrated from the supplied Mythos archive, with security hardening. Not activated in the agent harness or VeriFlow data ingestion. No autonomous execution, publishing, or policy grants.

## Capabilities

- `BudgetMeter`: rejects operations that would exceed delegated turn/token quotas.
- `StrictWriteDiscipline`: optional atomic local text writes with bounded relative paths, symlink rejection, size limits, before/after SHA-256 receipts.
- `MemoryLedger`: explicitly-created, local JSONL receipts with timestamps and SHA-256 metadata, not source contents or credentials.
- `DriftDetector`: read-only checking of files against their latest recorded receipts. No receipt means **unknown**, not verified.
- CLI: `python -m ethos_aegis.mythos_runtime.cli --root . verify --json`. It performs no writes; exit 0 = no drift among tracked files, 1 = drift/missing, 2 = no baseline.

## Local opt-in use

```python
from pathlib import Path
from ethos_aegis.mythos_runtime import MemoryLedger, StrictWriteDiscipline, DriftDetector

root = Path('/absolute/path/to/authorized/workspace')
ledger = MemoryLedger(root / '.ethos-aegis' / 'MEMORY.jsonl')
writer = StrictWriteDiscipline(root, memory_ledger=ledger)
report = writer.write_text('reports/result.txt', 'approved output')
assert report.ok
status = DriftDetector(root, ledger=ledger).scan()
assert 'reports/result.txt' in status.verified
```

Do not feed untrusted target paths, passwords, or agent-generated write grants to this helper. A filesystem check is not a trusted authorization decision. Writes are **explicit** and require a separately authorized caller. The runtime does not defend against adversarial race conditions in the host filesystem, malicious content, transformed-secret exfiltration, or forged local receipts. Use OS containment for stronger guarantees.

Local `.ethos-aegis/` receipts are gitignored and should not be uploaded to public repositories. The prior archive's automatic VeriFlow persistence and destructive `dream` compaction are intentionally deferred pending memory retention, concurrency, and permission review.

## Provenance

Source inspiration: user-supplied `Ethos-Aegis-Agentic-Immune-Veriflow-main(1).zip` (2026-10-08). The attached alternative snapshots and row-signature archives were inspected and not overlaid on the newer canonical repository. This file describes the new opt-in implementation, not an assurance certification.
