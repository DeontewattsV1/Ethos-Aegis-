"""
MistralAdapter -- Ethos Aegis adapter for the Mistral AI API.

Supports all Mistral chat-completion models via the official SDK or raw HTTP.
Compatible with: Mistral AI Cloud, Mistral self-hosted, La Plateforme.

pip install mistralai>=1.0
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional
from .base_adapter import BaseAdapter


class MistralAdapter(BaseAdapter):
    """
    Wraps the Mistral AI ChatCompletion API.

    Args:
        api_key:       Mistral API key (or set MISTRAL_API_KEY env var).
        model:         Mistral model ID. Default: "mistral-large-latest".
        server_url:    Override base URL for self-hosted endpoints.
        temperature:   Sampling temperature. Default: 0.7.
        max_tokens:    Max tokens to generate. Default: 1024.
        system_prompt: Optional system message prepended to every conversation.
        **kwargs:      Forwarded to the Mistral client constructor.
    """

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
        """Complete a conversation.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            system:   Optional system prompt override.
            **kwargs: ``temperature``, ``max_tokens`` overrides.
        """
        built = self._build_messages(messages, system=system)
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
        """Stream a completion.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            system:   Optional system prompt override.
            **kwargs: ``temperature``, ``max_tokens`` overrides.
        """
        built = self._build_messages(messages, system=system)
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

    def _build_messages(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
    ) -> list[dict]:
        result: list[dict] = []
        effective_system = system or self._system_prompt
        if effective_system:
            result.append({"role": "system", "content": effective_system})
        result.extend(messages)
        return result
