"""
GeminiAdapter — Ethos Aegis adapter for Google Gemini / Vertex AI.

Supports Google AI Studio (generativeai SDK) and Vertex AI endpoints.

pip install google-generativeai>=0.7   # Google AI Studio
pip install google-cloud-aiplatform    # Vertex AI (optional)
"""

from __future__ import annotations
from typing import Any, Dict, Iterator, List, Optional
from .base_adapter import BaseAdapter


def _to_gemini_contents(
    messages: List[Dict[str, str]],
    system: Optional[str],
) -> list:
    """
    Convert OpenAI-style chat messages to Gemini's `contents` format.

    Gemini uses ``{"role": "user"|"model", "parts": [text]}`` while the
    BaseAdapter contract passes OpenAI-style ``{"role": "user"|"assistant"|"system", "content": text}``.

    System instructions (either passed via the ``system`` kwarg or as messages
    with ``role == "system"``) are folded in as user/model turn pairs so they
    surface in the prompt without requiring the caller to reconstruct the
    GenerativeModel with ``system_instruction``:

    * A *leading* system instruction (kwarg + any system messages that appear
      before the first non-system turn) is concatenated and emitted as one
      ``user -> model ("Understood.")`` prelude.
    * A *trailing* system instruction (system messages that appear after
      non-system turns and after which no further non-system turns follow)
      is emitted as a final user-side hint *without* a synthetic model reply,
      so the model's next generation responds to the instruction directly.
    * A system instruction that appears *between* non-system turns is emitted
      as a prelude before the very next non-system turn.

    This avoids silently dropping any system content, which was the previous
    behavior when system messages followed non-system messages.
    """
    contents: list = []
    pending_system = system
    # Tracks whether the most recently appended model turn is a synthetic
    # "Understood." placeholder emitted by flush_prelude(). When a real
    # assistant message immediately follows the prelude, append_model()
    # replaces the placeholder content instead of folding into it (which
    # would produce "Understood.\nactual assistant text").
    state = {"last_model_synthetic": False}

    def append_user(parts_text: str) -> None:
        # Gemini requires strict user/model alternation. If the last appended
        # entry is already user, insert a synthetic "Understood." model turn
        # first so the new user entry doesn't produce consecutive same-role
        # entries (which the API rejects with 400 Invalid Argument). The
        # synthetic model turn inserted here is sandwiched between two user
        # turns (the new user follows immediately), so it can never be folded
        # into by a subsequent append_model — no need to set the synthetic flag.
        if contents and contents[-1]["role"] == "user":
            contents.append({"role": "model", "parts": ["Understood."]})
        contents.append({"role": "user", "parts": [parts_text]})
        state["last_model_synthetic"] = False

    def append_model(parts_text: str) -> None:
        # Mirror of append_user: skip consecutive model entries. Two adjacent
        # model turns can only arise if the caller passed adjacent assistant
        # messages, or if a real assistant message follows a prelude's
        # synthetic "Understood." placeholder. In the latter case we replace
        # the placeholder with the real content (so the model doesn't see
        # "Understood.\nactual" as its own historical message); in the former
        # we fold the second message into the first.
        if contents and contents[-1]["role"] == "model":
            if state["last_model_synthetic"]:
                contents[-1]["parts"][0] = parts_text
            else:
                contents[-1]["parts"][0] = f"{contents[-1]['parts'][0]}\n{parts_text}"
            state["last_model_synthetic"] = False
            return
        # Gemini requires the first turn to be "user". If the caller passed
        # an assistant-first message sequence with no system kwarg (so no
        # prelude was emitted), we'd otherwise produce a leading model turn
        # and trigger a 400 Invalid Argument. Synthesize a minimal user turn
        # so the assistant content is interpreted as prior conversational
        # context the model previously produced.
        if not contents:
            contents.append(
                {"role": "user", "parts": ["Continue from prior context."]}
            )
        contents.append({"role": "model", "parts": [parts_text]})
        state["last_model_synthetic"] = False

    def flush_prelude() -> None:
        nonlocal pending_system
        if pending_system is not None:
            append_user(f"System instruction:\n{pending_system}")
            # NOTE: we append the synthetic "Understood." model turn directly
            # rather than going through append_model() because (a) append_user
            # has just guaranteed the last entry is "user", so the fold/replace
            # logic in append_model is dead code here, and (b) we need to set
            # state["last_model_synthetic"] = True afterwards so the NEXT
            # append_model() call (if any) knows it can replace this
            # placeholder rather than fold into it. Routing through
            # append_model would clear that flag.
            contents.append({"role": "model", "parts": ["Understood."]})
            state["last_model_synthetic"] = True
            pending_system = None

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            pending_system = (
                content if pending_system is None else f"{pending_system}\n\n{content}"
            )
            continue
        flush_prelude()
        if role == "assistant":
            append_model(content)
        else:
            append_user(content)

    # Always flush any remaining pending_system so trailing system messages
    # are not silently dropped. If no prior contents exist, emit as a
    # standard prelude (user + "Understood." model). Otherwise, emit as a
    # final user-side hint without a synthetic model reply so the next
    # generate_content() call responds directly to the instruction.
    if pending_system is not None:
        if not contents:
            flush_prelude()
        else:
            append_user(f"System instruction:\n{pending_system}")
            pending_system = None
    return contents


