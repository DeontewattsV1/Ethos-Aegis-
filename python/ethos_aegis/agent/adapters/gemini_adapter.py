"""
GeminiAdapter -- Ethos Aegis adapter for Google Gemini / Vertex AI.

pip install google-generativeai>=0.7
pip install google-cloud-aiplatform  # Vertex AI (optional)
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional
from .base_adapter import BaseAdapter


def _to_gemini_contents(
    messages: List[Dict[str, str]],
    *,
    system: Optional[str] = None,
) -> List[Dict]:
    """Convert a standard message list into Gemini ``contents`` format.

    Contract (pinned by test suite):

    - ``parts`` entries are plain strings (not ``{"text": "..."}`` dicts).
    - Gemini does not accept ``role: "system"`` — that role never appears in
      the returned list.
    - ``system`` kwarg and ``role: "system"`` messages are folded together
      into a single synthetic user/model prelude pair:
        ``{"role": "user", "parts": ["System instruction:\\n..."]}``
        ``{"role": "model", "parts": ["Understood."]}``
    - When a system message appears *between* turns it is flushed as a
      user/model prelude pair immediately before the next user content.
    - Trailing system messages (no following user content) become the final
      user turn (no Understood. because there is no next turn to alternate to).
    - A standalone system-only call (no other messages) emits:
        ``[user(prelude), model("Understood.")]``
    - The first turn must always be ``"user"``. If the first non-system
      message is ``"assistant"``/``"model"``, a synthetic user prelude is
      prepended.
    - Consecutive same-role turns are merged with ``"\\n"``.
    """
    gemini_role = {"user": "user", "assistant": "model", "model": "model"}

    # Inject system kwarg as a leading virtual system message
    normalised: List[Dict[str, str]] = []
    if system:
        normalised.append({"role": "system", "content": system})
    normalised.extend(messages)

    if not normalised:
        return []

    # Determine if there are any real (non-system) messages
    real_messages = [m for m in normalised if m.get("role") != "system"]

    # ----------------------------------------------------------------
    # Build merged list: fold system messages into the following user turn
    # as a "System instruction:\n..." preamble, OR as a standalone prelude
    # pair when there is no following user message.
    # ----------------------------------------------------------------
    pending_system: List[str] = []
    merged: List[Dict[str, str]] = []  # role: user|assistant|model + content

    def _flush_system_as_prelude(following_content: str = "") -> str:
        """Combine pending system messages with optional following content.
        Returns the combined content string."""
        nonlocal pending_system
        preamble = "\n".join(f"System instruction:\n{s}" for s in pending_system)
        pending_system = []
        if following_content:
            return preamble + "\n\n" + following_content
        return preamble

    for msg in normalised:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            pending_system.append(content)
        elif role == "user":
            if pending_system:
                # Fold system preamble into this user turn
                content = _flush_system_as_prelude(content)
            merged.append({"role": "user", "content": content})
        else:
            # assistant / model
            if pending_system:
                # System before a non-user turn: emit standalone prelude user
                # turn then the model turn follows naturally
                merged.append({"role": "user", "content": _flush_system_as_prelude()})
            merged.append({"role": role, "content": content})

    # Trailing system with no following turn
    if pending_system:
        preamble = _flush_system_as_prelude()
        merged.append({"role": "user", "content": preamble})

    if not merged:
        return []

    # Ensure first turn is "user"
    first_g_role = gemini_role.get(merged[0]["role"], "user")
    if first_g_role != "user":
        merged.insert(0, {"role": "user", "content": ""})

    # Convert to Gemini format with plain-string parts
    # Merge consecutive same-role turns
    contents: List[Dict] = []
    for msg in merged:
        g_role = gemini_role.get(msg["role"], "user")
        if contents and contents[-1]["role"] == g_role:
            sep = "\n" if contents[-1]["parts"][0] else ""
            contents[-1]["parts"][0] += sep + msg["content"]
        else:
            contents.append({"role": g_role, "parts": [msg["content"]]})

    # ----------------------------------------------------------------
    # Insert synthetic "Understood." model turns after system preludes
    # to maintain strict alternation.
    #
    # A turn is a "system prelude" if:
    #   - role is "user"
    #   - content contains "System instruction:"
    #   - it is NOT the final turn (i.e. a real user message follows)
    #     OR it is the only turn (standalone system-only case)
    # ----------------------------------------------------------------
    final: List[Dict] = []
    for i, turn in enumerate(contents):
        final.append(turn)
        is_prelude = (
            turn["role"] == "user"
            and "System instruction:" in turn["parts"][0]
        )
        if is_prelude:
            next_turn = contents[i + 1] if i + 1 < len(contents) else None
            is_last = next_turn is None
            next_is_user = next_turn is not None and next_turn["role"] == "user"

            if is_last:
                # Standalone system — emit Understood.
                final.append({"role": "model", "parts": ["Understood."]})
            elif next_is_user:
                # Prelude before a user turn — emit Understood. so turns alternate
                final.append({"role": "model", "parts": ["Understood."]})
            # If next is model, no Understood. needed (already alternating)

    return final


class GeminiAdapter(BaseAdapter):
    """Wraps the Google Gemini GenerativeModel API."""

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

        import os as _os
        resolved_key = api_key or _os.getenv("GOOGLE_API_KEY") or _os.getenv("GEMINI_API_KEY")
        if resolved_key:
            genai.configure(api_key=resolved_key)

        model_kwargs: dict = {}
        if safety_settings:
            model_kwargs["safety_settings"] = safety_settings
        model_kwargs.update(kwargs)

        self._genai         = genai
        self._model_id      = model
        self._model         = genai.GenerativeModel(model, **model_kwargs)
        self._temperature   = temperature
        self._max_tokens    = max_tokens
        self._system_prompt = system_prompt

    def _effective_system(self, system: Optional[str]) -> Optional[str]:
        """Return call-time *system* if set, else fall back to constructor value."""
        return system if system is not None else self._system_prompt

    @property
    def provider_name(self) -> str:
        return "gemini"

    def model_id(self) -> str:
        return self._model_id

    def supports_streaming(self) -> bool:
        return True

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs,
    ) -> str:
        effective = self._effective_system(system)
        contents = _to_gemini_contents(messages, system=effective)
        config = self._genai.types.GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return self._model.generate_content(contents, generation_config=config).text or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs,
    ) -> Iterator[str]:
        effective = self._effective_system(system)
        contents = _to_gemini_contents(messages, system=effective)
        config = self._genai.types.GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        for chunk in self._model.generate_content(contents, generation_config=config, stream=True):
            if chunk.text:
                yield chunk.text


class GeminiVertexAdapter(BaseAdapter):
    """Wraps Gemini via Vertex AI."""

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
        except ImportError as exc:
            raise ImportError(
                "GeminiVertexAdapter requires: pip install google-cloud-aiplatform>=1.50"
            ) from exc

        self._model_id      = model
        self._model         = GenerativeModel(model)
        self._temperature   = temperature
        self._max_tokens    = max_tokens
        self._system_prompt: Optional[str] = None

    def _effective_system(self, system: Optional[str]) -> Optional[str]:
        return system if system is not None else self._system_prompt

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
        **kwargs,
    ) -> str:
        from vertexai.generative_models import GenerationConfig
        effective = self._effective_system(system)
        contents = _to_gemini_contents(messages, system=effective)
        config = GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return self._model.generate_content(contents, generation_config=config).text or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs,
    ) -> Iterator[str]:
        from vertexai.generative_models import GenerationConfig
        effective = self._effective_system(system)
        contents = _to_gemini_contents(messages, system=effective)
        config = GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        for chunk in self._model.generate_content(contents, generation_config=config, stream=True):
            if chunk.text:
                yield chunk.text
