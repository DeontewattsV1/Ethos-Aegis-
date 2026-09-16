import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from ethos_aegis.private_shield import (
    CapabilityGrant,
    Decision,
    MCPMediator,
    PrivateShield,
    ProjectPolicy,
    SecretBroker,
    SecretExfiltrationError,
    SecretLeaseError,
)

NOW = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
SIGNING_KEY = b"0123456789abcdef0123456789abcdef"


def _grant(
    capability_id: str,
    *,
    subject: str,
    resource: str,
    action: str,
    scopes: tuple[str, ...] = ("*",),
) -> CapabilityGrant:
    return CapabilityGrant(
        capability_id=capability_id,
        subject=subject,
        resource=resource,
        actions=frozenset({action}),
        scopes=scopes,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )


def test_secret_broker_returns_opaque_purpose_bound_lease_and_consumes_it_once() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    broker = SecretBroker(shield)
    secret_ref = "secret://github/production"
    raw_secret = "ghp_example_super_secret_value"
    purpose = "github.pull_request.create"
    broker.register(secret_ref, raw_secret)
    broker.register_adapter(
        purpose,
        lambda secret, arguments: {
            "credential_fingerprint": hashlib.sha256(secret).hexdigest()[:12],
            "repo": arguments.get("repo"),
        },
    )
    broker.register_adapter("database.healthcheck", lambda secret, arguments: {"ok": True})

    policy = ProjectPolicy(resource=secret_ref, actions=frozenset({"secret.use"}), scopes=("*",))
    grant = _grant(
        "cap-secret-use",
        subject="agent://coder-17",
        resource=secret_ref,
        action="secret.use",
    )
    result = broker.request_lease(
        subject="agent://coder-17",
        secret_ref=secret_ref,
        purpose=purpose,
        identity_verified=True,
        project_policy=policy,
        agent_grants=[grant],
        now=NOW,
        ttl_seconds=30,
        max_uses=1,
    )

    assert result.authorization.decision.decision is Decision.ALLOW
    assert result.lease is not None
    assert raw_secret not in repr(result.lease)

    # A lease cannot be redirected to another trusted adapter, and the failed
    # purpose check must not consume the valid one-use lease.
    with pytest.raises(SecretLeaseError):
        broker.execute(
            result.lease.lease_id,
            "database.healthcheck",
            now=NOW + timedelta(milliseconds=500),
        )

    output = broker.execute(
        result.lease.lease_id,
        purpose,
        arguments={"repo": "goodshyt/project"},
        now=NOW + timedelta(seconds=1),
    )
    assert output == {
        "credential_fingerprint": hashlib.sha256(raw_secret.encode()).hexdigest()[:12],
        "repo": "goodshyt/project",
    }
    assert raw_secret not in repr(output)
    assert shield.audit.verify()
    assert len(shield.audit.receipts) == 2

    with pytest.raises(SecretLeaseError):
        broker.execute(result.lease.lease_id, purpose, now=NOW + timedelta(seconds=2))


def test_secret_broker_requires_pre_registered_adapter() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    broker = SecretBroker(shield)
    secret_ref = "secret://github/production"
    broker.register(secret_ref, "token")
    policy = ProjectPolicy(resource=secret_ref, actions=frozenset({"secret.use"}), scopes=("*",))
    grant = _grant("cap-secret", subject="agent://coder-17", resource=secret_ref, action="secret.use")

    with pytest.raises(SecretLeaseError, match="registered trusted adapter"):
        broker.request_lease(
            subject="agent://coder-17",
            secret_ref=secret_ref,
            purpose="caller.supplied.callback",
            identity_verified=True,
            project_policy=policy,
            agent_grants=[grant],
            now=NOW,
        )


def test_secret_broker_blocks_direct_secret_reflection() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    broker = SecretBroker(shield)
    secret_ref = "secret://database/production"
    purpose = "database.healthcheck"
    broker.register(secret_ref, "database-password-value")
    broker.register_adapter(purpose, lambda secret, arguments: secret.decode())
    policy = ProjectPolicy(resource=secret_ref, actions=frozenset({"secret.use"}), scopes=("*",))
    grant = _grant("cap-db-use", subject="agent://coder-17", resource=secret_ref, action="secret.use")
    lease = broker.request_lease(
        subject="agent://coder-17",
        secret_ref=secret_ref,
        purpose=purpose,
        identity_verified=True,
        project_policy=policy,
        agent_grants=[grant],
        now=NOW,
    ).lease
    assert lease is not None

    with pytest.raises(SecretExfiltrationError):
        broker.execute(lease.lease_id, purpose, now=NOW + timedelta(seconds=1))

    assert shield.audit.verify()
    assert shield.audit.receipts[-1].decision == Decision.DENY.value


def test_mcp_denial_prevents_handler_execution() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    mediator = MCPMediator(shield)
    resource = "mcp://github/pull-request-create"
    calls: list[dict[str, object]] = []

    def handler(arguments):
        calls.append(dict(arguments))
        return {"number": 278}

    mediator.register_tool(
        name="github.create_pr",
        resource=resource,
        tool_subject="tool://github",
        handler=handler,
    )
    policy = ProjectPolicy(resource=resource, actions=frozenset({"mcp.invoke"}), scopes=("github.create_pr",))
    agent_grant = _grant(
        "cap-agent-mcp",
        subject="agent://coder-17",
        resource=resource,
        action="mcp.invoke",
        scopes=("github.create_pr",),
    )
    wrong_tool_grant = _grant(
        "cap-tool-wrong",
        subject="tool://github",
        resource=resource,
        action="github.read",
        scopes=("github.create_pr",),
    )

    result = mediator.invoke(
        "github.create_pr",
        subject="agent://coder-17",
        arguments={"title": "blocked"},
        identity_verified=True,
        project_policy=policy,
        agent_grants=[agent_grant],
        tool_grants=[wrong_tool_grant],
        now=NOW,
    )

    assert result.authorization.decision.decision is Decision.DENY
    assert result.authorization.decision.reasons == ("tool_authority_does_not_intersect",)
    assert result.executed is False
    assert calls == []
    assert shield.audit.verify()


