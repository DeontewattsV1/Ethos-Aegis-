from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SeverityLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    HYPOTHESIS = "hypothesis"
    PLAUSIBLE = "plausible"
    VERIFIED = "verified"


@dataclass(slots=True)
class TargetContext:
    name: str
    root: Path
    languages: List[str] = field(default_factory=list)
    build_files: List[str] = field(default_factory=list)
    test_commands: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FindingCandidate:
    identifier: str
    title: str
    summary: str
    severity: SeverityLevel
    confidence: ConfidenceLevel
    files: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    remediation_notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationOutcome:
    finding_id: str
    passed: bool
    confidence: ConfidenceLevel
    verifier_name: str
    details: str
    artifacts: List[str] = field(default_factory=list)


@dataclass(slots=True)
class PatchAssessment:
    finding_id: str
    patch_summary: str
    removes_trigger: bool
    preserves_behavior: bool
    reviewer_checks: List[str] = field(default_factory=list)
    regression_risks: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class DisclosurePacket:
    finding: FindingCandidate
    verification: VerificationOutcome
    patch_assessment: Optional[PatchAssessment]
    reproduction_steps: List[str] = field(default_factory=list)
    maintainer_notes: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        patch_lines = []
        if self.patch_assessment is not None:
            patch_lines.extend(
                [
                    "## Patch assessment",
                    f"- Summary: {self.patch_assessment.patch_summary}",
                    f"- Trigger removed: {self.patch_assessment.removes_trigger}",
                    f"- Behavior preserved: {self.patch_assessment.preserves_behavior}",
                ]
            )
            if self.patch_assessment.reviewer_checks:
                patch_lines.append("- Reviewer checks:")
                patch_lines.extend(
                    [f"  - {item}" for item in self.patch_assessment.reviewer_checks]
                )
        refs = "\n".join(f"- {ref}" for ref in self.references) or "- None"
        repro = "\n".join(f"- {step}" for step in self.reproduction_steps) or "- None"
        notes = "\n".join(f"- {note}" for note in self.maintainer_notes) or "- None"
        evidence = "\n".join(f"- {item}" for item in self.finding.evidence) or "- None"
        patch_block = "\n".join(patch_lines) if patch_lines else "## Patch assessment\n- Not provided"
        return "\n".join(
            [
                f"# Disclosure Packet: {self.finding.title}",
                "",
                "## Finding",
                f"- ID: {self.finding.identifier}",
                f"- Severity: {self.finding.severity.value}",
                f"- Confidence: {self.finding.confidence.value}",
                f"- Summary: {self.finding.summary}",
                "",
                "## Evidence",
                evidence,
                "",
                "## Verification",
                f"- Verifier: {self.verification.verifier_name}",
                f"- Passed: {self.verification.passed}",
                f"- Confidence: {self.verification.confidence.value}",
                f"- Details: {self.verification.details}",
                "",
                "## Reproduction steps",
                repro,
                "",
                "## Maintainer notes",
                notes,
                "",
                patch_block,
                "",
                "## References",
                refs,
            ]
        )
