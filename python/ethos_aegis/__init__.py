"""
ethos_aegis — The Sovereign Integrity Mesh for AI

A living, adaptive digital immune architecture that maps every biological
defense mechanism into rigorous computational infrastructure for the
purification of AI systems.

Quick start:
    from ethos_aegis import EthosAegis, AegisVitality

    aegis    = EthosAegis()
    vitality = AegisVitality(aegis)
    vitality.nourish()
    vitality.exercise()

    verdict, notes = vitality.adjudicate_with_vitality("user input")
    print(verdict.axiological_report)
"""

from ethos_aegis.core.aegis import (
    EthosAegis,
    AegisVerdict,
    Malignum,
    MalignaClass,
    CorruptionDepth,
    SentinelCell,
    VanguardProbe,
    LogosScythe,
    MnemosyneCache,
    SanitasSwarm,
    EntropicWatch,
    TaintBeacon,
    FinalityForge,
    CytokineCommand,
)

from ethos_aegis.vitality.protocol import (
    AegisVitality,
    VitalityReport,
    VitalityLevel,
    NutrientClass,
    NutrientPlex,
    KineticRegimen,
    SomnaticCycle,
    NeuroStressBuffer,
    HematopoieticBoost,
    ProbiomicBaseline,
    VitalityMonitor,
)

from ethos_aegis.security.vault import (
    VaultKeeper,
    SessionSeal,
    SecureVault,
    AuditLedger,
    IntegrityVerifier,
    ThreatArchive,
)

__version__ = "1.0.0"
__author__  = "The Ethos Aegis Project"
__all__ = [
    # Core pipeline
    "EthosAegis", "AegisVerdict", "Malignum", "MalignaClass", "CorruptionDepth",
    "SentinelCell", "CytokineCommand",
    # Seven Sentinel Cells
    "VanguardProbe", "LogosScythe", "MnemosyneCache", "SanitasSwarm",
    "EntropicWatch", "TaintBeacon", "FinalityForge",
    # Vitality protocol
    "AegisVitality", "VitalityReport", "VitalityLevel", "NutrientClass",
    "NutrientPlex", "KineticRegimen", "SomnaticCycle", "NeuroStressBuffer",
    "HematopoieticBoost", "ProbiomicBaseline", "VitalityMonitor",
    # Security vault
    "VaultKeeper", "SessionSeal", "SecureVault", "AuditLedger",
    "IntegrityVerifier", "ThreatArchive",
]
