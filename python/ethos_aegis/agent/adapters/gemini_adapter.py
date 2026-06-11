"""
GeminiAdapter -- Ethos Aegis adapter for Google Gemini / Vertex AI.

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

    Parts are plain strings (not dicts).

    Invariants:
    - First turn is always ``user`` (Gemini rejects model-first inputs).
    - Roles strictly alternate.
    - ``role: "system"`` is never emitted directly.

    Folding rules:
    1. Any accumulated system messages are emitted as:
         user("System instruction:\\n<text>") + model("Understood.")
       ...before the next real user/model turn.
    2. When the next real turn is also ``user``, the real user content follows
       as a third turn (giving: user-prelude, model-Understood, user-real).
    3. Trailing system (no following real turn): same user+model pair at end.
    4. Empty input with system kwarg only: user+model pair.
    5. Leading ``assistant``/``model`` with no prior user: synthesize
       ``user("Continue from prior context.")`` prelude first.
    6. When a synthetic ``model("Understood.")`` is immediately followed by a
       real model/assistant turn, replace the placeholder with the real content.
    """
    gemini_role = {"user": "user", "assistant": "model", "model": "model"}

    # Prepend system kwarg as a synthetic system message
    normalised: List[Dict[str, str]] = []
    if system:
        normalised.append({"role": "system", "content": system})
    normalised.extend(messages)

    out: List[Dict] = []
    pending_system: List[str] = []
    last_is_synthetic_understood = False  # sentinel for rule 6

    def _flush_system_as_pair() -> None:
        """Emit pending system messages as user(prelude) + model(Understood.)."""
        nonlocal pending_system, last_is_synthetic_understood
        if not pending_system:
            return
        preamble = "System instruction:\n" + "\n".join(pending_system)
        pending_system = []
        # If last turn was user, insert model bridge to maintain alternation
        if out and out[-1]["role"] == "user":
            out.append({"role": "model", "parts": ["Understood."]})
        out.append({"role": "user", "parts": [preamble]})
        out.append({"role": "model", "parts": ["Understood."]})
        last_is_synthetic_understood = True

    for msg in normalised:
        role = msg.get("role", "user")
        text = msg.get("content", "")

        if role == "system":
            pending_system.append(text)
            continue

        g_role = gemini_role.get(role, "user")

        # Flush pending system as user/model pair before this turn
        _flush_system_as_pair()

        # Rule 5: first turn must be user
        if not out and g_role == "model":
            out.append({"role": "user", "parts": ["Continue from prior context."]})
            last_is_synthetic_understood = False

        # Rule 6: replace synthetic Understood. with real model content
        if (
            last_is_synthetic_understood
            and g_role == "model"
            and out
            and out[-1]["role"] == "model"
            and out[-1]["parts"][0] == "Understood."
        ):
            out[-1]["parts"][0] = text
            last_is_synthetic_understood = False
            continue

        # Normal append -- merge consecutive same-role turns
        if out and out[-1]["role"] == g_role:
            out[-1]["parts"][0] += "\n" + text
        else:
            out.append({"role": g_role, "parts": [text]})
        last_is_synthetic_understood = False

    # Trailing system messages
    if pending_system:
        preamble = "System instruction:\n" + "\n".join(pending_system)
        pending_system = []
        if not out:
            out.append({"role": "user", "parts": [preamble]})
            out.append({"role": "model", "parts": ["Understood."]})
        else:
            if out[-1]["role"] == "user":
                out.append({"role": "model", "parts": ["Understood."]})
            out.append({"role": "user", "parts": [preamble]})
            # trailing system: no Understood. (per trailing-system contract)

    return out


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

    def _effective_system(self, call_time_system: Optional[str]) -> Optional[str]:
        """Call-time ``system`` overrides constructor ``system_prompt``."""
        return call_time_system if call_time_system is not None else self._system_prompt

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
        for chunk in self._model.generate_content(
            contents, generation_config=config, stream=True
        ):
            if chunk.text:
                yield chunk.text


class GeminiVertexAdapter(BaseAdapter):
    """Wraps Gemini via Vertex AI (google-cloud-aiplatform>=1.50)."""

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
