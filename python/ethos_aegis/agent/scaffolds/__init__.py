"""Composable defensive-security scaffolds for Mythos-style model workflows."""

from .types import (
    ConfidenceLevel,
    DisclosurePacket,
    FindingCandidate,
    PatchAssessment,
    SeverityLevel,
    TargetContext,
    VerificationOutcome,
)
from .intake import TargetIntakeScaffold
from .verifier import TaskVerifierScaffold, VerificationHook
from .patching import PatchValidationScaffold
from .disclosure import CVDScaffold
from .orchestrator import DefensiveResearchOrchestrator, ResearchRunReport

__all__ = [
    "ConfidenceLevel",
    "DisclosurePacket",
    "FindingCandidate",
    "PatchAssessment",
    "SeverityLevel",
    "TargetContext",
    "VerificationOutcome",
    "TargetIntakeScaffold",
    "TaskVerifierScaffold",
    "VerificationHook",
    "PatchValidationScaffold",
    "CVDScaffold",
    "DefensiveResearchOrchestrator",
    "ResearchRunReport",
]
