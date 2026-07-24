"""
harness/orchestrator.py — Components 1, 5, 11: The agent harness orchestration loop.

Implements the full 7-step TAO (Thought-Action-Observation) cycle:
  Step 1: Prompt assembly   (context manager + memory)
  Step 2: LLM inference     (via adapter)
  Step 3: Output parsing    (native tool_calls → ParsedOutput)
  Step 4: Tool execution    (registry, permission gate, parallel readonly)
  Step 5: Result packaging  (ToolResult → Message)
  Step 6: Context update    (append, compact if needed)
  Step 7: Loop              (repeat until termination)

Plus the Ralph Loop pattern for multi-session long-running tasks.

This is intentionally a "dumb loop" (Anthropic framing): all intelligence
lives in the model. The harness just manages turns.
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from .context      import ContextManager
from .errors       import ErrorCategory, HarnessError, ToolExecutionError, classify
from .guardrails   import GuardrailLayer, HarnessHalted
from .memory       import MemoryStore
from .output_parser import OutputParser, ParsedOutput
from .state        import CheckpointStore
from .tools        import ToolRegistry
from .types        import (
    HarnessConfig, HarnessState, Message, Role,
    TerminationReason, ToolCall, ToolResult,
)
from .verification  import VerificationEngine

_log = logging.getLogger("HarnessOrchestrator")


class AegisHarness:
    """
    The Ethos-Aegis Production Agent Harness.

    Wraps any LLM adapter with the full 12-component harness:
    orchestration loop, tools, memory, context management, state
    persistence, output parsing, error handling, guardrails,
    verification loops, and sub-agent support.

    Canonical formula (Vivek Trivedy / LangChain):
        "If you're not the model, you're the harness."

    Quick start:
        from ethos_aegis.harness import AegisHarness, HarnessConfig
        from ethos_aegis.agent.adapters.openai_adapter import OpenAIAdapter

        harness = AegisHarness(
            adapter=OpenAIAdapter(api_key="sk-..."),
            config=HarnessConfig(),
        )
        for event in harness.run("Refactor the auth module to use JWT"):
            print(event)
    """

    SYSTEM_PROMPT = """\
You are an Ethos-Aegis AI agent operating inside a production-grade harness.
You have access to a set of tools. Use them to accomplish the user's goal.
Think carefully before acting. Verify your work after each significant step.
When you are done, respond with your final answer — do NOT call any more tools.

## Harness contract
- Tool outputs are observations, not ground truth. Always verify.
- You are operating with a context budget. Be concise in reasoning.
- If a tool fails, adapt your approach rather than retrying identically.
- Architectural decisions and unresolved bugs should be noted explicitly
  so they survive context compaction.
