"""Operator-controlled scope checks. This is not an OS sandbox or identity proof."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ToolId, ToolkitError


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ToolkitError("Scope lists must contain nonempty strings.")
    return tuple(value)


@dataclass(frozen=True)
class AssessmentScope:
    authorization_reference: str
    expires_at: datetime
    allowed_tools: tuple[ToolId, ...]
    local_roots: tuple[Path, ...]
    usernames: tuple[str, ...] = ()
    sites: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()
    allow_execution: bool = False
    allow_network: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssessmentScope:
        try:
            ref = data["authorization_reference"]
            if not isinstance(ref, str) or not ref.strip():
                raise ToolkitError("An authorization reference is required.")
            expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ToolkitError("Scope expiry must include a timezone.")
            execution, network = data.get("allow_execution", False), data.get("allow_network", False)
            if type(execution) is not bool or type(network) is not bool:
                raise ToolkitError("Execution and network grants must be booleans.")
            roots = _strings(data.get("local_roots", []))
            if any(not Path(root).is_absolute() for root in roots):
                raise ToolkitError("Local roots must be absolute paths.")
            return cls(
                authorization_reference=ref,
                expires_at=expiry,
                allowed_tools=tuple(ToolId(x) for x in _strings(data.get("allowed_tools", []))),
                local_roots=tuple(Path(x).resolve(strict=True) for x in roots),
                usernames=_strings(data.get("usernames", [])),
                sites=_strings(data.get("sites", [])),
                hosts=tuple(x.lower().rstrip(".") for x in _strings(data.get("hosts", []))),
                devices=_strings(data.get("devices", [])),
                allow_execution=execution,
                allow_network=network,
            )
        except (KeyError, TypeError, ValueError, OSError, AttributeError) as exc:
            if isinstance(exc, ToolkitError):
                raise
            raise ToolkitError("Invalid assessment scope.") from None

    def check(self, tool: ToolId, *, execute: bool = False, network: bool = False) -> None:
        if datetime.now(timezone.utc) >= self.expires_at:
            raise ToolkitError("Assessment scope has expired.")
        if tool not in self.allowed_tools:
            raise ToolkitError("Tool is outside the assessment scope.")
        if execute and not self.allow_execution:
            raise ToolkitError("Tool execution is not authorized.")
        if network and not self.allow_network:
            raise ToolkitError("Network access is not authorized.")

    def local_path(self, path: str | Path, *, directory: bool = False) -> Path:
        try:
            target = Path(path).resolve(strict=True)
        except (OSError, ValueError):
            raise ToolkitError("Local target does not exist.") from None
        if not any(target == root or root in target.parents for root in self.local_roots):
            raise ToolkitError("Local target is outside the assessment scope.")
        if (directory and not target.is_dir()) or (not directory and not target.is_file()):
            raise ToolkitError("Local target has the wrong file type.")
        return target

    def username(self, username: str) -> None:
        if username not in self.usernames or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username):
            raise ToolkitError("Username is outside the assessment scope.")
        if not self.sites or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", x) for x in self.sites):
            raise ToolkitError("Explicit, valid Sherlock site names are required.")

    def host(self, host: str) -> str:
        normalized = host.lower().rstrip(".")
        if normalized not in self.hosts or not re.fullmatch(r"[a-z0-9.-]{1,253}", normalized):
            raise ToolkitError("Host is outside the assessment scope.")
        return normalized
