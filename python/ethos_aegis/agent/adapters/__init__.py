"""
Ethos Aegis — AI Provider Adapters

Available adapters:
    OpenAIAdapter     — OpenAI, Azure OpenAI, OpenRouter, Groq, Together AI
    AnthropicAdapter  — Anthropic Claude models
    MistralAdapter    — Mistral AI Cloud + self-hosted
    GeminiAdapter     — Google Gemini via AI Studio
    GeminiVertexAdapter — Google Gemini via Vertex AI
    GenericAdapter    — Any OpenAI-compatible HTTP endpoint (zero deps)
"""

from .base_adapter      import BaseAdapter
from .openai_adapter    import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter
from .mistral_adapter   import MistralAdapter
from .gemini_adapter    import GeminiAdapter, GeminiVertexAdapter
from .generic_adapter   import GenericAdapter

__all__ = [
    "BaseAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "MistralAdapter",
    "GeminiAdapter",
    "GeminiVertexAdapter",
    "GenericAdapter",
]
