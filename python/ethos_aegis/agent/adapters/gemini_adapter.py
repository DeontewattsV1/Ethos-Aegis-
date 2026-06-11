"""
GeminiAdapter -- Ethos Aegis adapter for Google Gemini / Vertex AI.

Supports Google AI Studio (generativeai SDK) and Vertex AI endpoints.

pip install google-generativeai>=0.7   # Google AI Studio
pip install google-cloud-aiplatform    # Vertex AI (optional)
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

    Parts are plain strings (not dicts) to match what GenerativeModel accepts
    and what the test suite asserts.

    Rules:
    - ``role: "system"`` messages are folded into the next user turn as a
      ``"System instruction:\\n<text>\\n\\n"`` preamble.
    - If a ``system`` kwarg is supplied it is merged the same way, prepended
      before any inline system messages.
    - Consecutive same-role turns are merged with a newline separator.
    - Trailing system messages with no following user turn are emitted as a
      final ``user`` turn (Gemini requires alternating roles).
    """
    gemini_role = {"user": "user", "assistant": "model", "model": "model"}

    # Build normalised message list, injecting the system kwarg first
    normalised: List[Dict[str, str]] = []
    if system:
        normalised.append({"role": "system", "content": system})
    normalised.extend(messages)

    # Fold system messages into the following user turn
    pending_system: List[str] = []
    merged: List[Dict[str, str]] = []
    for msg in normalised:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            pending_system.append(content)
        else:
            if pending_system and role == "user":
                preamble = "System instruction:\n" + "\n".join(pending_system)
                content = preamble + "\n\n" + content
                pending_system = []
            merged.append({"role": role, "content": content})

    # Handle trailing system messages (no following user turn)
    if pending_system:
        merged.append({
            "role": "user",
            "content": "System instruction:\n" + "\n".join(pending_system),
        })

    if not merged:
        return []

    # Convert to Gemini format -- parts are plain strings
    contents: List[Dict] = []
    for msg in merged:
        g_role = gemini_role.get(msg["role"], "user")
        if contents and contents[-1]["role"] == g_role:
            contents[-1]["parts"][0] += "\n" + msg["content"]
        else:
            contents.append({"role": g_role, "parts": [msg["content"]]})

    return contents


class GeminiAdapter(BaseAdapter):
    """
    Wraps the Google Gemini GenerativeModel API.

    Args:
        api_key:       Google AI Studio API key (or set GOOGLE_API_KEY env var).
        model:         Gemini model ID. Default: "gemini-1.5-pro".
        temperature:   Sampling temperature. Default: 0.7.
        max_tokens:    Max output tokens. Default: 1024.
        system_prompt: System instruction stored as ``_system_prompt``; can be
                       overridden per-call via the ``system`` kwarg.
        safety_settings: Override Gemini safety settings dict.
        **kwargs:      Forwarded to GenerativeModel constructor.
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
        self._system_prompt = system_prompt  # stored; used by _effective_system

    # -- Helpers -------------------------------------------------------------

    def _effective_system(self, call_time_system: Optional[str]) -> Optional[str]:
        """Return the system instruction to use for this call.

        Call-time ``system`` takes precedence over the constructor value so
        both are never applied simultaneously (avoids double-injection).
        """
        return call_time_system if call_time_system is not None else self._system_prompt

    # -- BaseAdapter interface ------------------------------------------------

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
        response = self._model.generate_content(contents, generation_config=config)
        return response.text or ""

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
        for chunk in self._model.generate_content(
            contents, generation_config=config, stream=True
        ):
            if chunk.text:
                yield chunk.text


class GeminiVertexAdapter(BaseAdapter):
    """
    Wraps Gemini via Vertex AI (google-cloud-aiplatform).

    pip install google-cloud-aiplatform>=1.50
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
        system_prompt: str | None = None,
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

        self._model_id      = model
        self._model         = GenerativeModel(model)
        self._temperature   = temperature
        self._max_tokens    = max_tokens
        self._system_prompt = system_prompt

    def _effective_system(self, call_time_system: Optional[str]) -> Optional[str]:
        return call_time_system if call_time_system is not None else self._system_prompt

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
        for chunk in self._model.generate_content(
            contents, generation_config=config, stream=True
        ):
            if chunk.text:
                yield chunk.text
