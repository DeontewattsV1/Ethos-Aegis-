"""Typed, deliberately small contracts for the Ethos Aegis security toolkit."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ethos_aegis.agent.scaffolds.types import FindingCandidate


class ToolId(str, Enum):
    TRUFFLEHOG = "trufflehog"
    SHERLOCK = "sherlock"
    GHIDRA = "ghidra"
    MITMPROXY = "mitmproxy"
    MARAUDER = "marauder"


class ToolkitError(ValueError):
    """A safe, fixed-message error; never attach raw tool output."""


@dataclass(frozen=True)
class SecurityFinding:
    identifier: str
    tool: ToolId
    category: str
    severity: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: str = "tool_reported"

    def to_candidate(self) -> FindingCandidate:
        """Feed observations into the existing defensive research scaffold."""
        from ethos_aegis.agent.scaffolds.types import (
            ConfidenceLevel,
            FindingCandidate,
            SeverityLevel,
        )

        return FindingCandidate(
            identifier=self.identifier,
            title=self.category,
            summary=self.summary,
            severity=SeverityLevel(self.severity),
            confidence=ConfidenceLevel.HYPOTHESIS,
            evidence=[f"source_sha256={self.evidence.get('source_sha256', '')}"],
            metadata={"tool": self.tool.value, "observation": dict(self.evidence)},
        )


@dataclass(frozen=True)
class SecurityReport:
    tool: ToolId
    source_sha256: str
    findings: tuple[SecurityFinding, ...]
    records_seen: int
    mode: str = "import"
    schema_version: str = "ethos-aegis.security-report.v1"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["tool"] = self.tool.value
        for item in result["findings"]:
            item["tool"] = item["tool"].value
        return result


@dataclass(frozen=True)
class ToolPlan:
    tool: ToolId
    target_id: str
    network_requested: bool
    description: str


CATALOG = {
    ToolId.TRUFFLEHOG: ("Local secret exposure", "local filesystem runner + JSONL import"),
    ToolId.SHERLOCK: ("Username exposure", "site-scoped username runner + CSV import"),
    ToolId.GHIDRA: ("Static binary inspection", "headless runner + summary import"),
    ToolId.MITMPROXY: ("Application egress", "offline HAR / sanitized flow import"),
    ToolId.MARAUDER: ("Wireless inventory", "offline device-scoped summary import"),
}
