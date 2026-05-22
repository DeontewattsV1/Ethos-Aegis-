from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

from .disclosure import CVDScaffold
from .intake import TargetIntakeScaffold
from .patching import PatchValidationScaffold
from .types import FindingCandidate, PatchAssessment, TargetContext, VerificationOutcome
from .verifier import TaskVerifierScaffold


@dataclass(slots=True)
class ResearchRunReport:
    target: TargetContext
    findings: List[FindingCandidate] = field(default_factory=list)
    verifications: List[VerificationOutcome] = field(default_factory=list)
    disclosures: List[str] = field(default_factory=list)


@dataclass(slots=True)
class DefensiveResearchOrchestrator:
    """Coordinates repository-local, defensive security research steps."""

    intake: TargetIntakeScaffold
    verifier: TaskVerifierScaffold
    patching: PatchValidationScaffold
    disclosure: CVDScaffold

    def run(
        self,
        target_root: str | Path,
        candidates: Sequence[FindingCandidate],
    ) -> ResearchRunReport:
        target = self.intake.from_path(target_root)
        report = ResearchRunReport(target=target, findings=list(candidates))

        for finding in candidates:
            verification = self.verifier.verify(target, finding)
            report.verifications.append(verification)

            patch_assessment = self.patching.assess(
                finding,
                verification,
                patch_summary="Manual maintainer patch required after deterministic confirmation.",
                removes_trigger=verification.passed,
                preserves_behavior=True,
            )
            packet = self.disclosure.build_packet(finding, verification, patch_assessment)
            report.disclosures.append(str(self.disclosure.write_packet(packet)))

        return report