"""

    def __init__(
        self,
        adapter,                              # Any BaseAdapter subclass
        config:        Optional[HarnessConfig] = None,
        aegis          = None,                # EthosAegis instance for guardrails
        checkpoint_dir: Optional[Path] = None,
        memory_path:    Optional[Path] = None,
    ) -> None:
        self._adapter     = adapter
        self._config      = config or HarnessConfig()
        self._tools       = ToolRegistry(self._config)
        self._memory      = MemoryStore(memory_path)
        self._context     = ContextManager(self._config, summarise_fn=self._extractive_summary)
        self._parser      = OutputParser()
        self._guardrails  = GuardrailLayer(self._config, aegis)
        self._verifier    = VerificationEngine()
        self._checkpoints = CheckpointStore(checkpoint_dir or Path("/tmp/aegis_checkpoints"))

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def verifier(self) -> VerificationEngine:
        return self._verifier

    def run(self, goal: str, session_id: Optional[str] = None,
            approval_fn: Optional[Callable[[ToolCall], bool]] = None
            ) -> Generator[Dict[str, Any], None, None]:
        """
        Execute the agent loop for a given goal.

        Yields event dicts at each step so callers can stream output:
          {"type": "turn_start", "turn": N}
          {"type": "tool_calls", "calls": [...]}
          {"type": "tool_results", "results": [...]}
          {"type": "final_answer", "content": "..."}
          {"type": "terminated", "reason": "..."}
        """
        sid = session_id or str(uuid.uuid4())[:8]

        # Try to resume from checkpoint (Ralph Loop)
        state = self._checkpoints.load_latest(sid)
        if state and not state.terminated:
            _log.info("Resuming session %s at turn %d", sid, state.turns)
        else:
            state = HarnessState(session_id=sid, goal=goal)

        # ── Step 1 (initial): Input guardrail ─────────────────────────────────
        gv = self._guardrails.check_input(goal)
        if gv.tripwire:
            state.terminated  = True
            state.term_reason = TerminationReason.GUARDRAIL
            yield {"type": "terminated", "reason": gv.reason}
            return

        # Seed user message
        state.messages.append(Message(Role.USER, goal))

        # ── TAO Loop ──────────────────────────────────────────────────────────
        while not state.terminated:
            state.turns += 1
            yield {"type": "turn_start", "turn": state.turns}

            # Termination guards
            if state.turns > self._config.max_turns:
                state.terminated  = True
                state.term_reason = TerminationReason.MAX_TURNS
                break
            if state.tokens_used > self._config.token_budget:
                state.terminated  = True
                state.term_reason = TerminationReason.TOKEN_BUDGET
                break

            # ── Step 1: Prompt assembly ───────────────────────────────────────
            system_block, trimmed_history = self._context.assemble(
                system_prompt=self.SYSTEM_PROMPT,
                tool_schemas=self._tools.schemas_for_context(),
                memory_index=self._memory.index_snapshot(),
                history=state.messages[:-1],   # exclude latest user msg
                user_message=goal,
            )
            token_est = self._context.estimate_tokens(system_block, trimmed_history)
            state.tokens_used += token_est

            # ── Step 2: LLM inference ─────────────────────────────────────────
            try:
                raw_response = self._adapter.complete(
                    system=system_block,
                    messages=trimmed_history + [state.messages[-1]],
                )
            except Exception as exc:
                cat = classify(exc)
                if cat == ErrorCategory.TRANSIENT and state.turns <= self._config.max_turns:
                    _log.warning("Transient LLM error, retrying: %s", exc)
                    time.sleep(1.0)
                    continue
                state.terminated  = True
                state.term_reason = TerminationReason.ERROR
                yield {"type": "terminated", "reason": str(exc)}
                return

            # ── Step 3: Output parsing ────────────────────────────────────────
            parsed: ParsedOutput = self._parser.parse(raw_response)

            # Handle sub-agent handoff
            if parsed.handoff_to:
                _log.info("Handoff requested to sub-agent: %s", parsed.handoff_to)
                state.scratchpad["handoff_to"] = parsed.handoff_to
                state.terminated  = True
                state.term_reason = TerminationReason.FINAL_ANSWER
                break

            # Final answer path (no tool calls)
            if parsed.final_answer is not None:
                # ── Output guardrail ──────────────────────────────────────────
                ogv = self._guardrails.check_output(parsed.final_answer)
                if ogv.tripwire:
                    state.terminated  = True
                    state.term_reason = TerminationReason.GUARDRAIL
                    yield {"type": "terminated", "reason": ogv.reason}
                    return

                # ── Verification ──────────────────────────────────────────────
                if self._config.verify_outputs:
                    vr = self._verifier.verify(parsed.final_answer)
                    if not vr.passed:
                        _log.info("Verification failed (score=%.2f): %s", vr.score, vr.feedback)
                        # Feed back to model for self-correction (one retry)
                        correction_msg = (f"Your answer did not pass verification:\n{vr.feedback}\n"
                                          f"Please correct and try again.")
                        state.messages.append(Message(Role.ASSISTANT, parsed.raw_text))
                        state.messages.append(Message(Role.USER, correction_msg))
                        continue

                state.messages.append(Message(Role.ASSISTANT, parsed.final_answer))
                yield {"type": "final_answer", "content": parsed.final_answer}
                state.terminated  = True
                state.term_reason = TerminationReason.FINAL_ANSWER
                break

            # ── Step 4: Tool execution ────────────────────────────────────────
            yield {"type": "tool_calls", "calls": [
                {"name": c.tool_name, "args": c.arguments} for c in parsed.tool_calls
            ]}

            # Tool guardrails (every call)
            approved_calls = []
            for call in parsed.tool_calls:
                tgv = self._guardrails.check_tool_call(call)
                if tgv.tripwire:
                    state.terminated  = True
                    state.term_reason = TerminationReason.GUARDRAIL
                    yield {"type": "terminated", "reason": tgv.reason}
                    return
                if tgv.passed:
                    approved_calls.append(call)

            results: List[ToolResult] = self._tools.execute_batch(
                approved_calls, approval_fn=approval_fn
            )
            yield {"type": "tool_results", "results": [
                {"name": r.tool_name, "error": r.is_error, "output": r.output[:200]}
                for r in results
            ]}

            # ── Step 5: Package results as messages ───────────────────────────
            state.messages.append(Message(Role.ASSISTANT, parsed.raw_text))
            for r in results:
                state.messages.append(Message(
                    role=Role.TOOL,
                    content=r.output if not r.is_error else f"ERROR: {r.output}",
                    tool_name=r.tool_name,
                    tool_call_id=r.tool_call_id,
                ))

            # ── Step 6: Checkpoint ────────────────────────────────────────────
            self._checkpoints.save(state)

        # Loop exited
        self._checkpoints.save(state)
        reason = state.term_reason.value if state.term_reason else "unknown"
        _log.info("Session %s terminated: %s after %d turns", sid, reason, state.turns)
        yield {"type": "terminated", "reason": reason, "turns": state.turns}

    # ── Subagent support ──────────────────────────────────────────────────────

    def spawn_subagent(self, goal: str, max_turns: int = 10,
                       summary_limit: int = 1500) -> str:
        """
        Spawn a sub-agent for a bounded subtask and return a condensed
        1k–2k token summary (Anthropic sub-agent delegation pattern).
        """
        sub_config = HarnessConfig(
            max_turns=max_turns,
            verify_outputs=False,
            token_budget=self._config.token_budget // 4,
        )
        sub = AegisHarness(
            adapter=self._adapter,
            config=sub_config,
            checkpoint_dir=self._checkpoints._root / "subagents",
        )
        # Share parent tool registry
        sub._tools = self._tools

        events = list(sub.run(goal))
        final  = next((e["content"] for e in events if e["type"] == "final_answer"), "")
        # Condense to summary_limit chars
        if len(final) > summary_limit:
            final = final[:summary_limit] + f"\n…[truncated, {len(final)} chars total]"
        return final

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extractive_summary(self, messages: List[Message]) -> str:
        """Lightweight extractive fallback — first line of each assistant turn."""
        lines = []
        for m in messages:
            if m.role == Role.ASSISTANT:
                lines.append("• " + m.content.split("\n")[0][:120])
        return "\n".join(lines) if lines else "(empty)"