class GeminiAdapter(BaseAdapter):
    """
    Wraps the Google Gemini GenerativeModel API.

    Args:
        api_key:    Google AI Studio API key (or set GOOGLE_API_KEY env var).
        model:      Gemini model ID. Default: "gemini-1.5-pro".
        temperature: Sampling temperature. Default: 0.7.
        max_tokens:  Max output tokens. Default: 1024.
        system_prompt: System instruction (Gemini 1.5+ only).
        safety_settings: Override Gemini safety settings dict.
        **kwargs:   Forwarded to GenerativeModel constructor.

    Examples::

        from ethos_aegis.agent.adapters import GeminiAdapter
        from ethos_aegis.agent import UniversalGuard

        guard = UniversalGuard(
            adapter=GeminiAdapter(api_key="AIza...", model="gemini-1.5-pro")
        )
        response = guard.chat("Explain transformers in one paragraph.")
    """

    DEFAULT_MODEL = "gemini-1.5-pro"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
        safety_settings: dict | None = None,
        **kwargs,
    ) -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "GeminiAdapter requires: pip install google-generativeai>=0.7"
            ) from exc

        import os
        resolved_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if resolved_key:
            genai.configure(api_key=resolved_key)

        # NOTE: We deliberately do NOT pass `system_instruction` to
        # GenerativeModel here. The system prompt is applied per-call via
        # `_to_gemini_contents()` instead. If we baked it into the model
        # *and* also threaded a call-time `system` kwarg through
        # `_to_gemini_contents()`, the model would see the instruction twice
        # (once as baked-in and once as a user prelude). Routing both paths
        # through the same prelude mechanism keeps precedence deterministic:
        # call-time `system` overrides constructor `system_prompt`.
        model_kwargs: dict = {}
        if safety_settings:
            model_kwargs["safety_settings"] = safety_settings
        model_kwargs.update(kwargs)

        self._genai          = genai
        self._model_id       = model
        self._model          = genai.GenerativeModel(model, **model_kwargs)
        self._temperature    = temperature
        self._max_tokens     = max_tokens
        self._system_prompt  = system_prompt

    # ── BaseAdapter interface ─────────────────────────────────────────────

    @property
    def provider_name(self) -> str:
        return "gemini"

    def model_id(self) -> str:
        return self._model_id

    def supports_streaming(self) -> bool:
        return True

    def _effective_system(self, system: Optional[str]) -> Optional[str]:
        """
        Resolve which system instruction to apply for a single call.

        Caller-supplied ``system`` overrides the adapter-level
        ``system_prompt`` set at construction time. If both are absent,
        no system prelude is emitted.
        """
        return system if system is not None else self._system_prompt

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        contents = _to_gemini_contents(messages, self._effective_system(system))
        config = self._genai.types.GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        response = self._model.generate_content(contents, generation_config=config)
        return response.text or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        contents = _to_gemini_contents(messages, self._effective_system(system))
        config = self._genai.types.GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        for chunk in self._model.generate_content(
            contents, generation_config=config, stream=True
        ):
            if chunk.text:
                yield chunk.text


class GeminiVertexAdapter(BaseAdapter):
    """
    Wraps Gemini via Vertex AI (google-cloud-aiplatform).
    Use when you need enterprise billing, VPC, or regional data residency.

    pip install google-cloud-aiplatform>=1.50

    Args:
        project:    GCP project ID.
        location:   GCP region. Default: "us-central1".
        model:      Vertex model ID. Default: "gemini-1.5-pro-001".
        temperature: Default: 0.7.
        max_tokens:  Default: 1024.
    """

    DEFAULT_MODEL = "gemini-1.5-pro-001"

    def __init__(
        self,
        project: str,
        *,
        location: str = "us-central1",
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> None:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=project, location=location)
            self._model_cls = GenerativeModel
        except ImportError as exc:
            raise ImportError(
                "GeminiVertexAdapter requires: pip install google-cloud-aiplatform>=1.50"
            ) from exc

        self._model_id    = model
        self._model       = GenerativeModel(model)
        self._temperature = temperature
        self._max_tokens  = max_tokens

    @property
    def provider_name(self) -> str:
        return "gemini-vertex"

    def model_id(self) -> str:
        return self._model_id

    def supports_streaming(self) -> bool:
        return True

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        from vertexai.generative_models import GenerationConfig
        contents = _to_gemini_contents(messages, system)
        config = GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return self._model.generate_content(contents, generation_config=config).text or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        from vertexai.generative_models import GenerationConfig
        contents = _to_gemini_contents(messages, system)
        config = GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        for chunk in self._model.generate_content(contents, generation_config=config, stream=True):
            if chunk.text:
                yield chunk.text
