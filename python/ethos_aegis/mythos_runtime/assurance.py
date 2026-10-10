"""Authenticated, retained evidence for the Mythos-VeriFlow production bridge."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


class StateIntegrityError(RuntimeError):
    """Persisted state or evidence failed authenticity or storage checks."""


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


@dataclass(frozen=True)
class RetentionPolicy:
    max_events: int = 5000
    max_age_seconds: int = 7 * 24 * 3600
    resource_state_ttl_seconds: int = 24 * 3600
    max_resources: int = 500
    max_state_bytes: int = 8 * 1024 * 1024
    persist_rows: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.max_events <= 100_000:
            raise ValueError("max_events must be between 1 and 100000")
        if not 60 <= self.max_age_seconds <= 366 * 24 * 3600:
            raise ValueError("max_age_seconds must be between 60 seconds and 366 days")
        if not 60 <= self.resource_state_ttl_seconds <= 30 * 24 * 3600:
            raise ValueError("resource_state_ttl_seconds must be between 60 seconds and 30 days")
        if not 1 <= self.max_resources <= 10_000:
            raise ValueError("max_resources must be between 1 and 10000")
        if not 1024 <= self.max_state_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_state_bytes must be between 1 KiB and 64 MiB")


@contextmanager
def exclusive_file_lock(target: Path, *, timeout_seconds: float = 2.0):
    """Serialize writers with a fail-closed lock file; stale locks need operator cleanup."""
    if timeout_seconds <= 0:
        raise ValueError("lock timeout must be positive")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink():
        raise StateIntegrityError("state parent symlink is forbidden")
    lock_path = target.with_name(f".{target.name}.lock")
    if lock_path.is_symlink():
        raise StateIntegrityError("state lock symlink is forbidden")
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise StateIntegrityError("state writer lock is already held") from exc
            time.sleep(0.025)
    try:
        os.write(fd, f"{os.getpid()}\n".encode("ascii", errors="ignore"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


class SecureEvidenceLedger:
    """Atomic HMAC-authenticated bounded evidence ledger with explicit retention."""

    GENESIS = "0" * 64

    def __init__(self, path: str | Path, *, signing_key: bytes, retention: RetentionPolicy) -> None:
        if len(signing_key) < 32:
            raise ValueError("persistence signing key must be at least 32 bytes")
        self.path = Path(path)
        self._key = bytes(signing_key)
        self.retention = retention
        # Detect file removal after this ledger instance observed an existing file.
        # Cross-process anti-rollback still requires an external monotonic anchor.
        self._observed_ledger = self.path.exists()

    def _new_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": 2,
            "anchor_hash": self.GENESIS,
            "events": [],
        }
        self._seal_payload(payload)
        return payload

    def _seal_payload(self, payload: dict[str, Any]) -> None:
        """Authenticate the entire bounded ledger, not just surviving events."""
        events = payload["events"]
        payload["event_count"] = len(events)
        payload["head_hash"] = events[-1]["event_hash"] if events else payload["anchor_hash"]
        canonical = {key: value for key, value in payload.items() if key != "seal"}
        payload["seal"] = hmac.new(
            self._key, b"ethos-evidence-ledger-v2:" + _canonical(canonical), hashlib.sha256
        ).hexdigest()

    def _assert_safe_path(self) -> None:
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise StateIntegrityError("evidence ledger symlinks are forbidden")

    def _load(self) -> dict[str, Any]:
        self._assert_safe_path()
        if not self.path.exists():
            if self._observed_ledger:
                raise StateIntegrityError("evidence ledger disappeared after it was observed")
            return self._new_payload()
        self._observed_ledger = True
        if self.path.stat().st_size > self.retention.max_state_bytes:
            raise StateIntegrityError("evidence ledger exceeds configured size limit")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateIntegrityError("evidence ledger is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("version") != 2 or not isinstance(payload.get("events"), list):
            raise StateIntegrityError(
                "evidence ledger schema is invalid or legacy unsigned ledger needs operator-reviewed migration"
            )
        self._verify_payload(payload)
        return payload

    def _verify_payload(self, payload: Mapping[str, Any]) -> None:
        required = {"version", "anchor_hash", "events", "event_count", "head_hash", "seal"}
        if set(payload) != required or payload.get("version") != 2:
            raise StateIntegrityError("signed evidence ledger envelope is missing or invalid")
        events = payload["events"]
        if not isinstance(events, list) or type(payload["event_count"]) is not int:
            raise StateIntegrityError("signed evidence ledger count is invalid")
        if payload["event_count"] != len(events):
            raise StateIntegrityError("evidence ledger event count was modified")
        seal = payload["seal"]
        if not isinstance(seal, str):
            raise StateIntegrityError("evidence ledger envelope signature is missing")
        unsigned = {key: value for key, value in payload.items() if key != "seal"}
        expected_seal = hmac.new(
            self._key, b"ethos-evidence-ledger-v2:" + _canonical(unsigned), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(seal, expected_seal):
            raise StateIntegrityError("evidence ledger envelope authentication failed")
        previous = str(payload.get("anchor_hash") or self.GENESIS)
        for event in payload.get("events", []):
            if not isinstance(event, dict) or event.get("previous_hash") != previous:
                raise StateIntegrityError("evidence ledger hash chain is invalid")
            event_hash = event.get("event_hash")
            signature = event.get("signature")
            canonical_event = dict(event)
            canonical_event.pop("event_hash", None)
            canonical_event.pop("signature", None)
            expected_hash = hashlib.sha256(_canonical(canonical_event)).hexdigest()
            if not isinstance(event_hash, str) or not hmac.compare_digest(event_hash, expected_hash):
                raise StateIntegrityError("evidence ledger event hash is invalid")
            expected_signature = hmac.new(self._key, event_hash.encode("ascii"), hashlib.sha256).hexdigest()
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected_signature):
                raise StateIntegrityError("evidence ledger signature is invalid")
            previous = event_hash
        if not isinstance(payload["head_hash"], str) or not hmac.compare_digest(
            payload["head_hash"], previous
        ):
            raise StateIntegrityError("evidence ledger authenticated head is inconsistent")

    def _write(self, payload: Mapping[str, Any]) -> None:
        self._assert_safe_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise StateIntegrityError("evidence ledger parent symlink is forbidden")
        encoded = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True).encode("utf-8") + b"\n"
        if len(encoded) > self.retention.max_state_bytes:
            raise StateIntegrityError("evidence ledger would exceed configured size limit")
        temporary: str | None = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            if os.name == "posix":
                self.path.chmod(0o600)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def append(
        self,
        *,
        event_type: str,
        action: str,
        resource_id: str,
        subject: str,
        decision: str,
        metadata: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _utc(now)
        with exclusive_file_lock(self.path):
            payload = self._load()
            events = list(payload["events"])
            cutoff = current - timedelta(seconds=self.retention.max_age_seconds)
            first_keep = 0
            while first_keep < len(events) and _parse_time(str(events[first_keep]["timestamp"])) < cutoff:
                first_keep += 1
            if first_keep:
                payload["anchor_hash"] = events[first_keep - 1]["event_hash"]
                events = events[first_keep:]
            if len(events) >= self.retention.max_events:
                remove = len(events) - self.retention.max_events + 1
                payload["anchor_hash"] = events[remove - 1]["event_hash"]
                events = events[remove:]
            clean_meta = dict(metadata or {})
            if len(_canonical(clean_meta)) > 8192:
                raise ValueError("evidence metadata exceeds 8 KiB")
            previous = events[-1]["event_hash"] if events else payload["anchor_hash"]
            event = {
                "version": 1,
                "event_id": f"mvr_{secrets.token_hex(12)}",
                "timestamp": _iso(current),
                "event_type": event_type,
                "action": action,
                "resource_id": resource_id,
                "subject": subject,
                "decision": decision,
                "metadata": clean_meta,
                "previous_hash": previous,
            }
            event_hash = hashlib.sha256(_canonical(event)).hexdigest()
            event["event_hash"] = event_hash
            event["signature"] = hmac.new(self._key, event_hash.encode("ascii"), hashlib.sha256).hexdigest()
            events.append(event)
            payload["events"] = events
            self._seal_payload(payload)
            self._verify_payload(payload)
            self._write(payload)
            self._observed_ledger = True
            return dict(event)

    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(x) for x in self._load()["events"])

    def verify(self) -> bool:
        if not self.path.exists():
            raise StateIntegrityError("evidence ledger file does not exist")
        self._load()
        return True
