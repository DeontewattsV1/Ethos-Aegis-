"""Tamper-evident authorization receipts for AEGIS Private Shield."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

from .models import ActionRequest, PolicyDecision


@dataclass(frozen=True)
class AuditReceipt:
    receipt_id: str
    timestamp: str
    subject: str
    action: str
    resource: str
    decision: str
    reasons: tuple[str, ...]
    capability_ids: tuple[str, ...]
    risk: float
    input_hash: str
    output_hash: str
    previous_receipt_hash: str
    receipt_hash: str
    signature: str


class AuditChain:
    """Append-only, HMAC-authenticated receipt chain.

    HMAC-SHA256 keeps the v0.1 reference implementation dependency-free. A
    production deployment should place the signing key behind KMS/HSM and may
    replace HMAC with an asymmetric signature for externally verifiable receipts.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, signing_key: bytes) -> None:
        if len(signing_key) < 16:
            raise ValueError("signing_key must be at least 16 bytes")
        self._signing_key = signing_key
        self._receipts: list[AuditReceipt] = []

    @property
    def receipts(self) -> tuple[AuditReceipt, ...]:
        return tuple(self._receipts)

    def append(
        self,
        request: ActionRequest,
        decision: PolicyDecision,
        *,
        input_material: bytes | str = b"",
        output_material: bytes | str = b"",
        timestamp: datetime | None = None,
    ) -> AuditReceipt:
        timestamp = timestamp or datetime.now(timezone.utc)
        previous_hash = self._receipts[-1].receipt_hash if self._receipts else self.GENESIS_HASH
        payload = {
            "receipt_id": f"agr_{secrets.token_hex(8)}",
            "timestamp": timestamp.isoformat(),
            "subject": request.subject,
            "action": request.action,
            "resource": request.resource,
            "decision": decision.decision.value,
            "reasons": list(decision.reasons),
            "capability_ids": list(decision.capability_ids),
            "risk": decision.risk,
            "input_hash": self._hash_material(input_material),
            "output_hash": self._hash_material(output_material),
            "previous_receipt_hash": previous_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        receipt_hash = hashlib.sha256(canonical).hexdigest()
        signature = hmac.new(self._signing_key, receipt_hash.encode(), hashlib.sha256).hexdigest()
        receipt = AuditReceipt(
            receipt_id=payload["receipt_id"],
            timestamp=payload["timestamp"],
            subject=payload["subject"],
            action=payload["action"],
            resource=payload["resource"],
            decision=payload["decision"],
            reasons=tuple(payload["reasons"]),
            capability_ids=tuple(payload["capability_ids"]),
            risk=payload["risk"],
            input_hash=payload["input_hash"],
            output_hash=payload["output_hash"],
            previous_receipt_hash=payload["previous_receipt_hash"],
            receipt_hash=receipt_hash,
            signature=signature,
        )
        self._receipts.append(receipt)
        return receipt

    def verify(self, receipts: Iterable[AuditReceipt] | None = None) -> bool:
        previous = self.GENESIS_HASH
        for receipt in tuple(receipts) if receipts is not None else self.receipts:
            if receipt.previous_receipt_hash != previous:
                return False
            payload = asdict(receipt)
            supplied_hash = payload.pop("receipt_hash")
            supplied_signature = payload.pop("signature")
            payload["reasons"] = list(payload["reasons"])
            payload["capability_ids"] = list(payload["capability_ids"])
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            expected_hash = hashlib.sha256(canonical).hexdigest()
            if not hmac.compare_digest(supplied_hash, expected_hash):
                return False
            expected_signature = hmac.new(self._signing_key, supplied_hash.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                return False
            previous = supplied_hash
        return True

    @staticmethod
    def _hash_material(material: bytes | str) -> str:
        raw = material.encode() if isinstance(material, str) else material
        return hashlib.sha256(raw).hexdigest()
