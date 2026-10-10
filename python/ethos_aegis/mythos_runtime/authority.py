"""Independent execution grants bound to trusted VeriFlow environments."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit


class AuthorizationDenied(PermissionError):
    """The independent execution grant did not authorize this operation."""


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("production CKAN base URL must be credential-free HTTPS")
    return value.rstrip("/")


@dataclass(frozen=True)
class TrustedEnvironment:
    execution_environment: str
    target_environment: str
    ckan_base_url: str
    source_revision: str

    def __post_init__(self) -> None:
        if not self.execution_environment or not self.target_environment:
            raise ValueError("trusted execution and target environments are required")
        object.__setattr__(self, "ckan_base_url", _validate_base_url(self.ckan_base_url))
        if not re.fullmatch(r"[0-9a-f]{40,64}", self.source_revision):
            raise ValueError("source_revision must be a 40-64 character lowercase hexadecimal revision")

    def to_dict(self) -> dict[str, str]:
        return {
            "execution_environment": self.execution_environment,
            "target_environment": self.target_environment,
            "ckan_base_url": self.ckan_base_url,
            "source_revision": self.source_revision,
        }


@dataclass(frozen=True)
class ExecutionGrant:
    grant_id: str
    subject: str
    purposes: tuple[str, ...]
    actions: tuple[str, ...]
    resources: tuple[str, ...]
    environment: TrustedEnvironment
    issued_at: str
    expires_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "grant_id": self.grant_id,
            "subject": self.subject,
            "purposes": list(self.purposes),
            "actions": list(self.actions),
            "resources": list(self.resources),
            "environment": self.environment.to_dict(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


class ExecutionGrantSigner:
    """Operator-side signer. Keep it outside model/tool-controlled code."""

    def __init__(self, signing_key: bytes, *, max_ttl_seconds: int = 3600) -> None:
        if len(signing_key) < 32:
            raise ValueError("authorization signing key must be at least 32 bytes")
        if not 1 <= max_ttl_seconds <= 24 * 3600:
            raise ValueError("max_ttl_seconds must be between 1 second and 24 hours")
        self._key = bytes(signing_key)
        self.max_ttl_seconds = max_ttl_seconds

    def issue(
        self,
        *,
        subject: str,
        purposes: Iterable[str],
        actions: Iterable[str],
        resources: Iterable[str],
        environment: TrustedEnvironment,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> str:
        if not subject:
            raise ValueError("subject is required")
        if not 1 <= ttl_seconds <= self.max_ttl_seconds:
            raise ValueError("grant TTL exceeds configured limit")
        purpose_set = tuple(sorted(set(purposes)))
        action_set = tuple(sorted(set(actions)))
        resource_set = tuple(sorted(set(resources)))
        if not purpose_set or not action_set or not resource_set:
            raise ValueError("at least one purpose, action and resource are required")
        issued = _utc(now)
        grant = ExecutionGrant(
            grant_id=f"evg_{secrets.token_hex(12)}",
            subject=subject,
            purposes=purpose_set,
            actions=action_set,
            resources=resource_set,
            environment=environment,
            issued_at=_iso(issued),
            expires_at=_iso(issued + timedelta(seconds=ttl_seconds)),
        )
        encoded = _b64encode(_canonical(grant.to_payload()))
        signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"


class ExecutionGrantVerifier:
    """Runtime-side verifier. It verifies authority but cannot mint it."""

    def __init__(self, verification_key: bytes, *, max_ttl_seconds: int = 3600) -> None:
        if len(verification_key) < 32:
            raise ValueError("authorization verification key must be at least 32 bytes")
        if not 1 <= max_ttl_seconds <= 24 * 3600:
            raise ValueError("max_ttl_seconds must be between 1 second and 24 hours")
        self._key = bytes(verification_key)
        self.max_ttl_seconds = max_ttl_seconds

    def verify(
        self,
        token: str | None,
        *,
        action: str,
        resource_id: str,
        purpose: str,
        environment: TrustedEnvironment,
        now: datetime | None = None,
    ) -> ExecutionGrant:
        if not token or token.count(".") != 1:
            raise AuthorizationDenied("a valid execution grant is required")
        encoded, supplied = token.split(".", 1)
        expected = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise AuthorizationDenied("execution grant signature is invalid")
        try:
            payload = json.loads(_b64decode(encoded))
            if payload.get("version") != 1:
                raise ValueError
            grant = ExecutionGrant(
                grant_id=str(payload["grant_id"]),
                subject=str(payload["subject"]),
                purposes=tuple(str(x) for x in payload["purposes"]),
                actions=tuple(str(x) for x in payload["actions"]),
                resources=tuple(str(x) for x in payload["resources"]),
                environment=TrustedEnvironment(**payload["environment"]),
                issued_at=str(payload["issued_at"]),
                expires_at=str(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuthorizationDenied("execution grant payload is invalid") from exc
        now_utc = _utc(now)
        issued, expires = _parse_time(grant.issued_at), _parse_time(grant.expires_at)
        ttl = (expires - issued).total_seconds()
        if ttl <= 0 or ttl > self.max_ttl_seconds:
            raise AuthorizationDenied("execution grant TTL is invalid")
        if now_utc < issued or now_utc >= expires:
            raise AuthorizationDenied("execution grant is not currently active")
        if purpose not in grant.purposes or action not in grant.actions:
            raise AuthorizationDenied("execution grant purpose or action mismatch")
        if resource_id not in grant.resources and "*" not in grant.resources:
            raise AuthorizationDenied("resource is outside execution grant scope")
        if grant.environment != environment:
            raise AuthorizationDenied("trusted execution context does not match the grant")
        return grant
