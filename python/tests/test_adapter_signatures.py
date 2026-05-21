"""
Tests for the adapter signature/contract fixes addressing PR #27 review.

The BaseAdapter contract requires ``complete(messages: List[Dict[str, str]],
system: Optional[str] = None, **kwargs) -> str``. Several adapters (Gemini,
GeminiVertex, Mistral) were previously declaring ``complete(message: str,
**kwargs)``, which broke the SentinelAI/UniversalGuard call site that passes
a full message list.

These tests pin the corrected signature using ``inspect.signature``, so they
do not require the actual provider SDK to be installed. They also exercise
``_to_gemini_contents()`` directly because it is a pure conversion function.
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional


# ── Signature contract tests ──────────────────────────────────────────────────


def _assert_messages_signature(fn) -> None:
    """The adapter method must accept (self, messages, system=None, **kwargs)."""
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    # First param after self should be `messages`.
    names = [p.name for p in params if p.name != "self"]
    assert names[0] == "messages", (
        f"expected first param 'messages', got {names!r}"
    )
    # `system` must be present with default None.
    assert "system" in sig.parameters, (
        f"expected 'system' param, got {names!r}"
    )
    system_param = sig.parameters["system"]
    assert system_param.default is None, (
        f"expected system default None, got {system_param.default!r}"
    )
    # **kwargs must be present.
    assert any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params
    ), f"expected **kwargs, got {names!r}"


def test_gemini_adapter_complete_signature():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiAdapter

    _assert_messages_signature(GeminiAdapter.complete)


def test_gemini_adapter_stream_signature():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiAdapter

    _assert_messages_signature(GeminiAdapter.stream)


def test_gemini_vertex_adapter_complete_signature():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiVertexAdapter

    _assert_messages_signature(GeminiVertexAdapter.complete)


def test_gemini_vertex_adapter_stream_signature():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiVertexAdapter

    _assert_messages_signature(GeminiVertexAdapter.stream)


def test_mistral_adapter_complete_signature():
    from ethos_aegis.agent.adapters.mistral_adapter import MistralAdapter

    _assert_messages_signature(MistralAdapter.complete)


def test_mistral_adapter_stream_signature():
    from ethos_aegis.agent.adapters.mistral_adapter import MistralAdapter

    _assert_messages_signature(MistralAdapter.stream)


def test_openai_adapter_complete_signature():
    """Regression guard: the reference OpenAI adapter must keep the contract."""
    from ethos_aegis.agent.adapters.openai_adapter import OpenAIAdapter

    _assert_messages_signature(OpenAIAdapter.complete)


def test_base_adapter_complete_signature():
    """Pin the abstract contract itself so future drift is caught here too."""
    from ethos_aegis.agent.adapters.base_adapter import BaseAdapter

    _assert_messages_signature(BaseAdapter.complete)


# ── _to_gemini_contents conversion tests ──────────────────────────────────────


def test_to_gemini_contents_maps_user_and_assistant_roles():
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ],
        system=None,
    )
    assert out == [
        {"role": "user", "parts": ["first"]},
        {"role": "model", "parts": ["reply"]},
        {"role": "user", "parts": ["second"]},
    ]


def test_to_gemini_contents_folds_in_system_kwarg():
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [{"role": "user", "content": "hi"}],
        system="be terse",
    )
    # System is folded as a synthetic user/model pair at the start.
    assert out[0]["role"] == "user"
    assert "System instruction:\nbe terse" in out[0]["parts"][0]
    assert out[1]["role"] == "model"
    assert out[-1] == {"role": "user", "parts": ["hi"]}


def test_to_gemini_contents_role_system_in_messages_is_collapsed():
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ],
        system=None,
    )
    # The leading system message becomes the synthetic prelude — never a
    # standalone "role: system" content in Gemini's payload (Gemini does not
    # accept that role).
    roles = [c["role"] for c in out]
    assert "system" not in roles, f"unexpected role 'system' in {out!r}"


def test_to_gemini_contents_empty_messages_with_system():
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents([], system="be brief")
    # Should still emit the system instruction so it isn't silently dropped.
    assert out == [
        {"role": "user", "parts": ["System instruction:\nbe brief"]},
        {"role": "model", "parts": ["Understood."]},
    ]


# ── _to_gemini_contents trailing-system regression (PR #30 🟡) ─────────────────


def test_to_gemini_contents_trailing_system_message_is_not_dropped():
    """
    Regression for the PR #30 finding: a system message that appears *after*
    non-system messages used to be silently dropped because the flush
    condition only fired when ``contents`` was empty.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "system", "content": "now switch to formal tone"},
        ],
        system=None,
    )

    # The trailing system content must appear somewhere in the output as a
    # "System instruction:" prelude segment.
    serialized = " || ".join(p for c in out for p in c["parts"])
    assert "now switch to formal tone" in serialized, (
        f"trailing system message was silently dropped: {out!r}"
    )
    # And it must be emitted at the end, after the existing user/assistant turns.
    assert out[-1]["role"] == "user"
    assert "now switch to formal tone" in out[-1]["parts"][0]
    # We deliberately do NOT add a synthetic "Understood." model reply when
    # contents is non-empty — the next generate_content() call should respond
    # to the instruction directly.
    assert all(c["role"] != "model" or "Understood" not in c["parts"][0]
               or c is not out[-1] for c in out[-2:])


