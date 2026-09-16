"""Opaque, short-lived secret leasing for AEGIS Private Shield.

The broker is the only component that stores raw secret material. Agent-facing
objects contain references and lease identifiers, never secret bytes. Secret
material can be consumed only by pre-registered trusted adapters; callers cannot
supply arbitrary credential-handling callbacks at execution time.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Mapping

from .models import ActionRequest, CapabilityGrant, Decision, PolicyDecision, ProjectPolicy, RiskVector
from .runtime import AuthorizationResult, PrivateShield

SecretAdapter = Callable[[bytes, Mapping[str, object]], object]


class SecretLeaseError(RuntimeError):
    """Raised when a secret lease is invalid, expired, revoked, or exhausted."""


class SecretExfiltrationError(RuntimeError):
    """Raised when a trusted adapter attempts to return the raw leased secret."""


@dataclass(frozen=True)
class SecretLease:
    """Opaque authority to use a secret through the trusted broker boundary."""

    lease_id: str
    secret_ref: str
    subject: str
    purpose: str
    expires_at: datetime
    max_uses: int


@dataclass(frozen=True)
class SecretLeaseResult:
    authorization: AuthorizationResult
    lease: SecretLease | None


@dataclass
class _LeaseRecord:
    lease: SecretLease
    material: bytes
    capability_ids: tuple[str, ...]
    risk: float
    remaining_uses: int
    revoked: bool = False


class SecretBroker:
    """In-memory reference broker used to prove the non-possession boundary.

    Production implementations should replace the in-memory secret store with
    Vault/cloud secret-manager/KMS resolution while preserving the same adapter
    registry and purpose-bound lease semantics.
    """

    def __init__(self, shield: PrivateShield) -> None:
        self._shield = shield
        self._secrets: dict[str, bytes] = {}
        self._leases: dict[str, _LeaseRecord] = {}
        self._adapters: dict[str, SecretAdapter] = {}

    def register(self, secret_ref: str, material: bytes | str) -> None:
        """Provision a secret into the trusted broker boundary."""

        if not secret_ref.startswith("secret://"):
            raise ValueError("secret references must start with secret://")
        raw = material.encode() if isinstance(material, str) else bytes(material)
        if not raw:
            raise ValueError("secret material cannot be empty")
        self._secrets[secret_ref] = raw

    def register_adapter(self, purpose: str, adapter: SecretAdapter) -> None:
        """Register trusted credential-consuming code during runtime setup.

        A lease is bound to exactly one purpose. Agent-controlled code can choose
        from capabilities/purposes granted by policy, but cannot inject a new
        callback that receives credential bytes.
        """

        if not purpose:
            raise ValueError("adapter purpose cannot be empty")
        if purpose in self._adapters:
            raise ValueError(f"adapter already registered for purpose: {purpose}")
        self._adapters[purpose] = adapter

    def request_lease(
        self,
        *,
        subject: str,
        secret_ref: str,
        purpose: str,
        identity_verified: bool,
        project_policy: ProjectPolicy,
        agent_grants: Iterable[CapabilityGrant],
        risk: RiskVector | None = None,
        human_approved: bool = False,
        now: datetime | None = None,
        ttl_seconds: int = 60,
        max_uses: int = 1,
    ) -> SecretLeaseResult:
        """Authorize ``secret.use`` and return a purpose-bound opaque lease."""

        now = now or datetime.now(timezone.utc)
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("secret lease TTL must be between 1 and 300 seconds")
        if not 1 <= max_uses <= 10:
            raise ValueError("secret lease max_uses must be between 1 and 10")
        if purpose not in self._adapters:
            raise SecretLeaseError("secret purpose has no registered trusted adapter")

        request = ActionRequest(
            subject=subject,
            action="secret.use",
            resource=secret_ref,
            path="",
            environment="sandbox",
        )
        authorization = self._shield.authorize(
            request,
            identity_verified=identity_verified,
            project_policy=project_policy,
            agent_grants=agent_grants,
            risk=risk,
            human_approved=human_approved,
            input_material=purpose,
            now=now,
        )
        if not authorization.decision.allowed:
            return SecretLeaseResult(authorization=authorization, lease=None)

        material = self._secrets.get(secret_ref)
        if material is None:
            raise KeyError(f"registered secret not found: {secret_ref}")

        lease = SecretLease(
            lease_id=f"lease_{secrets.token_urlsafe(18)}",
            secret_ref=secret_ref,
            subject=subject,
            purpose=purpose,
            expires_at=now + timedelta(seconds=ttl_seconds),
            max_uses=max_uses,
        )
        self._leases[lease.lease_id] = _LeaseRecord(
            lease=lease,
            material=material,
            capability_ids=authorization.decision.capability_ids,
            risk=authorization.decision.risk,
            remaining_uses=max_uses,
        )
        return SecretLeaseResult(authorization=authorization, lease=lease)

    def execute(
        self,
        lease_id: str,
        purpose: str,
        *,
        arguments: Mapping[str, object] | None = None,
        now: datetime | None = None,
    ) -> object:
        """Consume a lease through its pre-registered trusted adapter."""

        now = now or datetime.now(timezone.utc)
        record = self._leases.get(lease_id)
        if record is None:
            raise SecretLeaseError("unknown secret lease")
        if record.lease.purpose != purpose:
            raise SecretLeaseError("secret lease is not valid for requested purpose")
        adapter = self._adapters.get(purpose)
        if adapter is None:
            raise SecretLeaseError("trusted adapter is no longer registered")
        if record.revoked:
            raise SecretLeaseError("secret lease has been revoked")
        if now >= record.lease.expires_at:
            record.revoked = True
            raise SecretLeaseError("secret lease has expired")
        if record.remaining_uses <= 0:
            record.revoked = True
            raise SecretLeaseError("secret lease has been exhausted")

        record.remaining_uses -= 1
        if record.remaining_uses == 0:
            record.revoked = True

        adapter_arguments = dict(arguments or {})
        evidence_input = self._evidence_bytes(
            {
                "lease_id": record.lease.lease_id,
                "purpose": purpose,
                "arguments": adapter_arguments,
            }
        )

        try:
            output = adapter(record.material, adapter_arguments)
        except Exception as exc:
            self._append_consumption_receipt(
                record,
                input_material=evidence_input,
                output_material=repr(exc),
                success=False,
                now=now,
            )
            raise

        encoded_output = self._evidence_bytes(output)
        if record.material in encoded_output:
            self._append_consumption_receipt(
                record,
                input_material=evidence_input,
                output_material=b"blocked-secret-reflection",
                success=False,
                now=now,
            )
            raise SecretExfiltrationError("trusted adapter attempted to return raw secret material")

        self._append_consumption_receipt(
            record,
            input_material=evidence_input,
            output_material=encoded_output,
            success=True,
            now=now,
        )
        return output

    def revoke(self, lease_id: str) -> None:
        record = self._leases.get(lease_id)
        if record is not None:
            record.revoked = True

    def _append_consumption_receipt(
        self,
        record: _LeaseRecord,
        *,
        input_material: bytes | str,
        output_material: bytes | str,
        success: bool,
        now: datetime,
    ) -> None:
        decision = PolicyDecision(
            decision=Decision.ALLOW if success else Decision.DENY,
            reasons=("leased_secret_consumed" if success else "leased_secret_operation_blocked",),
            capability_ids=record.capability_ids,
            risk=record.risk,
        )
        request = ActionRequest(
            subject=record.lease.subject,
            action="secret.use",
            resource=record.lease.secret_ref,
            path="",
            environment="sandbox",
        )
        self._shield.audit.append(
            request,
            decision,
            input_material=input_material,
            output_material=output_material,
            timestamp=now,
        )

    @staticmethod
    def _evidence_bytes(value: object) -> bytes:
        try:
            return json.dumps(value, sort_keys=True, default=repr).encode()
        except (TypeError, ValueError):
            return repr(value).encode()
