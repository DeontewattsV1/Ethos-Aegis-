# Ethos Aegis defensive security scaffolds

**Status:** repository-local defensive review utilities. The current implementation under `python/ethos_aegis/agent/scaffolds/` is authoritative.

The supplied Claude/Mythos scaffolds archive describes bounded source intake, deterministic verification, patch assessment, coordinated disclosure, and human-reviewable orchestration. Those components are already present in this repository. This integration adds a conservative usage skill and this documentation, **not** a parallel agent runtime or new autonomous security authority.

| Workflow | Existing component | Trust boundary |
|---|---|---|
| Intake | `TargetIntakeScaffold` | Only locally available, authorized sources |
| Verification | `TaskVerifierScaffold` | A successful predicate validates that predicate, not the entire vulnerability claim |
| Patch assessment | `PatchValidationScaffold` | Checks and reviewer evidence required before making outcome claims |
| Disclosure | `CVDScaffold` | Store redacted packets in an access-controlled output location |
| Orchestration | `DefensiveResearchOrchestrator` | Human review and policy authorization govern any external effects |

No exploit execution, remote intrusion, public vulnerability disclosure, auto-merge, or unauthorized credential access is introduced.

For existing code, see [scaffold module](../python/ethos_aegis/agent/scaffolds/) and [tests](../python/tests/test_scaffolds.py). For agent workflows, see [defensive-security skill](../.claude/skills/defensive-security-scaffolds/SKILL.md).

**Provenance:** adapted from user-supplied `Ethos-Aegis-Claude-Mythos-Scaffolds(20261008-011100).zip`. Existing implementations take precedence over older archive copies. "Mythos-style" is a descriptive interface convention, not a claim of endorsement or partnership with Anthropic.
