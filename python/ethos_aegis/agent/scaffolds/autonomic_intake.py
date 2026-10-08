"""Archive-derived change intake, adapted to the current review scaffolds.

Polls a bounded local tree and emits observations. Never rewrites source files,
promotes a finding to verified, or applies a patch on a model's judgment.
"""

from __future__ import annotations

import ast
import hashlib
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .types import ConfidenceLevel, FindingCandidate, SeverityLevel


@dataclass(frozen=True)
class MutationActivation:
    relative_path: str
    sha256_before: str | None
    sha256_after: str
    findings: tuple[FindingCandidate, ...]


class AutonomicSentinel:
    def __init__(
        self,
        target_directory: str | Path,
        *,
        sleep_interval: float = 1.0,
        max_file_bytes: int = 1_000_000,
        max_files: int = 1000,
    ) -> None:
        self.target = Path(target_directory).resolve(strict=True)
        if not self.target.is_dir() or sleep_interval <= 0 or max_file_bytes <= 0 or max_files <= 0:
            raise ValueError("Invalid watcher configuration.")
        self.sleep_interval = sleep_interval
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self._hashes: dict[str, str] = {}

    def poll_once(self) -> list[MutationActivation]:
        activations = []
        visited = 0
        candidates = []
        inspected = 0
        for directory, dirs, files in os.walk(self.target, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".") and name != "__pycache__" and not (Path(directory) / name).is_symlink()
            ]
            inspected += len(dirs) + len(files)
            if inspected > self.max_files:
                raise ValueError("Watcher file budget exceeded.")
            candidates.extend(Path(directory) / name for name in files if name.endswith(".py"))
        for path in sorted(candidates):
            if path.is_symlink() or any(
                part.startswith(".") or part == "__pycache__" for part in path.relative_to(self.target).parts
            ):
                continue
            canonical = path.resolve(strict=True)
            if self.target not in canonical.parents or not canonical.is_file():
                continue
            visited += 1
            if visited > self.max_files:
                raise ValueError("Watcher file budget exceeded.")
            with canonical.open("rb") as handle:
                raw = handle.read(self.max_file_bytes + 1)
            if len(raw) > self.max_file_bytes:
                continue
            relative = str(path.relative_to(self.target))
            digest = hashlib.sha256(raw).hexdigest()
            previous = self._hashes.get(relative)
            if previous == digest:
                continue
            findings = self._inspect(raw, digest)
            self._hashes[relative] = digest
            activations.append(MutationActivation(relative, previous, digest, tuple(findings)))
        return activations

    @staticmethod
    def _inspect(raw: bytes, digest: str) -> list[FindingCandidate]:
        try:
            tree = ast.parse(raw)
        except (SyntaxError, UnicodeError):
            return [
                FindingCandidate(
                    digest,
                    "Source parsing failed",
                    "Review changed Python source.",
                    SeverityLevel.MODERATE,
                    ConfidenceLevel.HYPOTHESIS,
                )
            ]
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                identity = hashlib.sha256(f"{digest}:{node.lineno}:{node.func.id}".encode()).hexdigest()
                findings.append(
                    FindingCandidate(
                        identity,
                        "Dynamic execution call",
                        "Changed source contains a direct dynamic execution call.",
                        SeverityLevel.HIGH,
                        ConfidenceLevel.HYPOTHESIS,
                        evidence=[f"source_sha256={digest}", f"line={node.lineno}"],
                        remediation_notes=["Verify reachability and intended behavior before proposing a patch."],
                    )
                )
        return findings

    def run_forever(self, on_activation: Callable[[MutationActivation], None], stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            for activation in self.poll_once():
                if stop_event.is_set():
                    return
                on_activation(activation)
            stop_event.wait(self.sleep_interval)
