from datetime import datetime, timedelta, timezone

from ethos_aegis.private_shield import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PolicyEngine,
    ProjectPolicy,
    RiskVector,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def grant(
    capability_id: str,
    *,
    subject: str = "agent://coder-17",
    actions: frozenset[str] = frozenset({"source.read"}),
    scopes: tuple[str, ...] = ("src/**",),
    max_risk: float = 1.0,
    approval: bool = False,
    egress: frozenset[str] = frozenset(),
    exportable: frozenset[str] = frozenset(),
) -> CapabilityGrant:
    return CapabilityGrant(
        capability_id=capability_id,
        subject=subject,
        resource="repo://project",
        actions=actions,
        scopes=scopes,
        environments=frozenset({"sandbox"}),
        egress_destinations=egress,
        exportable_classifications=exportable,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        max_risk=max_risk,
        requires_human_approval=approval,
    )


def policy(**overrides) -> ProjectPolicy:
    values = {
        "resource": "repo://project",
        "actions": frozenset({"source.read", "production.deploy"}),
        "scopes": ("src/**", "deploy/**"),
        "environments": frozenset({"sandbox"}),
        "egress_destinations": frozenset({"github://approved-repo"}),
        "exportable_classifications": frozenset({"public", "internal"}),
    }
    values.update(overrides)
    return ProjectPolicy(**values)


def test_default_deny_when_identity_is_unverified() -> None:
    decision = PolicyEngine().evaluate(
        ActionRequest("agent://coder-17", "source.read", "repo://project", path="src/auth.py"),
        identity_verified=False,
        project_policy=policy(),
        agent_grants=[grant("cap-read")],
        now=NOW,
    )
    assert decision.decision is Decision.DENY
    assert decision.reasons == ("identity_unverified",)


def test_expired_capability_is_denied() -> None:
    expired = CapabilityGrant(
        capability_id="cap-expired",
        subject="agent://coder-17",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
        issued_at=NOW - timedelta(minutes=20),
        expires_at=NOW - timedelta(minutes=10),
    )
    decision = PolicyEngine().evaluate(
        ActionRequest("agent://coder-17", "source.read", "repo://project", path="src/auth.py"),
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[expired],
        now=NOW,
    )
    assert decision.decision is Decision.DENY
    assert "no_active_agent_capability" in decision.reasons


def test_authority_contracts_monotonically_as_risk_rises() -> None:
    engine = PolicyEngine()
    read = grant("cap-read", actions=frozenset({"source.read"}), max_risk=0.85)
    deploy = grant(
        "cap-deploy",
        actions=frozenset({"production.deploy"}),
        scopes=("deploy/**",),
        max_risk=0.20,
    )

    low_risk_deploy = engine.evaluate(
        ActionRequest("agent://coder-17", "production.deploy", "repo://project", path="deploy/prod.yaml"),
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[read, deploy],
        risk=RiskVector(production=0.10),
        now=NOW,
    )
    elevated_risk_deploy = engine.evaluate(
        ActionRequest("agent://coder-17", "production.deploy", "repo://project", path="deploy/prod.yaml"),
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[read, deploy],
        risk=RiskVector(production=0.50),
        now=NOW,
    )
    elevated_risk_read = engine.evaluate(
        ActionRequest("agent://coder-17", "source.read", "repo://project", path="src/auth.py"),
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[read, deploy],
        risk=RiskVector(source=0.50),
        now=NOW,
    )

    assert low_risk_deploy.decision is Decision.ALLOW
    assert elevated_risk_deploy.decision is Decision.DENY
    assert elevated_risk_read.decision is Decision.ALLOW


def test_tool_authority_must_intersect_agent_authority() -> None:
    decision = PolicyEngine().evaluate(
        ActionRequest(
            "agent://coder-17",
            "source.read",
            "repo://project",
            path="src/auth.py",
            tool_subject="tool://github",
        ),
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[grant("cap-agent")],
        tool_grants=[grant("cap-tool", subject="tool://github", actions=frozenset({"github.pr.create"}))],
        now=NOW,
    )
    assert decision.decision is Decision.DENY
    assert decision.reasons == ("tool_authority_does_not_intersect",)


def test_private_read_does_not_imply_export() -> None:
    request = ActionRequest(
        "agent://coder-17",
        "source.read",
        "repo://project",
        path="src/auth.py",
        output_destination="github://approved-repo",
        data_classification="private",
    )
    decision = PolicyEngine().evaluate(
        request,
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[
            grant(
                "cap-read",
                egress=frozenset({"github://approved-repo"}),
                exportable=frozenset({"public", "internal"}),
            )
        ],
        now=NOW,
    )
    assert decision.decision is Decision.DENY
    assert decision.reasons == ("project_classification_not_exportable",)


def test_human_approval_gate_is_explicit() -> None:
    gated = grant("cap-gated", approval=True)
    request = ActionRequest("agent://coder-17", "source.read", "repo://project", path="src/auth.py")
    engine = PolicyEngine()

    pending = engine.evaluate(
        request,
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[gated],
        now=NOW,
    )
    approved = engine.evaluate(
        request,
        identity_verified=True,
        project_policy=policy(),
        agent_grants=[gated],
        human_approved=True,
        now=NOW,
    )

    assert pending.decision is Decision.REQUIRE_APPROVAL
    assert approved.decision is Decision.ALLOW
