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

    Pinned contract (test suite):
    - ``parts`` are plain strings, never ``{"text": "..."}`` dicts.
    - ``role: "system"`` never appears in output.
    - System text is ALWAYS emitted as a standalone user prelude entry,
      never folded into the content of a real user turn.

    Placement rules for system preludes:
    - **Before a following user turn** (leading or interleaved):
        emit [user(prelude), model("Understood.")] THEN the real user turn.
    - **Trailing after a model turn** (natural alternation already satisfied):
        emit [user(prelude)] — no Understood. added.
    - **Trailing after a user turn** (would create consecutive user turns):
        emit [model("Understood."), user(prelude)] to preserve alternation.
    - **Standalone (no real messages)**:
        emit [user(prelude), model("Understood.")].

    Other rules:
    - First turn must be ``"user"``. Leading assistant/model content gets a
      synthetic ``{"role": "user", "parts": [""]}`` prepended.
    - Consecutive same-role turns are merged with ``"\\n"``.
    """
    gemini_role = {"user": "user", "assistant": "model", "model": "model"}

    # --- Step 1: build an ordered event list ---
    # Each event is ('sys', text) or ('real', role, content)
    events: List[tuple] = []
    if system:
        events.append(('sys', system))
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            events.append(('sys', content))
        else:
            events.append(('real', role, content))

    # --- Step 2: group consecutive sys events and pair with context ---
    # Build a cleaned sequence: ('prelude', text) | ('real', gemini_role, content)
    cleaned: List[tuple] = []
    pending_sys: List[str] = []

    for ev in events:
        if ev[0] == 'sys':
            pending_sys.append(ev[1])
        else:
            if pending_sys:
                preamble = "\n".join(f"System instruction:\n{s}" for s in pending_sys)
                pending_sys = []
                cleaned.append(('prelude', preamble))
            _, role, content = ev
            cleaned.append(('real', gemini_role.get(role, 'user'), content))

    # Trailing sys
    if pending_sys:
        preamble = "\n".join(f"System instruction:\n{s}" for s in pending_sys)
        cleaned.append(('prelude', preamble))

    if not cleaned:
        return []

    # --- Step 3: emit Gemini contents with alternation rules ---
    # We build the final list by processing each cleaned item and
    # inserting synthetic turns as needed.
    out: List[Dict] = []

    def last_role() -> Optional[str]:
        return out[-1]["role"] if out else None

    def append_turn(role: str, text: str) -> None:
        """Append a turn, merging with previous if same role."""
        if out and out[-1]["role"] == role:
            sep = "\n" if out[-1]["parts"][0] else ""
            out[-1]["parts"][0] += sep + text
        else:
            out.append({"role": role, "parts": [text]})

    for i, item in enumerate(cleaned):
        if item[0] == 'prelude':
            preamble = item[1]
            # Look ahead: is there a following real user turn?
            next_real = None
            for j in range(i + 1, len(cleaned)):
                if cleaned[j][0] == 'real':
                    next_real = cleaned[j]
                    break

            if next_real is not None and next_real[1] == 'user':
                # Prelude before a real user turn:
                # emit [user(prelude), model(Understood.)] -- real user follows naturally
                if last_role() == 'user':
                    # maintain alternation
                    append_turn('model', 'Understood.')
                append_turn('user', preamble)
                append_turn('model', 'Understood.')
            elif next_real is None:
                # Trailing prelude (no more real messages)
                lr = last_role()
                if lr == 'user':
                    # user -> would create consecutive users -> insert model first
                    append_turn('model', 'Understood.')
                    append_turn('user', preamble)
                elif lr == 'model' or lr is None:
                    # natural: just append user prelude
                    append_turn('user', preamble)
                    # standalone (no prior content) -> add Understood.
                    if lr is None:
                        append_turn('model', 'Understood.')
            else:
                # Prelude before a real model turn (rare)
                if last_role() == 'user':
                    append_turn('model', 'Understood.')
                append_turn('user', preamble)

        else:
            # Real turn
            _, g_role, content = item
            # Ensure first turn is user
            if not out and g_role != 'user':
                append_turn('user', '')
            append_turn(g_role, content)

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

    def _effective_system(self, system: Optional[str]) -> Optional[str]:
        return system if system is not None else self._system_prompt

    @property
    def provider_name(self) -> str:
        return "gemini"

    def model_id(self) -> str:
        return self._model_id

    def supports_streaming(self) -> bool:
        return True

    def complete(self, messages, system=None, **kwargs) -> str:
        effective = self._effective_system(system)
        contents = _to_gemini_contents(messages, system=effective)
        config = self._genai.types.GenerationConfig(
            temperature=kwargs.get("temperature", self._temperature),
            max_output_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return self._model.generate_content(contents, generation_config=config).text or ""

    def stream(self, messages, system=None, **kwargs) -> Iterator[str]:
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

    def __init__(self, project: str, *, location: str = "us-central1",
                 model: str = DEFAULT_MODEL, temperature: float = 0.7,
                 max_tokens: int = 1024) -> None:
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

    def _effective_system(self, system):
        return system if system is not None else self._system_prompt

    @property
    def provider_name(self): return "gemini-vertex"
    def model_id(self): return self._model_id
    def supports_streaming(self): return True

    def complete(self, messages, system=None, **kwargs) -> str:
        from vertexai.generative_models import GenerationConfig
        contents = _to_gemini_contents(messages, system=self._effective_system(system))
        config = GenerationConfig(temperature=kwargs.get("temperature", self._temperature),
                                  max_output_tokens=kwargs.get("max_tokens", self._max_tokens))
        return self._model.generate_content(contents, generation_config=config).text or ""

    def stream(self, messages, system=None, **kwargs) -> Iterator[str]:
        from vertexai.generative_models import GenerationConfig
        contents = _to_gemini_contents(messages, system=self._effective_system(system))
        config = GenerationConfig(temperature=kwargs.get("temperature", self._temperature),
                                  max_output_tokens=kwargs.get("max_tokens", self._max_tokens))
        for chunk in self._model.generate_content(contents, generation_config=config, stream=True):
            if chunk.text:
                yield chunk.text
