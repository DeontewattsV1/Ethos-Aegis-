"""
task_verifier_mesh.py - DeterministicVerifier shim for veriflow compatibility.

Provides the DeterministicVerifier that veriflow.immune_system expects,
wrapping a lightweight SHA-256 based verification pipeline.
All checks are local-only; no network calls.
"""
from __future__ import annotations

import hashlib
import json as _json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationResult:
    """Minimal result returned by DeterministicVerifier."""
    passed: bool = True
    issue_type: str = ""
    integrity_hash: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return self.passed


class DeterministicVerifier:
    """
    Mesh-level deterministic verifier for source snapshots.

    Applies a chain of lightweight, stateless checks to a serialised payload:
    1. Non-empty payload guard
    2. UTF-8 decodability
    3. JSON structural integrity (if payload looks like JSON)
    4. SHA-256 integrity hash computation

    Args:
        strict: If True, JSON parse errors cause a failure result.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self._strict = strict

    def verify_source_snapshot(self, payload: str) -> VerificationResult:
        """Verify payload and return a VerificationResult.

        Args:
            payload: Serialised data snapshot (e.g. json.dumps(rows)).

        Returns:
            VerificationResult with passed=True if all checks succeed.
        """
        if not payload:
            return VerificationResult(
                passed=False,
                issue_type="empty_payload",
                details={"reason": "Payload must be a non-empty string."},
            )

        try:
            raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        except (UnicodeEncodeError, AttributeError) as exc:
            return VerificationResult(
                passed=False,
                issue_type="encoding_error",
                details={"error": str(exc)},
            )

        if payload.lstrip().startswith(("[", "{")):
            try:
                _json.loads(payload)
            except _json.JSONDecodeError as exc:
                if self._strict:
                    return VerificationResult(
                        passed=False,
                        issue_type="json_parse_error",
                        details={"error": str(exc)},
                    )

        integrity_hash = hashlib.sha256(raw).hexdigest()
        return VerificationResult(
            passed=True,
            issue_type="",
            integrity_hash=integrity_hash,
            details={"bytes": len(raw), "hash_algo": "sha256"},
        )

    def verify_batch(self, payloads: list[str]) -> list[VerificationResult]:
        """Verify a list of payloads, returning one result per entry."""
        return [self.verify_source_snapshot(p) for p in payloads]
