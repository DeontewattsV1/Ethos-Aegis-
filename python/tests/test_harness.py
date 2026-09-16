"""
tests/test_harness.py — Unit tests for the 12-component AegisHarness.

Covers all components without requiring a live LLM:
  - memory tiers and persistence
  - tool registry, parallel execution, error capture
  - context compaction and observation masking
  - output parser (native, ReAct, final-answer)
  - state checkpointing and Ralph Loop progress
  - guardrail tripwire (no aegis = pass-through)
  - verification engine (rules + shell command)
  - full orchestrator loop with a mock adapter
"""
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from ethos_aegis.harness import (
    AegisHarness, HarnessConfig, Message, Role,
    MemoryStore, ToolRegistry, tool,
    ContextManager, OutputParser,
    CheckpointStore, HarnessState,
    GuardrailLayer, VerificationEngine,
    ToolCall, ToolResult, ToolSchema,
)
from ethos_aegis.harness.errors import ErrorCategory, classify, ToolExecutionError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class MockAdapter:
    """Fake LLM adapter that returns a configurable sequence of responses."""
    def __init__(self, responses: List[Any]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def complete(self, system: str, messages: list) -> Any:
        if self._idx >= len(self._responses):
            return {"content": "No more responses", "tool_calls": []}
        r = self._responses[self._idx]
        self._idx += 1
        return r


def _make_config(**kw) -> HarnessConfig:
    defaults = dict(max_turns=10, token_budget=50_000,
                    context_limit=40_000, max_tool_retries=1,
                    verify_outputs=False, parallel_readonly=False)
    defaults.update(kw)
    return HarnessConfig(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Memory
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryStore(unittest.TestCase):

    def test_index_tier_roundtrip(self):
        m = MemoryStore()
        m.remember("goal", "fix the bug", tier="index")
        snap = m.index_snapshot()
        self.assertEqual(snap["goal"], "fix the bug")

    def test_detail_tier_recalled_on_demand(self):
        m = MemoryStore()
        m.remember("spec", "A" * 500, tier="detail")
        self.assertNotIn("spec", m.index_snapshot())
        self.assertEqual(m.recall("spec"), "A" * 500)

    def test_transcript_search(self):
        m = MemoryStore()
        m.remember("t1", "The refactor was completed successfully", tier="transcript")
        m.remember("t2", "Unrelated entry", tier="transcript")
        hits = m.search_transcript("refactor")
        self.assertEqual(len(hits), 1)
        self.assertIn("refactor", hits[0])

    def test_index_truncated_to_200_chars(self):
        m = MemoryStore()
        m.remember("long", "X" * 500, tier="index")
        snap = m.index_snapshot()
        self.assertLessEqual(len(snap["long"]), 200)

    def test_persistence_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        m1 = MemoryStore(path)
        m1.remember("k1", "value1", tier="index")
        m1.remember("k2", "detail content", tier="detail")

        m2 = MemoryStore(path)
        self.assertEqual(m2.index_snapshot().get("k1"), "value1")
        self.assertEqual(m2.recall("k2"), "detail content")
        path.unlink(missing_ok=True)

    def test_forget(self):
        m = MemoryStore()
        m.remember("key", "val", tier="index")
        m.forget("key")
        self.assertNotIn("key", m.index_snapshot())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tools
# ─────────────────────────────────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.config = _make_config()
        self.registry = ToolRegistry(self.config)

        @tool("add", "Add two numbers",
              parameters={"type": "object",
                          "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                          "required": ["a", "b"]})
        def add(a: float, b: float) -> str:
            return str(a + b)

        @tool("explode", "Always raises",
              parameters={"type": "object", "properties": {}})
        def explode() -> str:
            raise ValueError("boom")

        self.registry.register(add)
        self.registry.register(explode)

    def test_schema_injection(self):
        schemas = self.registry.schemas_for_context()
        names = [s["name"] for s in schemas]
        self.assertIn("add", names)

    def test_successful_execution(self):
        results = self.registry.execute_batch([
            ToolCall(id="1", tool_name="add", arguments={"a": 3, "b": 4})
        ])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_error)
        self.assertEqual(results[0].output, "7")

    def test_error_captured_not_raised(self):
        results = self.registry.execute_batch([
            ToolCall(id="2", tool_name="explode", arguments={})
        ])
        self.assertTrue(results[0].is_error)
        self.assertIn("boom", results[0].output)

    def test_unknown_tool_returns_error(self):
        results = self.registry.execute_batch([
            ToolCall(id="3", tool_name="nonexistent", arguments={})
        ])
        self.assertTrue(results[0].is_error)


# ─────────────────────────────────────────────────────────────────────────────
# 3 & 4. Context management
# ─────────────────────────────────────────────────────────────────────────────

class TestContextManager(unittest.TestCase):

    def _make_history(self, n: int) -> List[Message]:
        msgs = []
        for i in range(n):
            msgs.append(Message(Role.USER, f"User message {i}"))
            msgs.append(Message(Role.ASSISTANT, f"Assistant reply {i}"))
            msgs.append(Message(Role.TOOL, f"Tool output {i}", tool_name="test"))
        return msgs

    def test_assemble_returns_system_and_history(self):
        cm = ContextManager(_make_config())
        sys_block, hist = cm.assemble(
            system_prompt="You are a test agent.",
            tool_schemas=[{"name": "t", "description": "d", "parameters": {}}],
            memory_index={"key": "val"},
            history=self._make_history(2),
            user_message="hello",
        )
        self.assertIn("You are a test agent.", sys_block)
        self.assertIn("Working Memory", sys_block)
        self.assertIn("Available Tools", sys_block)
        self.assertIsInstance(hist, list)

    def test_old_tool_outputs_masked(self):
        cm = ContextManager(_make_config())
        long_history = self._make_history(5)  # 15 messages
        _, hist = cm.assemble("sys", [], {}, long_history, "msg")
        tool_msgs = [m for m in hist if m.role == Role.TOOL]
        masked = [m for m in tool_msgs if "masked" in m.content]
        self.assertTrue(len(masked) > 0, "Old tool outputs should be masked")

    def test_token_estimate_positive(self):
        cm = ContextManager(_make_config())
        est = cm.estimate_tokens("system block", self._make_history(3))
        self.assertGreater(est, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Output parser
# ─────────────────────────────────────────────────────────────────────────────

class TestOutputParser(unittest.TestCase):

    def setUp(self):
        self.parser = OutputParser()

    def test_native_tool_calls(self):
        raw = {
            "content": "",
            "tool_calls": [
                {"id": "tc1", "name": "search", "arguments": {"query": "test"}}
            ]
        }
        parsed = self.parser.parse(raw)
        self.assertEqual(len(parsed.tool_calls), 1)
        self.assertEqual(parsed.tool_calls[0].tool_name, "search")
        self.assertIsNone(parsed.final_answer)

    def test_final_answer_no_tools(self):
        raw = {"content": "The answer is 42.", "tool_calls": []}
        parsed = self.parser.parse(raw)
        self.assertEqual(parsed.final_answer, "The answer is 42.")
        self.assertEqual(len(parsed.tool_calls), 0)

    def test_react_pattern(self):
        text = (
            "Thought: I need to search\n"
            "Action: search\n"
            "Action Input: {\"query\": \"python\"}\n"
            "Observation: found results"
        )
        parsed = self.parser.parse(text)
        self.assertEqual(len(parsed.tool_calls), 1)
        self.assertEqual(parsed.tool_calls[0].tool_name, "search")

    def test_react_final_answer(self):
        text = "Final Answer: Python is a programming language."
        parsed = self.parser.parse(text)
        self.assertIsNotNone(parsed.final_answer)
        self.assertIn("Python", parsed.final_answer)

    def test_retry_parse_builds_prompt(self):
        prompt = self.parser.retry_parse("original", "bad output", "SyntaxError")
        self.assertIn("original", prompt)
        self.assertIn("bad output", prompt)
        self.assertIn("SyntaxError", prompt)


# ─────────────────────────────────────────────────────────────────────────────
# 7. State checkpointing
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpointStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = CheckpointStore(Path(self.tmp))

    def test_save_and_load_roundtrip(self):
        state = HarnessState(session_id="s1", goal="test goal", turns=3)
        state.messages.append(Message(Role.USER, "hello"))
        self.store.save(state)
        loaded = self.store.load_latest("s1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.goal, "test goal")
        self.assertEqual(loaded.turns, 3)
        self.assertEqual(loaded.messages[0].content, "hello")

    def test_load_returns_none_for_unknown_session(self):
        self.assertIsNone(self.store.load_latest("ghost_session"))

    def test_ralph_loop_progress(self):
        self.store.write_progress("s2", {"completed": ["task1"], "current": "task2"})
        progress = self.store.read_progress("s2")
        self.assertEqual(progress["completed"], ["task1"])
        self.assertEqual(progress["current"], "task2")

    def test_progress_merge(self):
        self.store.write_progress("s3", {"a": 1})
        self.store.write_progress("s3", {"b": 2})
        p = self.store.read_progress("s3")
        self.assertEqual(p["a"], 1)
        self.assertEqual(p["b"], 2)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Error handling
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling(unittest.TestCase):

    def test_classify_transient(self):
        self.assertEqual(classify(ConnectionError("timeout")), ErrorCategory.TRANSIENT)

    def test_classify_llm_recoverable(self):
        self.assertEqual(classify(ValueError("bad value")), ErrorCategory.LLM_RECOVERABLE)

    def test_classify_user_fixable(self):
        self.assertEqual(classify(PermissionError("denied")), ErrorCategory.USER_FIXABLE)

    def test_classify_unexpected(self):
        self.assertEqual(classify(RuntimeError("????")), ErrorCategory.UNEXPECTED)

    def test_tool_execution_error_message(self):
        err = ToolExecutionError("search", "rate limit exceeded")
        msg = err.as_tool_message()
        self.assertIn("search", msg)
        self.assertIn("rate limit", msg)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Guardrails
# ─────────────────────────────────────────────────────────────────────────────

class TestGuardrailLayer(unittest.TestCase):

    def test_passthrough_without_aegis(self):
        gl = GuardrailLayer(_make_config(), aegis=None)
        v = gl.check_input("hello world")
        self.assertTrue(v.passed)
        self.assertFalse(v.tripwire)

    def test_output_passthrough(self):
        gl = GuardrailLayer(_make_config(), aegis=None)
        v = gl.check_output("safe content")
        self.assertTrue(v.passed)

    def test_tool_call_passthrough(self):
        gl = GuardrailLayer(_make_config(), aegis=None)
        v = gl.check_tool_call(ToolCall("1", "search", {"query": "hello"}))
        self.assertTrue(v.passed)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Verification
# ─────────────────────────────────────────────────────────────────────────────

class TestVerificationEngine(unittest.TestCase):

    def test_python_syntax_check_pass(self):
        r = VerificationEngine.python_syntax_check("def f(): return 1")
        self.assertTrue(r.passed)

    def test_python_syntax_check_fail(self):
        r = VerificationEngine.python_syntax_check("def f( return 1")
        self.assertFalse(r.passed)
        self.assertIn("SyntaxError", r.feedback)

    def test_shell_command_pass(self):
        r = VerificationEngine.shell_command_verifier("echo ok")
        self.assertTrue(r.passed)

    def test_shell_command_fail(self):
        r = VerificationEngine.shell_command_verifier("exit 1")
        self.assertFalse(r.passed)

    def test_composite_all_pass(self):
        ve = VerificationEngine()
        ve.add_rules_verifier(lambda _: __import__('ethos_aegis.harness.types', fromlist=['VerificationResult']).VerificationResult(True, 1.0, "ok", "rules"))
        r = ve.verify("some output")
        self.assertTrue(r.passed)


# ─────────────────────────────────────────────────────────────────────────────
# Full orchestrator integration
# ─────────────────────────────────────────────────────────────────────────────

class TestAegisHarnessLoop(unittest.TestCase):

    def test_single_turn_final_answer(self):
        adapter = MockAdapter([
            {"content": "The answer is 42.", "tool_calls": []}
        ])
        with tempfile.TemporaryDirectory() as tmp:
            harness = AegisHarness(
                adapter=adapter,
                config=_make_config(),
                checkpoint_dir=Path(tmp),
            )
            events = list(harness.run("What is 6 times 7?"))
        final = next((e for e in events if e["type"] == "final_answer"), None)
        self.assertIsNotNone(final)
        self.assertEqual(final["content"], "The answer is 42.")

    def test_tool_call_then_final_answer(self):
        adapter = MockAdapter([
            # Turn 1: call a tool
            {"content": "", "tool_calls": [
                {"id": "t1", "name": "add", "arguments": {"a": 10, "b": 5}}
            ]},
            # Turn 2: final answer
            {"content": "The sum is 15.", "tool_calls": []},
        ])

        @tool("add", "Add two numbers",
              parameters={"type": "object",
                          "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                          "required": ["a", "b"]})
        def add(a: float, b: float) -> str:
            return str(a + b)

        with tempfile.TemporaryDirectory() as tmp:
            harness = AegisHarness(
                adapter=adapter,
                config=_make_config(),
                checkpoint_dir=Path(tmp),
            )
            harness.tools.register(add)
            events = list(harness.run("What is 10 + 5?"))

        tool_events = [e for e in events if e["type"] == "tool_results"]
        final_events = [e for e in events if e["type"] == "final_answer"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["results"][0]["output"], "15")
        self.assertEqual(len(final_events), 1)

    def test_max_turns_termination(self):
        # Always returns a tool call → should hit max_turns
        adapter = MockAdapter([
            {"content": "", "tool_calls": [
                {"id": f"t{i}", "name": "loop", "arguments": {}}
            ]} for i in range(20)
        ])

        @tool("loop", "Infinite loop tool", parameters={"type": "object", "properties": {}})
        def loop_tool() -> str:
            return "looping"

        with tempfile.TemporaryDirectory() as tmp:
            harness = AegisHarness(
                adapter=adapter,
                config=_make_config(max_turns=3),
                checkpoint_dir=Path(tmp),
            )
            harness.tools.register(loop_tool)
            events = list(harness.run("loop forever"))

        terminated = next((e for e in events if e["type"] == "terminated"), None)
        self.assertIsNotNone(terminated)
        self.assertEqual(terminated["reason"], "max_turns")

    def test_checkpoint_persisted(self):
        adapter = MockAdapter([
            {"content": "Done.", "tool_calls": []}
        ])
        with tempfile.TemporaryDirectory() as tmp:
            harness = AegisHarness(
                adapter=adapter,
                config=_make_config(),
                checkpoint_dir=Path(tmp),
            )
            events = list(harness.run("test goal", session_id="sess_test"))
            loaded = harness._checkpoints.load_latest("sess_test")
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.terminated)


if __name__ == "__main__":
    unittest.main()
