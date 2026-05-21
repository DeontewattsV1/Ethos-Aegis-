from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Mapping

from .ckan_adapter import CKANCapabilityMatrix, SchemaField
from .law_engine import FormulaCandidate, UniversalVeriflowLaw


_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: safe_div(a, b),
    ast.Pow: lambda a, b: a ** b,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}
_ALLOWED_CALLS = {
    "abs": abs,
    "sqrt": math.sqrt,
    "log": lambda x: math.log(max(x, 1e-12)),
    "safe_div": lambda a, b: safe_div(a, b),
}
_NUMERIC_HINTS = {
    "int", "integer", "float", "double", "decimal", "numeric", "number", "real", "bigint", "smallint"
}
_RATE_HINTS = {"rate", "ratio", "percent", "percentage", "share", "fraction", "ctr", "conversion"}


def safe_div(a: float, b: float, epsilon: float = 1e-9) -> float:
    if abs(b) <= epsilon:
        return math.nan
    return a / b


@dataclass(slots=True, frozen=True)
class FormulaGenerationProfile:
    mode: str = "baseline"
    trust_schema_metadata: bool = False
    prefer_typed_numeric_features: bool = False
    prefer_ratio_candidates: bool = False
    include_provenance: bool = False


class SafeExpressionEvaluator(ast.NodeVisitor):
    def __init__(self, environment: Mapping[str, float]) -> None:
        self.environment = environment

    def visit_Expression(self, node: ast.Expression) -> float:
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> float:
        if node.id not in self.environment:
            raise KeyError(node.id)
        return float(self.environment[node.id])

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise TypeError("Only numeric constants are allowed.")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise TypeError("Unsupported unary operator.")
        return op(self.visit(node.operand))

    def visit_BinOp(self, node: ast.BinOp) -> float:
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise TypeError("Unsupported binary operator.")
        return op(self.visit(node.left), self.visit(node.right))

    def visit_Call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name):
            raise TypeError("Only simple function calls are allowed.")
        func = _ALLOWED_CALLS.get(node.func.id)
        if func is None:
            raise TypeError("Unsupported function call.")
        args = [self.visit(arg) for arg in node.args]
        return float(func(*args))

    def generic_visit(self, node: ast.AST) -> float:
        raise TypeError(f"Unsupported AST node: {node.__class__.__name__}")


