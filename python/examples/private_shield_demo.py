"""Minimal executable AEGIS Private Shield example."""
from datetime import datetime, timedelta, timezone

from ethos_aegis.private_shield import (
    ActionRequest,
    CapabilityGrant,
    PrivateShield,
    ProjectPolicy,
    RiskVector,
)

now = datetime.now(timezone.utc)
shield = PrivateShield(signing_key=b"replace-with-kms-backed-key-material")

project = ProjectPolicy(
    resource="repo://project",
    actions=frozenset({"source.read", "production.deploy"}),
    scopes=("src/**", "deploy/**"),
    environments=frozenset({"sandbox"}),
)

read_grant = CapabilityGrant(
    capability_id="cap_read",
    subject="agent://coder-17",
    resource="repo://project",
    actions=frozenset({"source.read"}),
    scopes=("src/**",),
    issued_at=now - timedelta(seconds=5),
    expires_at=now + timedelta(minutes=10),
    max_risk=0.85,
)

deploy_grant = CapabilityGrant(
    capability_id="cap_deploy",
    subject="agent://coder-17",
    resource="repo://project",
    actions=frozenset({"production.deploy"}),
    scopes=("deploy/**",),
    issued_at=now - timedelta(seconds=5),
    expires_at=now + timedelta(minutes=10),
    max_risk=0.20,
    requires_human_approval=True,
)

grants = [read_grant, deploy_grant]

read = shield.authorize(
    ActionRequest(
        subject="agent://coder-17",
        action="source.read",
        resource="repo://project",
        path="src/auth/session.py",
    ),
    identity_verified=True,
    project_policy=project,
    agent_grants=grants,
    risk=RiskVector(source=0.45),
    now=now,
)

blocked_deploy = shield.authorize(
    ActionRequest(
        subject="agent://coder-17",
        action="production.deploy",
        resource="repo://project",
        path="deploy/prod.yaml",
    ),
    identity_verified=True,
    project_policy=project,
    agent_grants=grants,
    risk=RiskVector(production=0.45),
    now=now,
)

print("read:", read.decision.decision.value)
print("deploy:", blocked_deploy.decision.decision.value)
print("audit-chain-valid:", shield.audit.verify())
