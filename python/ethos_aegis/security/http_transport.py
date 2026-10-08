"""Validate HTTP endpoint schemes shared by Generic and VeriFlow clients.

Enforces transport hygiene, not remote-server authorization or ownership.
"""
from __future__ import annotations

from urllib.parse import urlsplit


def validate_http_base_url(value: str) -> str:
    """Reject non-HTTP schemes, URL userinfo, and remote cleartext HTTP."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise ValueError("invalid HTTP endpoint")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HTTP endpoint must use a valid HTTP(S) URL without credentials or fragments")
    _ = parsed.port
    if parsed.scheme == "http" and parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("cleartext HTTP is supported for loopback development servers only")
    return value.rstrip("/")
