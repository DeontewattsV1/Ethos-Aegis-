"""
harness/context.py — Component 4: Context management & compaction.

Implements the five production strategies from the deep-dive:
  1. Compaction (summarise when approaching limit)
  2. Observation masking (hide old tool outputs, keep tool calls visible)
  3. Just-in-time retrieval (lightweight identifiers, load on demand)
  4. Sub-agent delegation (1k–2k token condensed summaries)
  5. Priority positioning (important context at front and end of window)

Also implements the "Lost in the Middle" mitigation: high-signal tokens
are placed at the START and END of the assembled prompt, never mid-window.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional, Tuple

from .types import Message, Role, HarnessConfig

_log = logging.getLogger("HarnessContext")

# Rough token estimator: 1 token ≈ 4 chars (GPT-style)
def _token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


class ContextManager:
    """
    Manages what the model sees at each turn.

    Applies observation masking, compaction, and priority positioning to
    keep the active context under `config.context_limit` tokens while
    preserving the highest-signal information.
    """

    def __init__(self, config: HarnessConfig,
                 summarise_fn: Optional[Callable[[List[Message]], str]] = None) -> None:
        self._config      = config
        self._summarise   = summarise_fn   # injected by Orchestrator (avoids circular dep)
        self._compaction_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def assemble(self,
                 system_prompt: str,
                 tool_schemas:  List[dict],
                 memory_index:  dict,
                 history:       List[Message],
                 user_message:  str) -> Tuple[str, List[Message]]:
        """
        Build the full prompt, applying context budget management.

        Returns (system_block, trimmed_history) — the caller is responsible
        for serialising this into the provider-specific API format.

        Priority stack (highest → lowest):
          1. System prompt (always at front)
          2. Tool schemas (injected into system block)
          3. Memory index snapshot (lightweight, always present)
          4. Earliest messages (anchor context)
          5. Most-recent messages (recency)
          6. Middle messages (masked if budget exceeded)
        """
        history = self._mask_old_tool_outputs(history)
        history = self._compact_if_needed(history)
        system_block = self._build_system_block(system_prompt, tool_schemas, memory_index)
        return system_block, history

    def estimate_tokens(self, system_block: str, history: List[Message]) -> int:
        total = _token_estimate(system_block)
        for m in history:
            total += _token_estimate(m.content)
        return total

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_system_block(self, system_prompt: str,
                             tool_schemas: List[dict],
                             memory_index: dict) -> str:
        parts = [system_prompt.strip()]
        if memory_index:
            lines = "\n".join(f"  {k}: {v}" for k, v in memory_index.items())
            parts.append(f"\n## Working Memory\n{lines}")
        if tool_schemas:
            import json
            parts.append(f"\n## Available Tools\n{json.dumps(tool_schemas, indent=2)}")
        return "\n".join(parts)

    def _mask_old_tool_outputs(self, history: List[Message]) -> List[Message]:
        """
        JetBrains Junie strategy: hide old tool *outputs* while keeping
        tool *calls* visible. Reduces noise without losing the action trail.
        Only mask outputs older than the last 6 messages.
        """
        if len(history) <= 6:
            return history
        cutoff = len(history) - 6
        masked = []
        for i, msg in enumerate(history):
            if i < cutoff and msg.role == Role.TOOL:
                masked.append(Message(
                    role=msg.role,
                    content="[output masked for context efficiency]",
                    tool_name=msg.tool_name,
                    tool_call_id=msg.tool_call_id,
                ))
            else:
                masked.append(msg)
        return masked

    def _compact_if_needed(self, history: List[Message]) -> List[Message]:
        """
        Compaction: summarise middle history when approaching the context limit.
        Preserves: first 2 messages (anchor), last 6 messages (recency),
        architectural decisions and unresolved bugs (keyword scan).
        Everything else is summarised into a single SYSTEM message.
        """
        total_chars = sum(len(m.content) for m in history)
        budget_chars = self._config.context_limit * 4   # chars ≈ tokens * 4
        if total_chars <= budget_chars * 0.85:
            return history

        _log.info("Context at %.0f%% of limit — compacting",
                  100 * total_chars / budget_chars)

        anchor   = history[:2]
        recent   = history[-6:]
        middle   = history[2:-6]

        # Preserve high-signal middle messages (architectural decisions, bugs)
        keep_keywords = {"decided", "architecture", "bug", "unresolved",
                         "TODO", "FIXME", "important", "critical"}
        preserved = [m for m in middle
                     if any(kw.lower() in m.content.lower() for kw in keep_keywords)]

        # Summarise the rest
        to_summarise = [m for m in middle if m not in preserved]
        summary_text = self._do_summarise(to_summarise)

        compacted = (anchor
                     + [Message(Role.SYSTEM, f"[Compacted history — {self._compaction_count+1}]\n{summary_text}")]
                     + preserved
                     + recent)
        self._compaction_count += 1
        _log.info("Compacted %d messages → 1 summary block", len(to_summarise))
        return compacted

    def _do_summarise(self, messages: List[Message]) -> str:
        if not messages:
            return "(no content)"
        if self._summarise:
            return self._summarise(messages)
        # Fallback: extractive summary (first sentence of each assistant turn)
        lines = []
        for m in messages:
            if m.role == Role.ASSISTANT:
                first_line = m.content.split("\n")[0][:120]
                lines.append(f"• {first_line}")
        return "\n".join(lines) if lines else f"({len(messages)} messages omitted)"
