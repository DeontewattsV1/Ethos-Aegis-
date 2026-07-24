"""
harness/output_parser.py — Component 6: Output parsing & structured extraction.

Modern harnesses rely on native tool calling (model returns structured
tool_calls objects). This module handles:
  - Native structured tool_calls → ToolCall dataclasses
  - Pydantic-schema-constrained structured outputs
  - Legacy free-text ReAct parsing (THOUGHT/ACTION/OBSERVATION pattern)
  - RetryWithErrorOutputParser fallback
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .types import ToolCall

_log = logging.getLogger("HarnessOutputParser")


@dataclass
class ParsedOutput:
    tool_calls:    List[ToolCall]
    final_answer:  Optional[str]   # non-None → loop should terminate
    raw_text:      str
    handoff_to:    Optional[str]   # non-None → delegate to named sub-agent


class OutputParser:
    """
    Parse LLM output into structured harness actions.

    Priority:
      1. Native tool_calls dict (OpenAI / Anthropic format)
      2. Pydantic-constrained JSON block
      3. ReAct free-text pattern (legacy fallback)
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, raw: Any) -> ParsedOutput:
        """
        `raw` can be:
          - A dict  with 'content' + optional 'tool_calls' (OpenAI response format)
          - A str   (plain text — use ReAct pattern matching)
        """
        if isinstance(raw, dict):
            return self._parse_native(raw)
        return self._parse_text(str(raw))

    # ── Native tool_calls ─────────────────────────────────────────────────────

    def _parse_native(self, response: Dict[str, Any]) -> ParsedOutput:
        tool_calls: List[ToolCall] = []
        raw_text    = response.get("content", "") or ""
        handoff_to  = response.get("handoff_to")

        for tc in response.get("tool_calls", []):
            try:
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"tc_{len(tool_calls)}"),
                    tool_name=tc["name"],
                    arguments=args,
                ))
            except (KeyError, json.JSONDecodeError) as exc:
                _log.warning("Malformed tool_call entry skipped: %s", exc)

        final = raw_text if not tool_calls and not handoff_to else None
        return ParsedOutput(tool_calls=tool_calls, final_answer=final,
                            raw_text=raw_text, handoff_to=handoff_to)

    # ── ReAct text pattern (legacy) ───────────────────────────────────────────

    _ACTION_RE  = re.compile(r"Action:\s*(\w+)\s*\nAction Input:\s*(.+?)(?=\nObservation:|\Z)",
                              re.DOTALL | re.IGNORECASE)
    _FINAL_RE   = re.compile(r"Final Answer:\s*(.+)", re.DOTALL | re.IGNORECASE)

    def _parse_text(self, text: str) -> ParsedOutput:
        # Check for Final Answer first
        fm = self._FINAL_RE.search(text)
        if fm:
            return ParsedOutput(tool_calls=[], final_answer=fm.group(1).strip(),
                                raw_text=text, handoff_to=None)

        # Try JSON block (Pydantic-constrained structured output)
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "tool_calls" in data or "tool_name" in data:
                    return self._parse_native(data)
            except json.JSONDecodeError:
                pass

        # ReAct pattern
        calls = []
        for m in self._ACTION_RE.finditer(text):
            tool_name  = m.group(1).strip()
            raw_input  = m.group(2).strip()
            try:
                args = json.loads(raw_input)
            except json.JSONDecodeError:
                args = {"input": raw_input}
            calls.append(ToolCall(
                id=f"react_{len(calls)}",
                tool_name=tool_name,
                arguments=args,
            ))

        if calls:
            return ParsedOutput(tool_calls=calls, final_answer=None,
                                raw_text=text, handoff_to=None)

        # Nothing matched → treat the whole response as a final answer
        return ParsedOutput(tool_calls=[], final_answer=text,
                            raw_text=text, handoff_to=None)

    # ── Retry-with-error parser ───────────────────────────────────────────────

    def retry_parse(self, original_prompt: str, failed_output: str,
                    parse_error: str) -> str:
        """
        Construct a follow-up prompt that feeds the original prompt,
        the failed completion, and the parsing error back to the model
        (LangChain's RetryWithErrorOutputParser pattern).
        """
        return (
            f"{original_prompt}\n\n"
            f"Your previous response could not be parsed:\n"
            f"---\n{failed_output}\n---\n"
            f"Parse error: {parse_error}\n\n"
            f"Please respond again following the required format exactly."
        )