def test_mcp_executes_only_inside_agent_tool_project_intersection() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    mediator = MCPMediator(shield)
    resource = "mcp://github/pull-request-create"
    calls: list[dict[str, object]] = []

    def handler(arguments):
        calls.append(dict(arguments))
        return {"number": 278, "status": "created"}

    mediator.register_tool(
        name="github.create_pr",
        resource=resource,
        tool_subject="tool://github",
        handler=handler,
    )
    policy = ProjectPolicy(resource=resource, actions=frozenset({"mcp.invoke"}), scopes=("github.create_pr",))
    agent_grant = _grant(
        "cap-agent-mcp",
        subject="agent://coder-17",
        resource=resource,
        action="mcp.invoke",
        scopes=("github.create_pr",),
    )
    tool_grant = _grant(
        "cap-tool-mcp",
        subject="tool://github",
        resource=resource,
        action="mcp.invoke",
        scopes=("github.create_pr",),
    )

    result = mediator.invoke(
        "github.create_pr",
        subject="agent://coder-17",
        arguments={"title": "AEGIS test PR"},
        identity_verified=True,
        project_policy=policy,
        agent_grants=[agent_grant],
        tool_grants=[tool_grant],
        now=NOW,
    )

    assert result.authorization.decision.decision is Decision.ALLOW
    assert result.executed is True
    assert result.execution_error is None
    assert result.output == {"number": 278, "status": "created"}
    assert calls == [{"title": "AEGIS test PR"}]
    assert shield.audit.verify()
    receipt = result.authorization.receipt
    assert receipt.input_hash != "AEGIS test PR"
    assert receipt.output_hash != repr(result.output)


def test_mcp_adapter_can_consume_opaque_secret_lease_without_agent_possession() -> None:
    shield = PrivateShield(signing_key=SIGNING_KEY)
    broker = SecretBroker(shield)
    mediator = MCPMediator(shield)

    raw_secret = "github-production-token-value"
    secret_ref = "secret://github/production"
    purpose = "github.pull_request.create"
    broker.register(secret_ref, raw_secret)
    broker.register_adapter(
        purpose,
        lambda credential, arguments: {
            "number": 279,
            "title": arguments["title"],
            "credential_fingerprint": hashlib.sha256(credential).hexdigest()[:12],
        },
    )

    secret_policy = ProjectPolicy(resource=secret_ref, actions=frozenset({"secret.use"}), scopes=("*",))
    secret_grant = _grant(
        "cap-github-secret",
        subject="agent://coder-17",
        resource=secret_ref,
        action="secret.use",
    )
    lease = broker.request_lease(
        subject="agent://coder-17",
        secret_ref=secret_ref,
        purpose=purpose,
        identity_verified=True,
        project_policy=secret_policy,
        agent_grants=[secret_grant],
        now=NOW,
        ttl_seconds=30,
        max_uses=1,
    ).lease
    assert lease is not None
    assert raw_secret not in repr(lease)

    mcp_resource = "mcp://github/pull-request-create"

    def github_adapter(arguments):
        return broker.execute(
            str(arguments["credential_lease"]),
            purpose,
            arguments={"title": str(arguments["title"])},
            now=NOW + timedelta(seconds=2),
        )

    mediator.register_tool(
        name="github.create_pr",
        resource=mcp_resource,
        tool_subject="tool://github",
        handler=github_adapter,
    )
    mcp_policy = ProjectPolicy(
        resource=mcp_resource,
        actions=frozenset({"mcp.invoke"}),
        scopes=("github.create_pr",),
    )
    agent_mcp_grant = _grant(
        "cap-agent-github-mcp",
        subject="agent://coder-17",
        resource=mcp_resource,
        action="mcp.invoke",
        scopes=("github.create_pr",),
    )
    tool_mcp_grant = _grant(
        "cap-tool-github-mcp",
        subject="tool://github",
        resource=mcp_resource,
        action="mcp.invoke",
        scopes=("github.create_pr",),
    )

    result = mediator.invoke(
        "github.create_pr",
        subject="agent://coder-17",
        arguments={
            "title": "Opaque credential integration",
            "credential_lease": lease.lease_id,
        },
        identity_verified=True,
        project_policy=mcp_policy,
        agent_grants=[agent_mcp_grant],
        tool_grants=[tool_mcp_grant],
        now=NOW + timedelta(seconds=1),
    )

    assert result.authorization.decision.decision is Decision.ALLOW
    assert result.executed is True
    assert result.execution_error is None
    assert result.output == {
        "number": 279,
        "title": "Opaque credential integration",
        "credential_fingerprint": hashlib.sha256(raw_secret.encode()).hexdigest()[:12],
    }
    assert raw_secret not in repr(result.output)
    assert raw_secret not in repr(result.authorization.receipt)
    assert shield.audit.verify()
    assert [receipt.action for receipt in shield.audit.receipts] == [
        "secret.use",
        "secret.use",
        "mcp.invoke",
    ]

    with pytest.raises(SecretLeaseError):
        broker.execute(lease.lease_id, purpose, now=NOW + timedelta(seconds=3))
