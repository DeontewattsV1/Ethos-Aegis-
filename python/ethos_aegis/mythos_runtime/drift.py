"""Read-only comparison of a repository's files with local verified-write receipts."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from .memory import MemoryLedger
from .swd import StrictWriteDiscipline

@dataclass
class DriftScanResult:
    verified: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

class DriftDetector:
    def __init__(self, root: str | Path, *, ledger: MemoryLedger, swd: StrictWriteDiscipline | None = None) -> None:
        self.ledger = ledger
        self.swd = swd or StrictWriteDiscipline(root)

    def scan(self) -> DriftScanResult:
        expected: dict[str, str] = {}
        for event in self.ledger.list_events():
            data = event.payload
            path, digest = data.get("path"), data.get("after_sha256")
            if isinstance(path, str) and isinstance(digest, str):
                expected[path] = digest
        result = DriftScanResult()
        for path, digest in expected.items():
            try:
                item = self.swd.snapshot([path])[path]
            except (ValueError, OSError):
                result.drifted.append(path)
                continue
            if not item.exists:
                result.missing.append(path)
            elif item.sha256 == digest:
                result.verified.append(path)
            else:
                result.drifted.append(path)
        return result