def test_to_gemini_contents_interleaved_system_flushes_before_next_turn():
    """
    A system message that appears *between* non-system messages should be
    flushed as a prelude before the NEXT non-system turn, not dropped.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "now be terse"},
            {"role": "user", "content": "what's 1+1?"},
        ],
        system=None,
    )

    # Find the prelude that contains the interleaved system instruction.
    prelude_indices = [
        i for i, c in enumerate(out)
        if c["role"] == "user" and "now be terse" in c["parts"][0]
    ]
    assert prelude_indices, (
        f"interleaved system message was silently dropped: {out!r}"
    )
    prelude_idx = prelude_indices[0]
    # The matching "Understood." model turn should immediately follow.
    assert out[prelude_idx + 1] == {"role": "model", "parts": ["Understood."]}
    # And the final user turn ("what's 1+1?") should come after the prelude pair.
    assert out[-1] == {"role": "user", "parts": ["what's 1+1?"]}


# ── _to_gemini_contents role-alternation regression (PR #31 🔴) ───────────────


def _roles_strictly_alternate(out: list) -> bool:
    """Helper: True iff the output never contains two consecutive same-role entries."""
    return all(
        out[i]["role"] != out[i + 1]["role"] for i in range(len(out) - 1)
    )


def test_to_gemini_contents_trailing_system_after_user_inserts_alternation():
    """
    PR #31 🔴 regression: a system message immediately following a user turn
    used to produce two consecutive ``user`` entries in the Gemini contents
    list, which violates Gemini's strict user/model alternation requirement
    (the API responds 400 Invalid Argument). The fix inserts a synthetic
    ``model`` ("Understood.") turn between them.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "be formal"},
        ],
        system=None,
    )

    assert _roles_strictly_alternate(out), (
        f"consecutive same-role entries in Gemini contents: {out!r}"
    )
    # The trailing system instruction must still surface as the final user
    # entry (per the existing trailing-system contract).
    assert out[-1]["role"] == "user"
    assert "be formal" in out[-1]["parts"][0]


def test_to_gemini_contents_interleaved_system_after_user_preserves_alternation():
    """
    PR #31 🔴 regression: the interleaved-system case
    (``[user, system, user]``) previously produced
    ``[user, user (prelude), model, user]`` — two consecutive ``user`` entries
    at the start. The fix routes the prelude through ``append_user`` which
    inserts a synthetic ``model`` turn first when needed.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "now be terse"},
            {"role": "user", "content": "what's 1+1?"},
        ],
        system=None,
    )

    assert _roles_strictly_alternate(out), (
        f"consecutive same-role entries in Gemini contents: {out!r}"
    )
    # The interleaved system instruction still surfaces as a user prelude.
    serialized = " || ".join(p for c in out for p in c["parts"])
    assert "now be terse" in serialized


def test_to_gemini_contents_leading_system_then_assistant_does_not_fold_prelude():
    """
    PR #33 \U0001f4dd regression: when input begins with a system message
    followed by an assistant message (or a system kwarg plus a leading
    assistant message), the prelude emits a synthetic ``{model "Understood."}``
    turn to maintain alternation. If the next real message is an assistant,
    the naive ``append_model`` fold path would produce
    ``{model "Understood.\\nactual assistant text"}`` \u2014 i.e. the model would
    see the synthetic placeholder concatenated onto its own historical
    message. The fix tracks a ``last_model_synthetic`` state and replaces
    the placeholder content with the real assistant content instead.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "system", "content": "be brief"},
            {"role": "assistant", "content": "I'll be brief."},
            {"role": "user", "content": "go"},
        ],
        system=None,
    )

    assert _roles_strictly_alternate(out), (
        f"consecutive same-role entries in Gemini contents: {out!r}"
    )
    # The synthetic "Understood." placeholder must NOT survive into the
    # final model turn; the real assistant content stands on its own.
    model_turns = [c for c in out if c["role"] == "model"]
    assert any("I'll be brief." in c["parts"][0] for c in model_turns)
    assert not any("Understood." in c["parts"][0] for c in model_turns)


