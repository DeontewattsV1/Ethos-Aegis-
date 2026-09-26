from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ethos_aegis.private_shield import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PrivateShield,
    ProjectPolicy,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_denied_attempt_still_produces_tamper_evident_receipt() -> None:
    shield = PrivateShield(signing_key=b"0123456789abcdef0123456789abcdef")
    policy = ProjectPolicy(
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
    )
    grant = CapabilityGrant(
        capability_id="cap-read",
        subject="agent://coder-17",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )

    result = shield.authorize(
        ActionRequest("agent://coder-17", "source.read", "repo://project", path="secrets/key.txt"),
        identity_verified=True,
        project_policy=policy,
        agent_grants=[grant],
        input_material="request-body",
        now=NOW,
    )

    assert result.decision.decision is Decision.DENY
    assert shield.audit.verify()
    assert result.receipt.input_hash != "request-body"


def test_receipt_chain_detects_tampering() -> None:
    shield = PrivateShield(signing_key=b"0123456789abcdef0123456789abcdef")
    policy = ProjectPolicy(
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
    )
    grant = CapabilityGrant(
        capability_id="cap-read",
        subject="agent://coder-17",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )
    request = ActionRequest("agent://coder-17", "source.read", "repo://project", path="src/auth.py")

    first = shield.authorize(
        request,
        identity_verified=True,
        project_policy=policy,
        agent_grants=[grant],
        now=NOW,
    ).receipt
    shield.authorize(
        request,
        identity_verified=True,
        project_policy=policy,
        agent_grants=[grant],
        now=NOW + timedelta(seconds=1),
    )

    assert shield.audit.verify()
    tampered = (replace(first, decision="DENY"),) + shield.audit.receipts[1:]
    assert shield.audit.verify(tampered) is False
