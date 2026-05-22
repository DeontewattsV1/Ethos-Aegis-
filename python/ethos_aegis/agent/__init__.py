"""
ethos_aegis.agent — The Agentic Generative Immune System

Autonomous, self-evolving, multi-AI deployment layer for the Ethos Aegis.
"""
from .sentinel_ai import SentinelAI, UniversalGuard
from .genesis import GenesisEngine

__all__ = ["SentinelAI", "UniversalGuard", "GenesisEngine", "TargetIntakeScaffold", "TaskVerifierScaffold", "PatchValidationScaffold", "CVDScaffold", "DefensiveResearchOrchestrator"]

from .scaffolds import (
    CVDScaffold,
    DefensiveResearchOrchestrator,
    PatchValidationScaffold,
    TargetIntakeScaffold,
    TaskVerifierScaffold,
)
