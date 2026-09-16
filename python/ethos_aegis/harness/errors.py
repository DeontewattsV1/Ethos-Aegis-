"""
harness/errors.py — Component 8: Layered error handling strategy.

Implements the four LangGraph error categories and Stripe's production
retry pattern (max 2 retries). Critical insight: a 10-step process with
99% per-step success = ~90.4% end-to-end. Errors compound fast.

Categories:
  TRANSIENT       — retry with backoff (network, rate limit)
  LLM_RECOVERABLE — return as ToolMessage so the model can self-correct
  USER_FIXABLE    — interrupt for human input
  UNEXPECTED      — bubble up immediately for debugging
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Callable, Optional, Tuple, Type

_log = logging.getLogger("HarnessErrors")


class ErrorCategory(str, Enum):
    TRANSIENT        = "transient"
    LLM_RECOVERABLE  = "llm_recoverable"
    USER_FIXABLE     = "user_fixable"
    UNEXPECTED       = "unexpected"


# Exception type → category mapping (extend as needed)
_CATEGORY_MAP: list[Tuple[Tuple[Type[Exception], ...], ErrorCategory]] = [
    # Transient
    ((ConnectionError, TimeoutError, OSError), ErrorCategory.TRANSIENT),
    # LLM-recoverable (validation, parsing, known tool failures)
    ((ValueError, KeyError, json_err := type("JSONDecodeError", (ValueError,), {})),
     ErrorCategory.LLM_RECOVERABLE),
]


def classify(exc: Exception) -> ErrorCategory:
    import json
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return ErrorCategory.TRANSIENT
    if isinstance(exc, (ValueError, KeyError, json.JSONDecodeError)):
        return ErrorCategory.LLM_RECOVERABLE
    if isinstance(exc, PermissionError):
        return ErrorCategory.USER_FIXABLE
    return ErrorCategory.UNEXPECTED


def with_retry(fn: Callable, max_retries: int = 2,
               category: ErrorCategory = ErrorCategory.TRANSIENT):
    """
    Retry decorator for transient errors with exponential backoff.
    Stripe production pattern: max 2 retries.
    """
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                cat = classify(exc)
                if cat != ErrorCategory.TRANSIENT or attempt == max_retries:
                    raise
                wait = 0.5 * (2 ** attempt)
                _log.warning("Transient error (attempt %d/%d), retrying in %.1fs: %s",
                             attempt + 1, max_retries + 1, wait, exc)
                time.sleep(wait)
                last_exc = exc
        raise last_exc  # unreachable but satisfies type checkers
    return wrapper


class HarnessError(RuntimeError):
    """Base for all harness-level errors."""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNEXPECTED) -> None:
        super().__init__(message)
        self.category = category


class ToolExecutionError(HarnessError):
    """Raised when a tool fails in a way that should be fed back to the model."""
    def __init__(self, tool_name: str, detail: str) -> None:
        super().__init__(f"Tool '{tool_name}' error: {detail}", ErrorCategory.LLM_RECOVERABLE)
        self.tool_name = tool_name
        self.detail    = detail

    def as_tool_message(self) -> str:
        """Format for injection as a ToolMessage so the model can self-correct."""
        return f"ERROR from tool '{self.tool_name}': {self.detail}\nPlease adjust your approach."
