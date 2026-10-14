"""
ethos-aegis-sdk — pip-installable Python client for the Ethos Aegis pipeline.

Wraps the core library with a clean, importable interface suitable for
installing in any Python project without needing the full repo on sys.path.

Install:
    pip install ethos-aegis-sdk   # (once published to PyPI)
    pip install -e sdk/python     # development install from repo

Usage::

    from ethos_aegis_sdk import AegisClient

    # HTTP mode works without the embedded core when a server is available.
    client = AegisClient(transport="http", server_url="https://example.test/v1/adjudicate")
    original = "user message"
    verdict = client.adjudicate(original)  # HTTP verdicts are dictionaries.

    # Fail closed if the verdict is missing clearance or has invalid sanitation.
    if (
        verdict.get("sanctified") is True
        and verdict.get("condemned") is False
        and (not verdict.get("sanitized") or isinstance(verdict.get("purified_payload"), str))
    ):
        purified = verdict.get("purified_payload")
        forward_to_llm(purified if isinstance(purified, str) else original)
    else:
        refuse()
"""

from importlib import import_module

from .client import AegisClient, AegisClientError, GuardedResponse

# Explicit adapter access remains compatible, but importing AegisClient for
# HTTP transport must never import the optional, locally installed core.
_ADAPTER_EXPORTS = frozenset(
    {
        "AnthropicAdapter",
        "BaseAdapter",
        "GeminiAdapter",
        "GeminiVertexAdapter",
        "GenericAdapter",
        "MistralAdapter",
        "OpenAIAdapter",
    }
)


def __getattr__(name: str):
    if name not in _ADAPTER_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # Only user-requested adapters load the separate ethos_aegis core.
    return getattr(import_module(".adapters", __name__), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | _ADAPTER_EXPORTS)

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
