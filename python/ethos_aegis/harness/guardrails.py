"""
harness/guardrails.py — Component 9: Three-level guardrail system + tripwire.

Implements OpenAI's three-level model:
  - Input guardrails  (run on first agent, before any tool calls)
  - Output guardrails (run on final answer)
  - Tool guardrails   (run on every tool invocation)

Integrates with Ethos-Aegis's own EthosAegis adjudication pipeline so every
input/output passes through the immune system.  The tripwire fires immediately
on CONDEMNED verdicts, halting the agent loop.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .types import ToolCall, ToolResult, HarnessConfig

_log = logging.getLogger("HarnessGuardrails")


@dataclass
class GuardrailVerdict:
    passed:   bool
    reason:   str
    tripwire: bool = False    # True → halt agent immediately


class GuardrailLayer:
    """
    Three-level guardrail gate integrated with the Aegis immune system.

    Usage:
        gl = GuardrailLayer(config, aegis_instance)
        v = gl.check_input(user_message)
        if v.tripwire: raise HarnessHalted(v.reason)
    """

    def __init__(self, config: HarnessConfig, aegis=None) -> None:
        self._config = config
        self._aegis  = aegis   # EthosAegis instance (optional, injected at runtime)

    # ── Level 1: Input guardrail ──────────────────────────────────────────────

    def check_input(self, text: str) -> GuardrailVerdict:
        """Run on the user message before any LLM call."""
        return self._run_aegis(text, stage="input")

    # ── Level 2: Output guardrail ─────────────────────────────────────────────

    def check_output(self, text: str) -> GuardrailVerdict:
        """Run on the model's final answer before returning it to the user."""
        return self._run_aegis(text, stage="output")

    # ── Level 3: Tool guardrail ───────────────────────────────────────────────

    def check_tool_call(self, call: ToolCall) -> GuardrailVerdict:
        """Run on every tool invocation argument string."""
        import json
        payload = json.dumps(call.arguments, default=str)
        verdict = self._run_aegis(payload, stage="tool")
        if not verdict.passed:
            _log.warning("Tool guardrail blocked: %s — %s", call.tool_name, verdict.reason)
        return verdict

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_aegis(self, text: str, stage: str) -> GuardrailVerdict:
        if self._aegis is None:
            return GuardrailVerdict(passed=True, reason="no aegis (pass-through)")
        try:
            from ethos_aegis.core.aegis import CorruptionDepth
            verdict = self._aegis.adjudicate(text)
            depth   = verdict.sovereignty_depth

            if depth == CorruptionDepth.CONDEMNED:
                return GuardrailVerdict(
                    passed=False,
                    reason=f"[{stage}] CONDEMNED by Aegis: {verdict.axiological_report[:120]}",
                    tripwire=True,
                )
            if depth == CorruptionDepth.GRAVE:
                return GuardrailVerdict(
                    passed=False,
                    reason=f"[{stage}] GRAVE risk detected — blocked for safety",
                    tripwire=False,
                )
            return GuardrailVerdict(passed=True, reason=f"[{stage}] cleared (depth={depth.name})")
        except Exception as exc:
            _log.error("Aegis adjudication error at %s stage: %s", stage, exc)
            return GuardrailVerdict(passed=True, reason=f"[{stage}] aegis error (fail-open): {exc}")


class HarnessHalted(RuntimeError):
    """Raised when a tripwire fires and the agent loop must stop immediately."""
    pass
