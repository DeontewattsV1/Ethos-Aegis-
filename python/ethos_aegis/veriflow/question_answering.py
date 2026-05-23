from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping

from .ckan_adapter import CKANCapabilityMatrix, SchemaField
from .formula_forge import FormulaForge


class SchemaResolver:
    def resolve(
        self,
        question: str,
        fields: Iterable[SchemaField],
        top_k: int = 3,
        capability_matrix: CKANCapabilityMatrix | None = None,
    ) -> list[SchemaField]:
        q_tokens = {token for token in question.lower().replace("?", " ").split() if len(token) > 2}
        scored = []
        schema_rich = bool(capability_matrix and (capability_matrix.supports("scheming") or capability_matrix.supports("table_designer")))
        for field in fields:
            searchable = set(self._search_tokens(field, schema_rich=schema_rich))
            overlap = len(q_tokens & searchable)
            if overlap:
                scored.append((overlap, field))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [field for _, field in scored[:top_k]]

    def _search_tokens(self, field: SchemaField, *, schema_rich: bool) -> list[str]:
        if schema_rich:
            text = field.searchable_text()
        else:
            text = " ".join(part for part in [field.name, field.label or ""] if part)
        return [token for token in text.lower().replace("/", " ").split() if token]


@dataclass(slots=True)
class AnswerRecord:
    question: str
    answer_type: str
    value: Any
    evidence: dict[str, Any]


class VeriflowReasoner:
    def __init__(self, resolver: SchemaResolver | None = None, forge: FormulaForge | None = None) -> None:
        self.resolver = resolver or SchemaResolver()
        self.forge = forge or FormulaForge()

    def answer(
        self,
        question: str,
        rows: list[Mapping[str, Any]],
        fields: list[SchemaField],
        *,
        target_field: str | None = None,
        capability_matrix: CKANCapabilityMatrix | None = None,
    ) -> AnswerRecord:
        lowered = question.lower()
        resolved = self.resolver.resolve(question, fields, capability_matrix=capability_matrix)
        target = target_field or (resolved[0].name if resolved else None)
        if target is None:
            raise ValueError("Unable to resolve a target field from the question.")

        capability_context = self._capability_context(capability_matrix)

        if any(word in lowered for word in ("average", "mean")):
            values = [float(row[target]) for row in rows if target in row]
            return AnswerRecord(question, "aggregate_mean", mean(values), {"field": target, "count": len(values), **capability_context})

        if any(word in lowered for word in ("sum", "total")):
            values = [float(row[target]) for row in rows if target in row]
            return AnswerRecord(question, "aggregate_sum", sum(values), {"field": target, "count": len(values), **capability_context})

        if "count" in lowered:
            return AnswerRecord(question, "aggregate_count", len(rows), {"field": target, **capability_context})

        feature_fields = [field.name for field in fields if field.name != target]
        formula = self.forge.discover_best_formula(
            rows=rows,
            target_field=target,
            feature_fields=feature_fields,
            question=question,
            fields=fields,
            capability_matrix=capability_matrix,
        )
        return AnswerRecord(
            question,
            "formula",
            formula.expression,
            {
                "target": target,
                "score": formula.score,
                "fit": formula.fit,
                "coverage": formula.coverage,
                "semantics": formula.semantics,
                "features": formula.features,
                "explanation": formula.explanation,
                **capability_context,
            },
        )

    def _capability_context(self, capability_matrix: CKANCapabilityMatrix | None) -> dict[str, Any]:
        if capability_matrix is None:
            return {"host_profile": "baseline", "capabilities": {}}
        return {
            "host_profile": self.forge.profile_from_capabilities(capability_matrix).mode,
            "capabilities": {
                name: record.state for name, record in capability_matrix.capabilities.items()
            },
            "ckan_version": capability_matrix.version.raw,
        }
