from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .types import DisclosurePacket, FindingCandidate, PatchAssessment, VerificationOutcome


@dataclass(slots=True)
class CVDScaffold:
    """Builds coordinated vulnerability disclosure artifacts for maintainers."""

    output_dir: Path

    def build_packet(
        self,
        finding: FindingCandidate,
        verification: VerificationOutcome,
        patch_assessment: PatchAssessment | None = None,
    ) -> DisclosurePacket:
        reproduction_steps = [
            "Check out the affected revision in an isolated environment.",
            "Run the minimal reproducer or verifier attached to the report.",
            "Apply the candidate patch in a review branch.",
            "Re-run the reproducer and the project's regression tests.",
        ]
        maintainer_notes = [
            "Treat AI-generated analysis as a lead, not as sole proof.",
            "Prefer private triage until severity and exploitability are understood.",
            "Confirm fix scope against adjacent code paths before public disclosure.",
        ]
        return DisclosurePacket(
            finding=finding,
            verification=verification,
            patch_assessment=patch_assessment,
            reproduction_steps=reproduction_steps,
            maintainer_notes=maintainer_notes,
            references=["Coordinated vulnerability disclosure process", "Repository-specific test suite"],
        )

    def write_packet(self, packet: DisclosurePacket) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{packet.finding.identifier}.md"
        path.write_text(packet.to_markdown(), encoding="utf-8")
        return path