class FormulaForge:
    def __init__(self, law: UniversalVeriflowLaw | None = None) -> None:
        self.law = law or UniversalVeriflowLaw()

    def profile_from_capabilities(self, capability_matrix: CKANCapabilityMatrix | None) -> FormulaGenerationProfile:
        if capability_matrix is None:
            return FormulaGenerationProfile()
        schema_rich = capability_matrix.supports("scheming") or capability_matrix.supports("table_designer")
        datastore_ready = capability_matrix.supports("datastore")
        include_provenance = capability_matrix.supports("dcat")
        mode_bits = []
        if schema_rich:
            mode_bits.append("schema-rich")
        if datastore_ready:
            mode_bits.append("datastore")
        if include_provenance:
            mode_bits.append("dcat")
        return FormulaGenerationProfile(
            mode="+".join(mode_bits) or "baseline",
            trust_schema_metadata=schema_rich,
            prefer_typed_numeric_features=schema_rich,
            prefer_ratio_candidates=datastore_ready or schema_rich,
            include_provenance=include_provenance,
        )

    def discover_best_formula(
        self,
        rows: list[Mapping[str, Any]],
        target_field: str,
        feature_fields: list[str],
        *,
        question: str = "",
        fields: list[SchemaField] | None = None,
        capability_matrix: CKANCapabilityMatrix | None = None,
    ) -> FormulaCandidate:
        profile = self.profile_from_capabilities(capability_matrix)
        field_map = {field.name: field for field in (fields or [])}
        candidates = []
        eligible_features = self._eligible_feature_fields(feature_fields, field_map, profile)
        rate_question = self._is_rate_question(question, field_map.get(target_field))

        for feature in eligible_features:
            if feature == target_field:
                continue
            fit = self._single_feature_linear_fit(rows, feature, target_field)
            expr = str(fit["expression"])
            linear_complexity = 0.15 if profile.prefer_typed_numeric_features else 0.2
            candidates.append(self.law.score_candidate(
                expression=expr,
                features=[feature],
                fit=float(fit["fit"]),
                coverage=float(fit["coverage"]),
                complexity=linear_complexity,
                stability=float(fit["stability"]),
                question=question,
                fields=fields or [],
            ))

            if not profile.prefer_ratio_candidates and not rate_question:
                continue

            for other in eligible_features:
                if other in {feature, target_field}:
                    continue
                expr = f"safe_div({feature}, {other})"
                score = self.score_expression(expr, rows, target_field)
                ratio_complexity = 0.18 if rate_question else 0.3
                if profile.prefer_ratio_candidates:
                    ratio_complexity -= 0.05
                candidates.append(self.law.score_candidate(
                    expression=expr,
                    features=[feature, other],
                    fit=score["fit"],
                    coverage=score["coverage"],
                    complexity=max(0.05, ratio_complexity),
                    stability=score["stability"],
                    question=question,
                    fields=fields or [],
                ))
        if not candidates:
            raise ValueError("No candidate formulas could be generated.")
        return max(candidates, key=lambda candidate: candidate.score)

    def score_expression(self, expression: str, rows: list[Mapping[str, Any]], target_field: str) -> dict[str, float]:
        parsed = ast.parse(expression, mode="eval")
        total_error = 0.0
        predicted = []
        actual = []
        valid_rows = 0
        for row in rows:
            try:
                prediction = SafeExpressionEvaluator(row).visit(parsed)
                truth = float(row[target_field])
            except Exception:
                continue
            if math.isnan(prediction) or math.isinf(prediction):
                continue
            predicted.append(prediction)
            actual.append(truth)
            total_error += abs(prediction - truth)
            valid_rows += 1
        if valid_rows == 0:
            return {"score": 0.0, "fit": 0.0, "coverage": 0.0, "stability": 0.0}
        mae = total_error / valid_rows
        span = max(max(actual) - min(actual), 1.0)
        fit = max(0.0, 1.0 - mae / span)
        stability = 1.0 - min(1.0, self._std(predicted) / max(1.0, abs(mean(predicted))))
        coverage = valid_rows / max(1, len(rows))
        score = 0.7 * fit + 0.3 * coverage
        return {"score": score, "fit": fit, "coverage": coverage, "stability": max(0.0, stability)}

    def _single_feature_linear_fit(self, rows: list[Mapping[str, Any]], feature: str, target: str) -> dict[str, float | str]:
        points = []
        for row in rows:
            try:
                x = float(row[feature])
                y = float(row[target])
            except Exception:
                continue
            points.append((x, y))
        if len(points) < 2:
            return {"expression": feature, "fit": 0.0, "coverage": 0.0, "stability": 0.0}
        n = len(points)
        sum_x = sum(x for x, _ in points)
        sum_y = sum(y for _, y in points)
        sum_xx = sum(x * x for x, _ in points)
        sum_xy = sum(x * y for x, y in points)
        denominator = n * sum_xx - sum_x ** 2
        if abs(denominator) < 1e-9:
            return {"expression": feature, "fit": 0.0, "coverage": n / max(1, len(rows)), "stability": 0.0}
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        expr = f"({slope:.6f} * {feature}) + ({intercept:.6f})"
        score = self.score_expression(expr, rows, target)
        return {"expression": expr, "fit": score["fit"], "coverage": score["coverage"], "stability": score["stability"]}

    def _eligible_feature_fields(
        self,
        feature_fields: list[str],
        field_map: Mapping[str, SchemaField],
        profile: FormulaGenerationProfile,
    ) -> list[str]:
        if not profile.prefer_typed_numeric_features:
            return feature_fields
        typed = [name for name in feature_fields if self._field_is_numeric(field_map.get(name))]
        return typed or feature_fields

    def _field_is_numeric(self, field: SchemaField | None) -> bool:
        if field is None:
            return False
        if field.field_type and field.field_type.lower() in _NUMERIC_HINTS:
            return True
        text = field.searchable_text()
        return any(token in text for token in {"count", "amount", "total", "number", "value"})

    def _is_rate_question(self, question: str, target_field: SchemaField | None) -> bool:
        lowered = question.lower()
        tokens = {token for token in lowered.replace("?", " ").split() if len(token) > 2}
        if tokens & _RATE_HINTS:
            return True
        if target_field is None:
            return False
        target_text = target_field.searchable_text()
        return any(token in target_text for token in _RATE_HINTS)

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
        return math.sqrt(variance)
