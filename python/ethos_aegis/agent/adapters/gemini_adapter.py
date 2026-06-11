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
    - ``parts`` entries are plain strings.
    - ``role: "system"`` messages are folded into the next user turn as a
      ``"System instruction:\\n<text>"`` preamble.
    - ``system`` kwarg is treated as a leading system message.
    - When a system message is emitted with no following user content,
      a synthetic ``{"role": "model", "parts": ["Understood."]}`` reply is
      appended so that Gemini's strict alternation requirement is satisfied.
    - The first turn **must** be ``"user"``.  If the first non-system message
      is ``"assistant"`` / ``"model"``, a synthetic empty-prelude user turn
      ``{"role": "user", "parts": [""]}`` is prepended so that the assistant
      content lands in the correct model slot.
    - Consecutive same-role turns are merged with ``"\\n"``.
    - Gemini does not accept ``role: "system"`` -- that role never appears
      in the returned list.
    """
    gemini_role = {"user": "user", "assistant": "model", "model": "model"}

    # Inject system kwarg as a virtual leading system message
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
                preamble = "\n".join(f"System instruction:\n{s}" for s in pending_system)
                content = preamble + "\n\n" + content
                pending_system = []
            elif pending_system:
                # pending system before a non-user turn -- flush as a user turn first
                preamble = "\n".join(f"System instruction:\n{s}" for s in pending_system)
                merged.append({"role": "user", "content": preamble})
                pending_system = []
            merged.append({"role": role, "content": content})

    # Trailing system messages with no following user turn
    if pending_system:
        preamble = "\n".join(f"System instruction:\n{s}" for s in pending_system)
        merged.append({"role": "user", "content": preamble})

    if not merged:
        return []

    # Ensure first turn is "user"
    first_role = gemini_role.get(merged[0]["role"], "user")
    if first_role != "user":
        merged.insert(0, {"role": "user", "content": ""})

    # Merge consecutive same-role turns; parts are plain strings
    contents: List[Dict] = []
    for msg in merged:
        g_role = gemini_role.get(msg["role"], "user")
        if contents and contents[-1]["role"] == g_role:
            sep = "\n" if contents[-1]["parts"][0] else ""
            contents[-1]["parts"][0] += sep + msg["content"]
        else:
            contents.append({"role": g_role, "parts": [msg["content"]]})

    # After a standalone system prelude (user turn with no real assistant reply),
    # append a synthetic "Understood." model turn if the last turn is "user"
    # and was generated from a system message (i.e. no real user content followed).
    # Detect: last turn role==user AND has "System instruction:" AND list len is odd
    # (user-only list, no assistant pair yet).
    if (
        len(contents) >= 1
        and contents[-1]["role"] == "user"
        and "System instruction:" in contents[-1]["parts"][0]
        and all(c["role"] != "model" for c in contents)
    ):
        contents.append({"role": "model", "parts": ["Understood."]})

    return contents


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
