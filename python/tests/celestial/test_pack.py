"""Tests for the Agent Specification Pack (AES-GCM + Ed25519)."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

pytest.importorskip("cryptography")

from ethos_aegis.celestial.pack import (  # noqa: E402  (import after importorskip)
    AgentSpecCrypto,
    EncryptedAgentPack,
)

SAMPLE_SPEC: dict[str, Any] = {
    "schema_version": "1.0",
    "creator": "ethos-aegis-test",
    "system_role": "policy-guardian",
    "use_case": "verify agent blueprints before deployment",
    "business_goal": "tamper-evident agent packaging",
    "users": ["security-team"],
    "inputs": ["agent_spec.json"],
    "tools": ["AES-GCM", "Ed25519"],
    "responsibilities": ["sign manifest", "encrypt payload"],
    "memory_requirements": "stateless",
    "constraints": {
        "tech_stack": "Python 3.10+",
        "model_provider": "n/a",
        "budget": "low",
        "latency": "<100ms",
        "security_privacy": "high",
        "deployment_target": "containerised",
    },
    "required_output": ["EncryptedAgentPack"],
    "success_criteria": "round-trip verify_and_decrypt passes",
}

PASSPHRASE = "correct horse battery staple"


class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_original_spec(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        restored = AgentSpecCrypto.verify_and_decrypt(pack, PASSPHRASE)
        assert restored == SAMPLE_SPEC

    def test_pack_to_dict_and_back(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        roundtripped = EncryptedAgentPack.from_dict(pack.to_dict())
        assert AgentSpecCrypto.verify_and_decrypt(roundtripped, PASSPHRASE) == SAMPLE_SPEC

    def test_manifest_carries_expected_fields(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        manifest = pack.manifest
        for field in (
            "schema_version",
            "creator",
            "public_key_b64",
            "spec_hash_sha256",
            "ciphertext_hash_sha256",
            "nonce_b64",
            "salt_b64",
            "content_type",
        ):
            assert field in manifest, f"missing manifest field: {field}"
        assert manifest["content_type"] == "agent_spec"
        assert manifest["creator"] == "ethos-aegis-test"


class TestTamperDetection:
    def test_wrong_passphrase_fails(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        with pytest.raises(ValueError, match="decryption failed"):
            AgentSpecCrypto.verify_and_decrypt(pack, "the wrong passphrase")

    def test_tampered_ciphertext_fails_signature(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        # Flip one byte of the ciphertext.
        raw = bytearray(base64.b64decode(pack.ciphertext_b64))
        raw[0] ^= 0xFF
        pack.ciphertext_b64 = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(ValueError, match="signature is invalid|hash mismatch"):
            AgentSpecCrypto.verify_and_decrypt(pack, PASSPHRASE)

    def test_tampered_manifest_fails_signature(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        pack.manifest["creator"] = "an-impostor"
        with pytest.raises(ValueError, match="signature is invalid"):
            AgentSpecCrypto.verify_and_decrypt(pack, PASSPHRASE)


class TestIdentityReuse:
    def test_restore_key_pair_from_private_key_b64(self) -> None:
        original = AgentSpecCrypto()
        clone = AgentSpecCrypto.from_private_key_b64(original.private_key_b64())
        assert clone.public_key_b64() == original.public_key_b64()

        # A pack from the original must verify with the clone's verifier path
        # (the manifest carries the public key, so any verifier works — but
        # this also catches accidental key-pair drift).
        pack = original.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        assert AgentSpecCrypto.verify_and_decrypt(pack, PASSPHRASE) == SAMPLE_SPEC

        pack2 = clone.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        assert pack2.manifest["public_key_b64"] == pack.manifest["public_key_b64"]


class TestInputValidation:
    def test_empty_passphrase_rejected(self) -> None:
        crypto = AgentSpecCrypto()
        with pytest.raises(ValueError):
            crypto.encrypt_spec(SAMPLE_SPEC, "")


class TestSerialisation:
    def test_pack_serialises_as_pure_json(self) -> None:
        crypto = AgentSpecCrypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, PASSPHRASE)
        blob = json.dumps(pack.to_dict())
        # Should be re-loadable from a plain JSON file (the CLI does this).
        restored = EncryptedAgentPack.from_dict(json.loads(blob))
        assert AgentSpecCrypto.verify_and_decrypt(restored, PASSPHRASE) == SAMPLE_SPEC
