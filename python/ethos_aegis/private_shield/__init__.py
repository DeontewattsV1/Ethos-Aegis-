"""AEGIS Private Shield — compromise-containment primitives for agentic systems."""

from .audit import AuditChain, AuditReceipt
from .mcp_mediator import MCPInvocationResult, MCPMediator
from .models import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PolicyDecision,
    ProjectPolicy,
    RiskVector,
)
from .paths import PathPolicyError, canonicalize_resource_path, canonicalize_scope_pattern
from .policy import PolicyEngine
from .runtime import AuthorizationResult, PrivateShield
from .secret_broker import (
    SecretBroker,
    SecretExfiltrationError,
    SecretLease,
    SecretLeaseError,
    SecretLeaseResult,
)

__all__ = [
    "ActionRequest",
    "AuditChain",
    "AuditReceipt",
    "AuthorizationResult",
    "CapabilityGrant",
    "Decision",
    "MCPInvocationResult",
    "MCPMediator",
    "PathPolicyError",
    "PolicyDecision",
    "PolicyEngine",
    "PrivateShield",
    "ProjectPolicy",
    "RiskVector",
    "SecretBroker",
    "SecretExfiltrationError",
    "SecretLease",
    "SecretLeaseError",
    "SecretLeaseResult",
    "canonicalize_resource_path",
    "canonicalize_scope_pattern",
]
