"""
ethos-aegis-sdk — pip-installable Python client for the Ethos Aegis pipeline.

Wraps the core library with a clean, importable interface suitable for
installing in any Python project without needing the full repo on sys.path.

Install:
    pip install ethos-aegis-sdk   # (once published to PyPI)
    pip install -e sdk/python     # development install from repo

Usage::

    from ethos_aegis_sdk import AegisClient

    client = AegisClient()
    verdict = client.adjudicate("user message")

    if verdict.is_condemned:
        refuse()
    else:
        forward_to_llm(verdict.purified_payload or original)
"""

from .adapters import (
    AnthropicAdapter,
    BaseAdapter,
    GeminiAdapter,
    GeminiVertexAdapter,
    GenericAdapter,
    MistralAdapter,
    OpenAIAdapter,
)
from .client import AegisClient, AegisClientError, GuardedResponse

__version__ = "1.0.0"
__all__ = [
    "AegisClient",
    "AegisClientError",
    "GuardedResponse",
    "BaseAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "MistralAdapter",
    "GeminiAdapter",
    "GeminiVertexAdapter",
    "GenericAdapter",
]
