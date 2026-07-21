"""
MistralAdapter -- Ethos Aegis adapter for the Mistral AI API.

pip install mistralai>=1.0
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional
from .base_adapter import BaseAdapter


class MistralAdapter(BaseAdapter):
    """Wraps the Mistral AI ChatCompletion API."""

    DEFAULT_MODEL = "mistral-large-latest"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        server_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
        **kwargs,
    ) -> None:
        try:
            from mistralai import Mistral
        except ImportError as exc:
            raise ImportError(
                "MistralAdapter requires: pip install mistralai>=1.0"
            ) from exc

        client_kwargs: dict = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if server_url:
            client_kwargs["server_url"] = server_url
        client_kwargs.update(kwargs)

        self._client        = Mistral(**client_kwargs)
        self._model         = model
        self._temperature   = temperature
        self._max_tokens    = max_tokens
        self._system_prompt = system_prompt

    # -- BaseAdapter interface ------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "mistral"

    def model_id(self) -> str:
        return self._model

    def supports_streaming(self) -> bool:
        return True

    def complete(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs,
    ) -> str:
        built = self._compose_messages(messages, system)
        response = self._client.chat.complete(
            model=self._model,
            messages=built,
            temperature=kwargs.get("temperature", self._temperature),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return response.choices[0].message.content or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        **kwargs,
    ) -> Iterator[str]:
        built = self._compose_messages(messages, system)
        with self._client.chat.stream(
            model=self._model,
            messages=built,
            temperature=kwargs.get("temperature", self._temperature),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
        ) as event_stream:
            for event in event_stream:
                delta = event.data.choices[0].delta.content if event.data.choices else None
                if delta:
                    yield delta

    # -- Helpers -------------------------------------------------------------

    def _compose_messages(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str],
    ) -> list[dict]:
        """Build the Mistral message list, resolving system instruction priority.

        Call-time ``system`` takes precedence over ``_system_prompt`` set at
        construction, so both are never applied simultaneously.
        """
        result: list[dict] = []
        effective = system if system is not None else self._system_prompt
        if effective:
            result.append({"role": "system", "content": effective})
        result.extend(messages)
        return result
