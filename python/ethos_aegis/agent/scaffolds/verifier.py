from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Protocol

from .types import ConfidenceLevel, FindingCandidate, TargetContext, VerificationOutcome


class VerificationHook(Protocol):
    def __call__(self, target: TargetContext, finding: FindingCandidate) -> VerificationOutcome:
        ...


@dataclass(slots=True)
class TaskVerifierScaffold:
    """Runs one or more deterministic verification hooks over a finding."""

    hooks: List[VerificationHook]

    def verify(self, target: TargetContext, finding: FindingCandidate) -> VerificationOutcome:
        outcomes = [hook(target, finding) for hook in self.hooks]
        if not outcomes:
            return VerificationOutcome(
                finding_id=finding.identifier,
                passed=False,
                confidence=ConfidenceLevel.HYPOTHESIS,
                verifier_name="no-verifier",
                details="No verification hooks were configured.",
            )
        passed = all(outcome.passed for outcome in outcomes)
        confidence = (
            ConfidenceLevel.VERIFIED
            if passed
            else max((outcome.confidence for outcome in outcomes), key=_confidence_rank)
        )
        return VerificationOutcome(
            finding_id=finding.identifier,
            passed=passed,
            confidence=confidence,
            verifier_name=",".join(outcome.verifier_name for outcome in outcomes),
            details=" | ".join(outcome.details for outcome in outcomes),
            artifacts=[artifact for outcome in outcomes for artifact in outcome.artifacts],
        )


def _confidence_rank(level: ConfidenceLevel) -> int:
    order = {
        ConfidenceLevel.HYPOTHESIS: 0,
        ConfidenceLevel.PLAUSIBLE: 1,
        ConfidenceLevel.VERIFIED: 2,
    }
    return order[level]


def make_path_exists_verifier(relative_path: str) -> VerificationHook:
    def _verify(target: TargetContext, finding: FindingCandidate) -> VerificationOutcome:
        exists = (target.root / relative_path).exists()
        return VerificationOutcome(
            finding_id=finding.identifier,
            passed=exists,
            confidence=ConfidenceLevel.PLAUSIBLE if exists else ConfidenceLevel.HYPOTHESIS,
            verifier_name=f"path-exists:{relative_path}",
            details=(
                f"Confirmed presence of {relative_path} required for the finding context."
                if exists
                else f"Missing expected file {relative_path}."
            ),
            artifacts=[relative_path] if exists else [],
        )

    return _verify


def make_keyword_verifier(relative_path: str, keyword: str) -> VerificationHook:
    def _verify(target: TargetContext, finding: FindingCandidate) -> VerificationOutcome:
        path = target.root / relative_path
        if not path.exists():
            return VerificationOutcome(
                finding_id=finding.identifier,
                passed=False,
                confidence=ConfidenceLevel.HYPOTHESIS,
                verifier_name=f"keyword:{relative_path}",
                details=f"Cannot inspect missing file {relative_path}.",
            )
        text = path.read_text(encoding="utf-8", errors="ignore")
        matched = keyword in text
        return VerificationOutcome(
            finding_id=finding.identifier,
            passed=matched,
            confidence=ConfidenceLevel.PLAUSIBLE if matched else ConfidenceLevel.HYPOTHESIS,
            verifier_name=f"keyword:{relative_path}",
            details=(
                f"Located keyword '{keyword}' in {relative_path}."
                if matched
                else f"Keyword '{keyword}' not found in {relative_path}."
            ),
            artifacts=[relative_path] if matched else [],
        )

    return _verify
