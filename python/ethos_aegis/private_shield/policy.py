"""Default-deny reference monitor for AEGIS Private Shield."""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
from typing import Iterable, Sequence

from .models import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PolicyDecision,
    ProjectPolicy,
    RiskVector,
)
from .paths import PathPolicyError, canonicalize_resource_path, canonicalize_scope_pattern


def _scope_allows(path: str, scopes: Sequence[str]) -> bool:
    try:
        candidate = canonicalize_resource_path(path or "")
        normalized_scopes = tuple(canonicalize_scope_pattern(scope) for scope in scopes)
    except PathPolicyError:
        # Invalid/unrepresentable paths fail closed instead of falling back to
        # host-specific path semantics.
        return False
    return any(scope == "*" or fnmatchcase(candidate, scope) for scope in normalized_scopes)


def _destination_allows(destination: str | None, allowed: frozenset[str]) -> bool:
    if destination is None:
        return True
    return destination in allowed


class PolicyEngine:
    """Complete-mediation policy engine.

    v0.1 enforces the constitutional equation:

        Permit(a) = I ∧ P ∧ R ∧ C ∧ E ∧ T

    plus data-flow mediation, confused-deputy prevention, explicit approval gates,
    risk-adaptive capability contraction, and architecture-neutral path matching.
    """

    def evaluate(
        self,
        request: ActionRequest,
        *,
        identity_verified: bool,
        project_policy: ProjectPolicy,
        agent_grants: Iterable[CapabilityGrant],
        risk: RiskVector | None = None,
        tool_grants: Iterable[CapabilityGrant] = (),
        human_approved: bool = False,
        now: datetime | None = None,
    ) -> PolicyDecision:
        now = now or datetime.now(timezone.utc)
        risk = risk or RiskVector()
        reasons: list[str] = []

        if not identity_verified:
            return self._deny("identity_unverified", risk)

        if request.resource != project_policy.resource:
            return self._deny("resource_outside_project_policy", risk)
        if request.action not in project_policy.actions:
            return self._deny("action_outside_project_policy", risk)
        if not _scope_allows(request.path, project_policy.scopes):
            return self._deny("scope_outside_project_policy", risk)
        if request.environment not in project_policy.environments:
            return self._deny("environment_outside_project_policy", risk)
        if not _destination_allows(request.network_destination, project_policy.network_destinations):
            return self._deny("network_destination_outside_project_policy", risk)

        flow_error = self._check_flow(
            request,
            egress_destinations=project_policy.egress_destinations,
            exportable_classifications=project_policy.exportable_classifications,
            prefix="project",
        )
        if flow_error:
            return self._deny(flow_error, risk)

        matching_agent = self._matching_grants(
            request=request,
            grants=agent_grants,
            subject=request.subject,
            risk=risk.maximum,
            now=now,
        )
        if not matching_agent:
            return self._deny("no_active_agent_capability", risk)

        agent_flow_matches = [grant for grant in matching_agent if self._grant_flow_allows(request, grant)]
        if not agent_flow_matches:
            return self._deny("agent_capability_blocks_data_flow", risk)

        selected: list[CapabilityGrant] = agent_flow_matches

        # No confused deputy: when a tool is involved, the action must be inside
        # the intersection of caller, tool, and project authority.
        if request.tool_subject:
            matching_tool = self._matching_grants(
                request=request,
                grants=tool_grants,
                subject=request.tool_subject,
                risk=risk.maximum,
                now=now,
            )
            if not matching_tool:
                return self._deny("tool_authority_does_not_intersect", risk)
            tool_flow_matches = [grant for grant in matching_tool if self._grant_flow_allows(request, grant)]
            if not tool_flow_matches:
                return self._deny("tool_capability_blocks_data_flow", risk)
            selected.extend(tool_flow_matches)

        if any(grant.requires_human_approval for grant in selected) and not human_approved:
            return PolicyDecision(
                decision=Decision.REQUIRE_APPROVAL,
                reasons=("human_approval_required",),
                capability_ids=tuple(grant.capability_id for grant in selected),
                risk=risk.maximum,
            )

        reasons.append("all_security_predicates_satisfied")
        return PolicyDecision(
            decision=Decision.ALLOW,
            reasons=tuple(reasons),
            capability_ids=tuple(grant.capability_id for grant in selected),
            risk=risk.maximum,
        )

    @staticmethod
    def _deny(reason: str, risk: RiskVector) -> PolicyDecision:
        return PolicyDecision(decision=Decision.DENY, reasons=(reason,), risk=risk.maximum)

    @staticmethod
    def _check_flow(
        request: ActionRequest,
        *,
        egress_destinations: frozenset[str],
        exportable_classifications: frozenset[str],
        prefix: str,
    ) -> str | None:
        if request.output_destination is None:
            return None
        if request.output_destination not in egress_destinations:
            return f"{prefix}_egress_destination_denied"
        if request.data_classification is None:
            return f"{prefix}_egress_requires_classification"
        if request.data_classification not in exportable_classifications:
            return f"{prefix}_classification_not_exportable"
        return None

    @classmethod
    def _grant_flow_allows(cls, request: ActionRequest, grant: CapabilityGrant) -> bool:
        return (
            cls._check_flow(
                request,
                egress_destinations=grant.egress_destinations,
                exportable_classifications=grant.exportable_classifications,
                prefix="grant",
            )
            is None
        )

    @staticmethod
    def _matching_grants(
        *,
        request: ActionRequest,
        grants: Iterable[CapabilityGrant],
        subject: str,
        risk: float,
        now: datetime,
    ) -> list[CapabilityGrant]:
        matched: list[CapabilityGrant] = []
        for grant in grants:
            if grant.subject != subject:
                continue
            if grant.resource != request.resource:
                continue
            if request.action not in grant.actions:
                continue
            if request.environment not in grant.environments:
                continue
            if request.network_destination is not None and request.network_destination not in grant.network_destinations:
                continue
            if not _scope_allows(request.path, grant.scopes):
                continue
            if not grant.is_active(now):
                continue
            # Core contraction invariant: increasing risk can only remove grants.
            if risk > grant.max_risk:
                continue
            matched.append(grant)
        return matched
