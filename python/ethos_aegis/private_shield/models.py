"""Core types for AEGIS Private Shield.

The model is intentionally dependency-free so the reference monitor can remain
small, inspectable, and easy to embed in notebooks, agents, and service runtimes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import FrozenSet, Tuple


class Decision(str, Enum):
    """Authorization outcomes produced by the reference monitor."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class RiskVector:
    """Risk/uncertainty scores by security domain, each normalized to [0, 1]."""

    secret: float = 0.0
    network: float = 0.0
    source: float = 0.0
    execution: float = 0.0
    production: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("secret", self.secret),
            ("network", self.network),
            ("source", self.source),
            ("execution", self.execution),
            ("production", self.production),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} risk must be between 0 and 1")

    @property
    def maximum(self) -> float:
        """Conservative aggregate risk used by the v0.1 contraction engine."""

        return max(self.secret, self.network, self.source, self.execution, self.production)


@dataclass(frozen=True)
class CapabilityGrant:
    """A short-lived, scope-bounded grant.

    AEGIS models authority as a set of grants instead of a bearer credential with
    ambient power. Multiple grants can exist for the same subject with different
    risk ceilings. As uncertainty rises, grants naturally fall out of the active
    set, producing monotonic capability contraction.
    """

    capability_id: str
    subject: str
    resource: str
    actions: FrozenSet[str]
    scopes: Tuple[str, ...] = ("*",)
    environments: FrozenSet[str] = frozenset({"sandbox"})
    network_destinations: FrozenSet[str] = frozenset()
    egress_destinations: FrozenSet[str] = frozenset()
    exportable_classifications: FrozenSet[str] = frozenset()
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.max.replace(tzinfo=timezone.utc))
    max_risk: float = 1.0
    requires_human_approval: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_risk <= 1.0:
            raise ValueError("max_risk must be between 0 and 1")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")

    def is_active(self, now: datetime) -> bool:
        return self.issued_at <= now < self.expires_at


@dataclass(frozen=True)
class ProjectPolicy:
    """Project-wide upper bound on delegated authority."""

    resource: str
    actions: FrozenSet[str]
    scopes: Tuple[str, ...] = ("*",)
    environments: FrozenSet[str] = frozenset({"sandbox"})
    network_destinations: FrozenSet[str] = frozenset()
    egress_destinations: FrozenSet[str] = frozenset()
    exportable_classifications: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class ActionRequest:
    """One security-sensitive operation submitted to the reference monitor."""

    subject: str
    action: str
    resource: str
    path: str = ""
    environment: str = "sandbox"
    network_destination: str | None = None
    output_destination: str | None = None
    data_classification: str | None = None
    tool_subject: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    """Explainable authorization result."""

    decision: Decision
    reasons: Tuple[str, ...]
    capability_ids: Tuple[str, ...] = ()
    risk: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW
