"""Local, opt-in JSONL receipt ledger. Not an authorization oracle."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class MemoryEvent:
    event_type: str
    summary: str
    payload: dict[str, Any]
    created_at: str

class MemoryLedger:
    """Stores file path/hash receipts only; never the file contents.

    The ledger is a local evidence index, not cryptographic authentication.
    The caller controls when a write is allowed to occur.
    """
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append_verified(self, *, path: str, action: str, before: str | None, after: str | None) -> None:
        event = {
            "event_type": "verified_write",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "action": action,
            "before_sha256": before,
            "after_sha256": after,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("ledger symlinks are not supported")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as output:
                output.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

    def list_events(self) -> list[MemoryEvent]:
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise ValueError("ledger symlinks are not supported")
        events = []
        with self.path.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                if index >= 100_000 or len(line) > 32_768:
                    raise ValueError("ledger exceeds bounded read limits")
                record = json.loads(line)
                if not isinstance(record, dict) or record.get("event_type") != "verified_write":
                    raise ValueError("unknown ledger event schema")
                events.append(MemoryEvent("verified_write", "Verified local write", record, record["created_at"]))
        return events
