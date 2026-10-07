"""VeriFlow: schema-aware reasoning, dataset fingerprints and Boolean rules."""

from .ckan_adapter import CKANClient, SchemaField
from .immune_system import DatasetCacheEntry, VeriflowImmuneSystem
from .law_engine import FormulaCandidate, UniversalVeriflowLaw
from .logic_laws import And, BoolConst, Expr, F, Not, Or, Symbol, T, simplify
from .question_answering import AnswerRecord, SchemaResolver, VeriflowReasoner

__all__ = [
    "CKANClient",
    "SchemaField",
    "DatasetCacheEntry",
    "VeriflowImmuneSystem",
    "FormulaCandidate",
    "UniversalVeriflowLaw",
    "F",
    "T",
    "And",
    "BoolConst",
    "Expr",
    "Not",
    "Or",
    "Symbol",
    "simplify",
    "AnswerRecord",
    "SchemaResolver",
    "VeriflowReasoner",
]
