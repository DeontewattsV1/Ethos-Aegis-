from __future__ import annotations

from pathlib import Path

from ethos_aegis.agent.scaffolds import (
    CVDScaffold,
    ConfidenceLevel,
    DefensiveResearchOrchestrator,
    FindingCandidate,
    PatchValidationScaffold,
    SeverityLevel,
    TargetIntakeScaffold,
    TaskVerifierScaffold,
)
from ethos_aegis.agent.scaffolds.verifier import make_keyword_verifier, make_path_exists_verifier


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_target_intake_detects_expected_files() -> None:
    context = TargetIntakeScaffold().from_path(REPO_ROOT)
    assert "pyproject.toml" in context.build_files
    assert "python" in context.languages


def test_verifier_combines_hooks() -> None:
    context = TargetIntakeScaffold().from_path(REPO_ROOT)
    finding = FindingCandidate(
        identifier="f-1",
        title="demo",
        summary="demo",
        severity=SeverityLevel.LOW,
        confidence=ConfidenceLevel.HYPOTHESIS,
    )
    verifier = TaskVerifierScaffold(
        hooks=[
            make_path_exists_verifier("README.md"),
            make_keyword_verifier("README.md", "Ethos Aegis"),
        ]
    )
    outcome = verifier.verify(context, finding)
    assert outcome.passed is True
    assert outcome.confidence == ConfidenceLevel.VERIFIED


def test_orchestrator_writes_disclosure_packet(tmp_path: Path) -> None:
    finding = FindingCandidate(
        identifier="f-2",
        title="review path",
        summary="review path summary",
        severity=SeverityLevel.MODERATE,
        confidence=ConfidenceLevel.PLAUSIBLE,
    )
    orchestrator = DefensiveResearchOrchestrator(
        intake=TargetIntakeScaffold(),
        verifier=TaskVerifierScaffold(hooks=[make_path_exists_verifier("README.md")]),
        patching=PatchValidationScaffold(),
        disclosure=CVDScaffold(output_dir=tmp_path),
    )
    report = orchestrator.run(REPO_ROOT, [finding])
    assert len(report.disclosures) == 1
    output_file = Path(report.disclosures[0])
    assert output_file.exists()
    assert "Disclosure Packet" in output_file.read_text(encoding="utf-8")
