"""Secret broker regression tests for typed output and error redaction."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ethos_aegis.private_shield import (
    CapabilityGrant, Decision, PrivateShield, ProjectPolicy, SecretBroker,
    SecretExfiltrationError, SecretLeaseError,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
SIGNING_KEY = b"0123456789abcdef0123456789abcdef"


def _lease_for(secret: str, adapter):
    shield = PrivateShield(signing_key=SIGNING_KEY)
    broker = SecretBroker(shield)
    ref = "secret://isolated-test"
    purpose = "test.consume"
    broker.register(ref, secret)
    broker.register_adapter(purpose, adapter)
    project = ProjectPolicy(resource=ref, actions=frozenset({"secret.use"}))
    grant = CapabilityGrant(
        capability_id="test-lease",
        subject="agent://test",
        resource=ref,
        actions=frozenset({"secret.use"}),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    lease = broker.request_lease(
        subject="agent://test",
        secret_ref=ref,
        purpose=purpose,
        identity_verified=True,
        project_policy=project,
        agent_grants=[grant],
        now=NOW,
    ).lease
    assert lease is not None
    return shield, broker, lease.lease_id, purpose


@pytest.mark.parametrize(
    ("secret", "adapter"),
    [
        ("pässwörd-token", lambda raw, args: {"value": raw.decode("utf-8")}),
        ("unicode-key", lambda raw, args: {raw.decode("utf-8"): True}),
        ("binary-token", lambda raw, args: {"nested": [raw]}),
        ("bytearray-token", lambda raw, args: {"nested": bytearray(raw)}),
        ("deep-string", lambda raw, args: {"nested": [{"payload": raw.decode("utf-8")}]}),
    ],
)
def test_raw_reflection_rejected_before_serialization(secret, adapter) -> None:
    shield, broker, lease, purpose = _lease_for(secret, adapter)
    with pytest.raises(SecretExfiltrationError):
        broker.execute(lease, purpose, now=NOW + timedelta(seconds=1))
    assert shield.audit.verify()
    assert shield.audit.receipts[-1].decision == Decision.DENY.value


def test_cyclic_output_is_rejected_and_audited() -> None:
    cycle = []
    cycle.append(cycle)
    shield, broker, lease, purpose = _lease_for("private-value", lambda raw, args: cycle)
    with pytest.raises(SecretLeaseError, match="cyclic"):
        broker.execute(lease, purpose, now=NOW + timedelta(seconds=1))
    assert shield.audit.verify()
    assert shield.audit.receipts[-1].decision == Decision.DENY.value


def test_unsupported_output_type_is_rejected() -> None:
    shield, broker, lease, purpose = _lease_for("private-value", lambda raw, args: object())
    with pytest.raises(SecretLeaseError, match="unsupported"):
        broker.execute(lease, purpose, now=NOW + timedelta(seconds=1))
    assert shield.audit.verify()


def test_adapter_exception_cannot_reflect_secret_through_error_or_receipt() -> None:
    secret = "never-expose-me"

    def fail(raw, args):
        raise ValueError(f"adapter leaked {raw.decode('utf-8')}")

    shield, broker, lease, purpose = _lease_for(secret, fail)
    with pytest.raises(SecretLeaseError, match="trusted adapter execution failed") as error:
        broker.execute(lease, purpose, now=NOW + timedelta(seconds=1))
    assert secret not in str(error.value)
    assert shield.audit.verify()
    assert secret not in repr(shield.audit.receipts)


def test_nonsecret_plain_output_still_succeeds() -> None:
    shield, broker, lease, purpose = _lease_for("private-value", lambda raw, args: {"ok": True, "count": 2})
    assert broker.execute(lease, purpose, now=NOW + timedelta(seconds=1)) == {"ok": True, "count": 2}
    assert shield.audit.verify()
    assert shield.audit.receipts[-1].decision == Decision.ALLOW.value