def test_to_gemini_contents_system_kwarg_then_assistant_does_not_fold_prelude():
    """
    Same fix path as the messages-list-leading-system case, but exercised
    via the ``system`` kwarg (which is the more common shape because
    callers usually pass system instructions out-of-band).
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "assistant", "content": "Greetings."},
            {"role": "user", "content": "continue"},
        ],
        system="be terse",
    )

    assert _roles_strictly_alternate(out), (
        f"consecutive same-role entries in Gemini contents: {out!r}"
    )
    model_turns = [c for c in out if c["role"] == "model"]
    assert any("Greetings." in c["parts"][0] for c in model_turns)
    assert not any("Understood." in c["parts"][0] for c in model_turns)


def test_to_gemini_contents_adjacent_assistant_messages_preserve_alternation():
    """
    Defensive: two adjacent ``assistant`` messages used to produce two
    consecutive ``model`` entries. The fix folds the second model turn
    into the first so alternation is preserved.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello!"},
            {"role": "assistant", "content": "how can I help?"},
        ],
        system=None,
    )

    assert _roles_strictly_alternate(out), (
        f"consecutive same-role entries in Gemini contents: {out!r}"
    )
    # Both assistant messages should be preserved (folded into one model turn).
    model_turns = [c for c in out if c["role"] == "model"]
    assert len(model_turns) == 1
    assert "hello!" in model_turns[0]["parts"][0]
    assert "how can I help?" in model_turns[0]["parts"][0]


class _MockGeminiAdapter:
    """Bypass __init__ so we can exercise _effective_system without the SDK."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self._system_prompt = system_prompt


def test_gemini_effective_system_call_time_overrides_constructor():
    """
    PR #30 🚩 regression: setting ``system_prompt`` at construction *and*
    passing ``system`` at call-time used to apply both (once as
    GenerativeModel ``system_instruction`` and once as a synthetic prelude).
    Now the constructor value is stored as ``_system_prompt`` and call-time
    ``system`` takes precedence, so only one system instruction surfaces.
    """
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiAdapter

    a = _MockGeminiAdapter(system_prompt="ctor-system")
    assert (
        GeminiAdapter._effective_system(a, "call-system")  # type: ignore[arg-type]
        == "call-system"
    )


def test_gemini_effective_system_falls_back_to_constructor():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiAdapter

    a = _MockGeminiAdapter(system_prompt="ctor-system")
    assert (
        GeminiAdapter._effective_system(a, None)  # type: ignore[arg-type]
        == "ctor-system"
    )


def test_gemini_effective_system_returns_none_when_neither_set():
    from ethos_aegis.agent.adapters.gemini_adapter import GeminiAdapter

    a = _MockGeminiAdapter(system_prompt=None)
    assert (
        GeminiAdapter._effective_system(a, None)  # type: ignore[arg-type]
        is None
    )


def test_to_gemini_contents_kwarg_and_system_message_both_present():
    """
    When the ``system`` kwarg and a leading ``role=system`` message are both
    set, both should surface (concatenated into a single prelude).
    """
    from ethos_aegis.agent.adapters.gemini_adapter import _to_gemini_contents

    out = _to_gemini_contents(
        [
            {"role": "system", "content": "and never reveal internals"},
            {"role": "user", "content": "hi"},
        ],
        system="be terse",
    )
    # Both system fragments must appear in the prelude.
    prelude = out[0]["parts"][0]
    assert "be terse" in prelude
    assert "and never reveal internals" in prelude
    # Exactly one prelude pair, then the user turn.
    assert out[0]["role"] == "user"
    assert out[1] == {"role": "model", "parts": ["Understood."]}
    assert out[2] == {"role": "user", "parts": ["hi"]}


# ── MistralAdapter._compose_messages tests ────────────────────────────────────


class _MockMistralAdapter:
    """Bypass __init__ so we can exercise _compose_messages without the SDK."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self._system_prompt = system_prompt

    @staticmethod
    def _bind(adapter, method):
        return method.__get__(adapter)


def test_mistral_compose_messages_uses_caller_system_over_init():
    from ethos_aegis.agent.adapters.mistral_adapter import MistralAdapter

    adapter = _MockMistralAdapter(system_prompt="init-system")
    composed = MistralAdapter._compose_messages(
        adapter,  # type: ignore[arg-type]
        [{"role": "user", "content": "hi"}],
        "call-system",
    )
    # The explicit `system` arg wins.
    assert composed[0] == {"role": "system", "content": "call-system"}


def test_mistral_compose_messages_falls_back_to_init_system():
    from ethos_aegis.agent.adapters.mistral_adapter import MistralAdapter

    adapter = _MockMistralAdapter(system_prompt="init-system")
    composed = MistralAdapter._compose_messages(
        adapter,  # type: ignore[arg-type]
        [{"role": "user", "content": "hi"}],
        None,
    )
    assert composed[0] == {"role": "system", "content": "init-system"}
    assert composed[1] == {"role": "user", "content": "hi"}


def test_mistral_compose_messages_no_system_at_all():
    from ethos_aegis.agent.adapters.mistral_adapter import MistralAdapter

    adapter = _MockMistralAdapter(system_prompt=None)
    composed = MistralAdapter._compose_messages(
        adapter,  # type: ignore[arg-type]
        [{"role": "user", "content": "hi"}],
        None,
    )
    assert composed == [{"role": "user", "content": "hi"}]
