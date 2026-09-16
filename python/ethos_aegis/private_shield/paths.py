"""Cross-platform path canonicalization for AEGIS policy matching.

Policy paths live in one POSIX-like namespace regardless of host OS. Host-specific
absolute paths, traversal segments, UNC paths, Windows drive paths, NTFS alternate
data-stream syntax, and Windows reserved device names are rejected before matching.
"""
from __future__ import annotations

import re


class PathPolicyError(ValueError):
    """Raised when a path cannot safely enter the AEGIS policy namespace."""


_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def canonicalize_resource_path(raw_path: str) -> str:
    """Normalize an untrusted resource path into the AEGIS virtual namespace."""

    return _canonicalize(raw_path, allow_glob=False)


def canonicalize_scope_pattern(raw_scope: str) -> str:
    """Normalize a trusted policy scope while preserving glob metacharacters."""

    if raw_scope == "*":
        return "*"
    return _canonicalize(raw_scope, allow_glob=True)


def _canonicalize(raw_value: str, *, allow_glob: bool) -> str:
    if not isinstance(raw_value, str):
        raise PathPolicyError("path must be a string")
    if "\x00" in raw_value:
        raise PathPolicyError("NUL bytes are forbidden")

    value = raw_value.replace("\\", "/")
    if value.startswith("/") or value.startswith("//"):
        raise PathPolicyError("absolute and UNC paths are forbidden")
    if _DRIVE_PATH.match(value):
        raise PathPolicyError("Windows drive paths are forbidden")

    canonical: list[str] = []
    for segment in value.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise PathPolicyError("parent traversal is forbidden")
        if ":" in segment:
            raise PathPolicyError("colon syntax is forbidden in policy paths")
        if not allow_glob and any(char in segment for char in "*?["):
            raise PathPolicyError("resource paths cannot contain glob metacharacters")
        if segment.endswith((".", " ")):
            raise PathPolicyError("trailing dots/spaces are forbidden")
        stem = segment.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise PathPolicyError("Windows reserved device name is forbidden")
        canonical.append(segment)

    return "/".join(canonical)
