"""Tests for the Agent Specification Pack (AES-GCM + Ed25519)."""

from __future__ import annotations

import base64
import json
import secrets
from typing import Any

import pytest

pytest.importorskip("cryptography")

from ethos_aegis.celestial.pack import (  # noqa: E402  (import after importorskip)
    AgentSpecCrypto,
    EncryptedAgentPack,
)

# Use the RFC 7914 interactive baseline (N=2**14) in tests so the suite
# stays fast; production code uses OWASP's recommended N=2**17 by default.
_TEST_SCRYPT_N = 2**14


def _new_crypto() -> AgentSpecCrypto:
    return AgentSpecCrypto(scrypt_n=_TEST_SCRYPT_N)


@pytest.fixture
def passphrase() -> str:
    """Fresh random passphrase per test — avoids hardcoded credentials."""
    return secrets.token_urlsafe(32)

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

class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_original_spec(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        restored = AgentSpecCrypto.verify_and_decrypt(pack, passphrase)
        assert restored == SAMPLE_SPEC

    def test_pack_to_dict_and_back(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        roundtripped = EncryptedAgentPack.from_dict(pack.to_dict())
        assert AgentSpecCrypto.verify_and_decrypt(roundtripped, passphrase) == SAMPLE_SPEC

    def test_manifest_carries_expected_fields(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
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
            "kdf",
        ):
            assert field in manifest, f"missing manifest field: {field}"
        assert manifest["content_type"] == "agent_spec"
        assert manifest["creator"] == "ethos-aegis-test"
        assert manifest["kdf"]["name"] == "scrypt"
        assert manifest["kdf"]["n"] == _TEST_SCRYPT_N


class TestTamperDetection:
    def test_wrong_passphrase_fails(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        with pytest.raises(ValueError, match="decryption failed"):
            AgentSpecCrypto.verify_and_decrypt(pack, secrets.token_urlsafe(32))

    def test_tampered_ciphertext_fails_signature(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        # Flip one byte of the ciphertext.
        raw = bytearray(base64.b64decode(pack.ciphertext_b64))
        raw[0] ^= 0xFF
        pack.ciphertext_b64 = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(ValueError, match="signature is invalid|hash mismatch"):
            AgentSpecCrypto.verify_and_decrypt(pack, passphrase)

    def test_tampered_manifest_fails_signature(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        pack.manifest["creator"] = "an-impostor"
        with pytest.raises(ValueError, match="signature is invalid"):
            AgentSpecCrypto.verify_and_decrypt(pack, passphrase)


class TestIdentityReuse:
    def test_restore_key_pair_from_private_key_b64(self, passphrase: str) -> None:
        original = _new_crypto()
        clone = AgentSpecCrypto.from_private_key_b64(
            original.private_key_b64(), scrypt_n=_TEST_SCRYPT_N
        )
        assert clone.public_key_b64() == original.public_key_b64()

        # A pack from the original must verify with the clone's verifier path
        # (the manifest carries the public key, so any verifier works — but
        # this also catches accidental key-pair drift).
        pack = original.encrypt_spec(SAMPLE_SPEC, passphrase)
        assert AgentSpecCrypto.verify_and_decrypt(pack, passphrase) == SAMPLE_SPEC

        pack2 = clone.encrypt_spec(SAMPLE_SPEC, passphrase)
        assert pack2.manifest["public_key_b64"] == pack.manifest["public_key_b64"]


class TestInputValidation:
    def test_empty_passphrase_rejected(self) -> None:
        crypto = _new_crypto()
        with pytest.raises(ValueError):
            crypto.encrypt_spec(SAMPLE_SPEC, "")

    def test_invalid_scrypt_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="scrypt_n must be a power of two"):
            AgentSpecCrypto(scrypt_n=1000)
        with pytest.raises(ValueError, match="scrypt_n must be a power of two"):
            AgentSpecCrypto(scrypt_n=2**10)  # below the minimum floor


class TestSerialisation:
    def test_pack_serialises_as_pure_json(self, passphrase: str) -> None:
        crypto = _new_crypto()
        pack = crypto.encrypt_spec(SAMPLE_SPEC, passphrase)
        blob = json.dumps(pack.to_dict())
        # Should be re-loadable from a plain JSON file (the CLI does this).
        restored = EncryptedAgentPack.from_dict(json.loads(blob))
        assert AgentSpecCrypto.verify_and_decrypt(restored, passphrase) == SAMPLE_SPEC
