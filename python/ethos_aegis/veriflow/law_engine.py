from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ckan_adapter import SchemaField


@dataclass(slots=True, frozen=True)
class FormulaCandidate:
    expression: str
    features: list[str]
    fit: float
    coverage: float
    semantics: float
    stability: float
    complexity: float
    score: float
    explanation: str


class UniversalVeriflowLaw:
    """Lightweight scoring law for candidate formulas.

    This package snapshot only needs a deterministic, portable candidate scorer.
    """

    def score_candidate(
        self,
        *,
        expression: str,
        features: list[str],
        fit: float,
        coverage: float,
        complexity: float,
        stability: float,
        question: str,
        fields: Iterable[SchemaField],
    ) -> FormulaCandidate:
        semantics = self._semantic_alignment(features, question, fields)
        score = (
            0.40 * fit
            + 0.25 * semantics
            + 0.20 * coverage
            + 0.15 * stability
            - 0.10 * complexity
        )
        explanation = (
            f"Selected {expression} from features {features} with fit={fit:.3f}, "
            f"semantics={semantics:.3f}, coverage={coverage:.3f}, stability={stability:.3f}."
        )
        return FormulaCandidate(
            expression=expression,
            features=list(features),
            fit=float(fit),
            coverage=float(coverage),
            semantics=float(semantics),
            stability=float(stability),
            complexity=float(complexity),
            score=float(score),
            explanation=explanation,
        )

    def _semantic_alignment(self, features: list[str], question: str, fields: Iterable[SchemaField]) -> float:
        q_tokens = {token for token in question.lower().replace("?", " ").split() if len(token) > 2}
        if not q_tokens:
            return 0.5
        searchable = {field.name: field.searchable_text() for field in fields}
        feature_hits = 0
        possible_hits = max(1, len(features))
        for feature in features:
            text = searchable.get(feature, feature.lower())
            if q_tokens & set(text.split()):
                feature_hits += 1
        return min(1.0, feature_hits / possible_hits)
