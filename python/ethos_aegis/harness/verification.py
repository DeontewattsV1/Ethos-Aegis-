"""
harness/verification.py — Component 10: Verification loops.

Implements the Gather-Act-Verify cycle with three verification modes:
  1. Rules-based  — deterministic: tests, linters, type checkers
  2. LLM-as-judge — semantic: a separate evaluator prompt scores the output
  3. Visual        — screenshot/diff based (stub for UI tasks)

Boris Cherny finding: giving the model a way to verify its work improves
quality by 2–3x. This module makes that structural.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any, Callable, List, Optional

from .types import VerificationResult

_log = logging.getLogger("HarnessVerification")


class VerificationEngine:
    """
    Runs a configurable stack of verifiers over agent output.

    Verifiers are called in order. If any returns passed=False with
    score < 0.4 the engine short-circuits and returns that result
    so the orchestrator can re-run or surface the failure.
    """

    def __init__(self) -> None:
        self._rules:    List[Callable[[str], VerificationResult]] = []
        self._judges:   List[Callable[[str], VerificationResult]] = []

    # ── Registration ──────────────────────────────────────────────────────────

    def add_rules_verifier(self, fn: Callable[[str], VerificationResult]) -> None:
        """Register a deterministic rules-based verifier (linter, test runner, etc.)."""
        self._rules.append(fn)

    def add_llm_judge(self, fn: Callable[[str], VerificationResult]) -> None:
        """Register an LLM-as-judge verifier."""
        self._judges.append(fn)

    # ── Built-in verifiers ────────────────────────────────────────────────────

    @staticmethod
    def python_syntax_check(code: str) -> VerificationResult:
        """Rules-based: compile the output as Python and report any SyntaxError."""
        try:
            compile(code, "<harness_output>", "exec")
            return VerificationResult(passed=True, score=1.0,
                                      feedback="Python syntax OK", source="rules")
        except SyntaxError as e:
            return VerificationResult(passed=False, score=0.0,
                                      feedback=f"SyntaxError: {e}", source="rules")

    @staticmethod
    def shell_command_verifier(cmd: str, cwd: Optional[str] = None) -> VerificationResult:
        """
        Rules-based: run a shell command (e.g. `pytest -q`, `ruff check .`)
        and interpret exit code.
        """
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=60, cwd=cwd)
            passed = result.returncode == 0
            feedback = (result.stdout + result.stderr).strip()[:500]
            return VerificationResult(
                passed=passed,
                score=1.0 if passed else 0.0,
                feedback=feedback or ("OK" if passed else "non-zero exit"),
                source="rules",
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(passed=False, score=0.0,
                                      feedback="Verification timed out", source="rules")
        except Exception as exc:
            return VerificationResult(passed=False, score=0.0,
                                      feedback=str(exc), source="rules")

    # ── Verify ────────────────────────────────────────────────────────────────

    def verify(self, output: str) -> VerificationResult:
        """
        Run all registered verifiers.
        Returns the first failing result (fast-fail), or a composite pass.
        """
        all_results: List[VerificationResult] = []

        for fn in self._rules:
            r = fn(output)
            all_results.append(r)
            if not r.passed and r.score < 0.4:
                _log.info("Rules verifier FAILED: %s", r.feedback[:80])
                return r

        for fn in self._judges:
            r = fn(output)
            all_results.append(r)
            if not r.passed and r.score < 0.4:
                _log.info("LLM judge FAILED: %s", r.feedback[:80])
                return r

        avg_score = (sum(r.score for r in all_results) / len(all_results)
                     if all_results else 1.0)
        return VerificationResult(
            passed=True,
            score=avg_score,
            feedback=f"All {len(all_results)} verifier(s) passed",
            source="composite",
        )
