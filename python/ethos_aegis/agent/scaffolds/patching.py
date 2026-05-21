from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .types import FindingCandidate, PatchAssessment, VerificationOutcome


@dataclass(slots=True)
class PatchValidationScaffold:
    """Minimal deterministic rubric for reviewing a proposed defensive patch."""

    require_reviewer_checks: bool = True

    def assess(
        self,
        finding: FindingCandidate,
        verification: VerificationOutcome,
        patch_summary: str,
        *,
        removes_trigger: bool,
        preserves_behavior: bool,
        reviewer_checks: List[str] | None = None,
        regression_risks: List[str] | None = None,
    ) -> PatchAssessment:
        checks = list(reviewer_checks or [])
        if self.require_reviewer_checks and not checks:
            checks = [
                "Run the smallest reproducer before and after the patch.",
                "Run the target project's existing regression suite.",
                "Confirm no new unsafe configuration paths were introduced.",
            ]
        notes = []
        if not verification.passed:
            notes.append("Underlying finding has not been fully verified; patch should not be merged on AI judgment alone.")
        if not removes_trigger:
            notes.append("Patch does not yet demonstrate removal of the trigger condition.")
        if not preserves_behavior:
            notes.append("Patch may alter intended behavior and needs maintainer review.")
        return PatchAssessment(
            finding_id=finding.identifier,
            patch_summary=patch_summary,
            removes_trigger=removes_trigger,
            preserves_behavior=preserves_behavior,
            reviewer_checks=checks,
            regression_risks=list(regression_risks or []),
            notes=notes,
        )
