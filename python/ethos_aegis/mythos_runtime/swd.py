"""Opt-in strict file write verification with path containment and atomic replacement."""
from __future__ import annotations
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .memory import MemoryLedger

@dataclass(frozen=True)
class FileSnapshot:
    path: str
    exists: bool
    size: int | None
    sha256: str | None

@dataclass(frozen=True)
class ClaimedFileAction:
    path: str
    action: str
    description: str = ""

@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    claimed_actions: tuple[ClaimedFileAction, ...]
    verified_actions: tuple[ClaimedFileAction, ...]
    before: dict[str, FileSnapshot]
    after: dict[str, FileSnapshot]
    detail: str
    dry_run: bool = False

class StrictWriteDiscipline:
    """A local helper, not an independent policy authority or race-proof sandbox."""
    def __init__(self, root: str | Path, *, memory_ledger: MemoryLedger | None = None) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("root must be a directory")
        self.memory_ledger = memory_ledger

    def _target(self, path: str | Path) -> tuple[str, Path]:
        raw = str(path).replace("\\", "/")
        if (not raw or len(raw) > 1024 or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw)
                or any(ord(c) < 32 for c in raw)):
            raise ValueError("only bounded relative paths are accepted")
        segments = raw.split("/")
        if any(
            seg in ("", ".", "..") or ":" in seg or seg.endswith((" ", "."))
            or seg.lower() in {".git", ".ethos-aegis"}
            or seg.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL"}
            or re.fullmatch(r"(?:COM|LPT)[1-9](?:\..*)?", seg, flags=re.IGNORECASE)
            for seg in segments
        ):
            raise ValueError("path traversal and ambiguous segments are rejected")
        target = self.root.joinpath(*segments)
        for ancestor in (target, *list(target.parents)):
            if ancestor == self.root:
                break
            if ancestor.is_symlink():
                raise ValueError("symlink traversal is rejected")
        return "/".join(segments), target

    def snapshot(self, paths: list[str]) -> dict[str, FileSnapshot]:
        result = {}
        for path in paths:
            relative, target = self._target(path)
            if target.exists():
                if not target.is_file():
                    raise ValueError("only regular files are supported")
                if target.stat().st_size > 8 * 1024 * 1024:
                    raise ValueError("snapshot exceeds the 8 MiB limit")
                data = target.read_bytes()
                result[relative] = FileSnapshot(relative, True, len(data), hashlib.sha256(data).hexdigest())
            else:
                result[relative] = FileSnapshot(relative, False, None, None)
        return result

    def write_text(self, path: str, content: str, *, description: str = "", dry_run: bool = False) -> VerificationReport:
        relative, target = self._target(path)
        if len(content.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("write exceeds the 8 MiB limit")
        before = self.snapshot([relative])
        old = before[relative]
        action = ClaimedFileAction(relative, "MODIFY" if old.exists else "CREATE", description)
        if dry_run:
            return VerificationReport(False, (action,), (), before, before, "dry-run: write not executed", True)
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._target(relative)  # Reject newly introduced symlink segments.
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".aegis-", suffix=".tmp", dir=parent)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        after = self.snapshot([relative])
        new = after[relative]
        changed = new.exists and (not old.exists or old.sha256 != new.sha256)
        report = VerificationReport(changed, (action,), (action,) if changed else (), before, after,
                                    "verified" if changed else "unchanged content: claim not verified")
        if changed and self.memory_ledger is not None:
            self.memory_ledger.append_verified(path=relative, action=action.action,
                                               before=old.sha256, after=new.sha256)
        return report
