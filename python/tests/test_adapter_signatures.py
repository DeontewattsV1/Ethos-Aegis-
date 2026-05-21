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
    ]


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
