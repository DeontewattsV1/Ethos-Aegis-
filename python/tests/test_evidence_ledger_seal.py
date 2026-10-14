"""Fail-closed regressions for the authenticated Mythos evidence-ledger head.

These tests use synthetic records only. Full rollback protection across a
new process requires an independently protected, monotonic external anchor.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ethos_aegis.mythos_runtime.assurance import (
    RetentionPolicy,
    SecureEvidenceLedger,
    StateIntegrityError,
)

KEY = b"evidence-ledger-test-key-" + b"x" * 32
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _ledger(tmp_path, *, max_events=12):
    return SecureEvidenceLedger(
        tmp_path / "ledger.json",
        signing_key=KEY,
        retention=RetentionPolicy(max_events=max_events),
    )


def _append(ledger, action):
    return ledger.append(
        event_type="authorization",
        action=action,
        resource_id="synthetic-resource",
        subject="test-operator",
        decision="ALLOW",
        metadata={"fixture": True},
        now=NOW,
    )


def test_append_and_retention_keep_authenticated_head_and_count(tmp_path):
    ledger = _ledger(tmp_path, max_events=2)
    for action in ("read", "refresh", "answer"):
        _append(ledger, action)
    stored = json.loads(ledger.path.read_text(encoding="utf-8"))
    assert stored["version"] == 2
    assert stored["event_count"] == 2
    assert len(stored["events"]) == 2
    assert stored["head_hash"] == stored["events"][-1]["event_hash"]
    assert len(stored["seal"]) == 64
    assert ledger.verify() is True
    assert [event["action"] for event in ledger.events()] == ["refresh", "answer"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda stored: stored["events"].pop(),
        lambda stored: stored["events"].clear(),
        lambda stored: stored.update({"event_count": 0}),
        lambda stored: stored.update({"head_hash": "0" * 64}),
        lambda stored: stored.update({"anchor_hash": "f" * 64}),
        lambda stored: stored.pop("seal"),
    ],
    ids=[
        "delete-most-recent",
        "erase-all-events",
        "rewrite-count",
        "rewrite-head",
        "rewrite-anchor",
        "delete-seal",
    ],
)
def test_persisted_ledger_edits_are_detected(tmp_path, mutation):
    ledger = _ledger(tmp_path)
    _append(ledger, "read")
    _append(ledger, "answer")
    stored = json.loads(ledger.path.read_text(encoding="utf-8"))
    mutation(stored)
    ledger.path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(StateIntegrityError):
        ledger.verify()
    with pytest.raises(StateIntegrityError):
        ledger.events()
    with pytest.raises(StateIntegrityError):
        _append(ledger, "more")


def test_legacy_unsigned_history_never_silently_reauthenticated(tmp_path):
    ledger = _ledger(tmp_path)
    _append(ledger, "read")
    stored = json.loads(ledger.path.read_text(encoding="utf-8"))
    stored["version"] = 1
    for field in ("event_count", "head_hash", "seal"):
        stored.pop(field)
    ledger.path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(StateIntegrityError, match="legacy unsigned"):
        ledger.verify()


def test_wrong_key_rejects_already_signed_history(tmp_path):
    ledger = _ledger(tmp_path)
    _append(ledger, "read")
    incorrect = SecureEvidenceLedger(
        ledger.path,
        signing_key=b"different-operator-key-" + b"z" * 32,
        retention=RetentionPolicy(),
    )
    with pytest.raises(StateIntegrityError, match="authentication failed"):
        incorrect.verify()


def test_removed_ledger_is_not_a_verified_empty_chain(tmp_path):
    ledger = _ledger(tmp_path)
    _append(ledger, "read")
    ledger.path.unlink()
    with pytest.raises(StateIntegrityError, match="does not exist"):
        ledger.verify()
    with pytest.raises(StateIntegrityError, match="disappeared"):
        _append(ledger, "more")
