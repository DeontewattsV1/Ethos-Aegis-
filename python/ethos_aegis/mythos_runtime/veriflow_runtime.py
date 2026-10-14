"""Automatic Mythos assurance bridge for production-configured VeriFlow execution."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .assurance import RetentionPolicy, SecureEvidenceLedger, StateIntegrityError, exclusive_file_lock
from .authority import AuthorizationDenied, ExecutionGrant, ExecutionGrantVerifier, TrustedEnvironment


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class MythosVeriflowRuntime:
    """Automatically enforce authorization and record evidence when attached to VeriFlow."""

    def __init__(
        self,
        *,
        environment: TrustedEnvironment,
        grant_verifier: ExecutionGrantVerifier,
        persistence_key: bytes,
        state_dir: str | Path,
        retention: RetentionPolicy | None = None,
    ) -> None:
        self.environment = environment
        self.grant_verifier = grant_verifier
        self.retention = retention or RetentionPolicy()
        self._persistence_key = bytes(persistence_key)
        if len(self._persistence_key) < 32:
            raise ValueError("persistence key must be at least 32 bytes")
        self.state_dir = Path(state_dir)
        self.ledger = SecureEvidenceLedger(
            self.state_dir / "mythos-veriflow-evidence.json",
            signing_key=self._persistence_key,
            retention=self.retention,
        )

    def _environment_metadata(self) -> dict[str, str]:
        return self.environment.to_dict()

    def authorize(
        self,
        token: str | None,
        *,
        action: str,
        resource_id: str,
        purpose: str,
        now: datetime | None = None,
    ) -> ExecutionGrant:
        try:
            grant = self.grant_verifier.verify(
                token,
                action=action,
                resource_id=resource_id,
                purpose=purpose,
                environment=self.environment,
                now=now,
            )
        except AuthorizationDenied as exc:
            self.ledger.append(
                event_type="authorization",
                action=action,
                resource_id=resource_id,
                subject="unknown",
                decision="DENY",
                metadata={
                    "reason_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                    **self._environment_metadata(),
                },
                now=now,
            )
            raise
        self.ledger.append(
            event_type="authorization",
            action=action,
            resource_id=resource_id,
            subject=grant.subject,
            decision="ALLOW",
            metadata={"grant_id": grant.grant_id, "purpose": purpose, **self._environment_metadata()},
            now=now,
        )
        return grant

    def record(
        self,
        *,
        event_type: str,
        action: str,
        resource_id: str,
        subject: str,
        metadata: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.ledger.append(
            event_type=event_type,
            action=action,
            resource_id=resource_id,
            subject=subject,
            decision="ALLOW",
            metadata={**self._environment_metadata(), **dict(metadata or {})},
            now=now,
        )

    def state_write_lock(self, path: str | Path):
        return exclusive_file_lock(Path(path))

    def protect_state(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        payload_copy = json.loads(json.dumps(payload, sort_keys=True, default=str))
        payload_hash = hashlib.sha256(_canonical(payload_copy)).hexdigest()
        header = {"version": 1, "environment": self.environment.to_dict(), "payload_hash": payload_hash}
        signature = hmac.new(self._persistence_key, _canonical(header), hashlib.sha256).hexdigest()
        return {"mythos_state_envelope": header, "payload": payload_copy, "signature": signature}

    def unprotect_state(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(envelope, Mapping):
            raise StateIntegrityError("state envelope is invalid")
        header, payload, signature = (
            envelope.get("mythos_state_envelope"),
            envelope.get("payload"),
            envelope.get("signature"),
        )
        if not isinstance(header, Mapping) or not isinstance(payload, Mapping) or not isinstance(signature, str):
            raise StateIntegrityError("unsigned legacy state is rejected in production mode")
        if header.get("version") != 1 or header.get("environment") != self.environment.to_dict():
            raise StateIntegrityError("persisted state is bound to another trusted environment")
        actual_hash = hashlib.sha256(_canonical(payload)).hexdigest()
        if not hmac.compare_digest(str(header.get("payload_hash")), actual_hash):
            raise StateIntegrityError("persisted state payload hash is invalid")
        expected = hmac.new(self._persistence_key, _canonical(dict(header)), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise StateIntegrityError("persisted state signature is invalid")
        return dict(payload)
