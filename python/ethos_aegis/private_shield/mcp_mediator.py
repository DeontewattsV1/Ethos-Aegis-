"""Reference MCP mediator for AEGIS Private Shield.

MCP tools are invoked only after caller, tool, project, environment, risk, and
flow policy intersect successfully. Raw tool handlers remain behind the trusted
mediator boundary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from .models import ActionRequest, CapabilityGrant, ProjectPolicy, RiskVector
from .runtime import AuthorizationResult, PrivateShield


@dataclass(frozen=True)
class MCPInvocationResult:
    authorization: AuthorizationResult
    executed: bool
    output: object | None = None
    execution_error: str | None = None


@dataclass(frozen=True)
class _RegisteredTool:
    name: str
    resource: str
    tool_subject: str
    handler: Callable[[Mapping[str, object]], object]


class MCPMediator:
    """Capability-aware boundary around MCP-style tool handlers."""

    def __init__(self, shield: PrivateShield) -> None:
        self._shield = shield
        self._tools: dict[str, _RegisteredTool] = {}

    def register_tool(
        self,
        *,
        name: str,
        resource: str,
        tool_subject: str,
        handler: Callable[[Mapping[str, object]], object],
    ) -> None:
        if not name:
            raise ValueError("tool name cannot be empty")
        if not resource.startswith("mcp://"):
            raise ValueError("MCP resources must start with mcp://")
        if not tool_subject.startswith("tool://"):
            raise ValueError("tool subjects must start with tool://")
        self._tools[name] = _RegisteredTool(name, resource, tool_subject, handler)

    def invoke(
        self,
        name: str,
        *,
        subject: str,
        arguments: Mapping[str, object],
        identity_verified: bool,
        project_policy: ProjectPolicy,
        agent_grants: Iterable[CapabilityGrant],
        tool_grants: Iterable[CapabilityGrant],
        risk: RiskVector | None = None,
        human_approved: bool = False,
        now: datetime | None = None,
        output_destination: str | None = None,
        data_classification: str | None = None,
    ) -> MCPInvocationResult:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"MCP tool not registered: {name}")
        now = now or datetime.now(timezone.utc)
        risk = risk or RiskVector()

        request = ActionRequest(
            subject=subject,
            action="mcp.invoke",
            resource=tool.resource,
            path=name,
            environment="sandbox",
            output_destination=output_destination,
            data_classification=data_classification,
            tool_subject=tool.tool_subject,
        )

        decision = self._shield.policy.evaluate(
            request,
            identity_verified=identity_verified,
            project_policy=project_policy,
            agent_grants=agent_grants,
            tool_grants=tool_grants,
            risk=risk,
            human_approved=human_approved,
            now=now,
        )
        input_material = self._evidence_bytes(dict(arguments))

        if not decision.allowed:
            receipt = self._shield.audit.append(
                request,
                decision,
                input_material=input_material,
                timestamp=now,
            )
            return MCPInvocationResult(
                authorization=AuthorizationResult(decision=decision, receipt=receipt),
                executed=False,
            )

        try:
            output = tool.handler(arguments)
        except Exception as exc:
            receipt = self._shield.audit.append(
                request,
                decision,
                input_material=input_material,
                output_material=repr(exc),
                timestamp=now,
            )
            return MCPInvocationResult(
                authorization=AuthorizationResult(decision=decision, receipt=receipt),
                executed=True,
                execution_error=f"{type(exc).__name__}: {exc}",
            )

        receipt = self._shield.audit.append(
            request,
            decision,
            input_material=input_material,
            output_material=self._evidence_bytes(output),
            timestamp=now,
        )
        return MCPInvocationResult(
            authorization=AuthorizationResult(decision=decision, receipt=receipt),
            executed=True,
            output=output,
        )

    @staticmethod
    def _evidence_bytes(value: object) -> bytes:
        try:
            return json.dumps(value, sort_keys=True, default=repr).encode()
        except (TypeError, ValueError):
            return repr(value).encode()
