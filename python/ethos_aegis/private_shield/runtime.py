"""Reference runtime that combines policy evaluation and evidence capture."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .audit import AuditChain, AuditReceipt
from .models import ActionRequest, CapabilityGrant, PolicyDecision, ProjectPolicy, RiskVector
from .policy import PolicyEngine


@dataclass(frozen=True)
class AuthorizationResult:
    decision: PolicyDecision
    receipt: AuditReceipt


class PrivateShield:
    """Small reference monitor for agent/tool operations."""

    def __init__(self, *, signing_key: bytes, policy_engine: PolicyEngine | None = None) -> None:
        self.policy = policy_engine or PolicyEngine()
        self.audit = AuditChain(signing_key)

    def authorize(
        self,
        request: ActionRequest,
        *,
        identity_verified: bool,
        project_policy: ProjectPolicy,
        agent_grants: Iterable[CapabilityGrant],
        risk: RiskVector | None = None,
        tool_grants: Iterable[CapabilityGrant] = (),
        human_approved: bool = False,
        input_material: bytes | str = b"",
        output_material: bytes | str = b"",
        now: datetime | None = None,
    ) -> AuthorizationResult:
        decision = self.policy.evaluate(
            request,
            identity_verified=identity_verified,
            project_policy=project_policy,
            agent_grants=agent_grants,
            risk=risk,
            tool_grants=tool_grants,
            human_approved=human_approved,
            now=now,
        )
        receipt = self.audit.append(
            request,
            decision,
            input_material=input_material,
            output_material=output_material,
            timestamp=now,
        )
        return AuthorizationResult(decision=decision, receipt=receipt)
