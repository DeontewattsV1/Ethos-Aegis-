"""
Agent Specification Pack — signed, encrypted bundles for agent blueprints
=========================================================================

Wraps a JSON agent specification in two cryptographic layers:

1. **AES-GCM** encryption of canonical-JSON plaintext, keyed by a
   passphrase-derived **scrypt** key.  Confidentiality + integrity for
   the spec body.
2. **Ed25519** signature over the manifest *concatenated* with the raw
   ciphertext.  Anyone with the manifest's embedded public key can
   verify creator attribution and detect tampering of either half of
   the pack — without needing the passphrase.

The manifest carries SHA-256 hashes of both the canonical plaintext and
the ciphertext, plus the nonce and salt, so verifiers can detect
corruption *before* attempting decryption.

This module requires the third-party `cryptography` package
(``pip install 'ethos-aegis[celestial]'``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# scrypt parameters per RFC 7914 §2 (interactive use; ~16 MiB of memory).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32
_NONCE_LEN = 12
_SALT_LEN = 16


def _canonical_json(data: dict[str, Any]) -> bytes:
    """Deterministic JSON serialisation: sorted keys, no whitespace."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """scrypt-based KDF producing a 32-byte AES-256-GCM key."""
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(passphrase.encode("utf-8"))


@dataclass
class EncryptedAgentPack:
    """All bytes needed to verify and decrypt an agent specification.

    Attributes
    ----------
    manifest:
        Public metadata: schema version, creator, public key, hashes,
        nonce, salt.  Carried in cleartext so verifiers can inspect
        provenance before decrypting.
    ciphertext_b64:
        AES-GCM ciphertext (includes the 16-byte authentication tag),
        base64-encoded.
    nonce_b64:
        12-byte AES-GCM nonce, base64-encoded.  Mirrored inside the
        manifest under ``nonce_b64`` for self-contained verification.
    salt_b64:
        16-byte scrypt salt, base64-encoded.  Also mirrored in the
        manifest.
    signature_b64:
        Ed25519 signature over ``canonical_json(manifest) || ciphertext``.
    """

    manifest: dict[str, Any]
    ciphertext_b64: str
    nonce_b64: str
    salt_b64: str
    signature_b64: str

    def to_dict(self) -> dict[str, Any]:
        """Serialise the pack as a single JSON-friendly dict."""
        return {
            "manifest": self.manifest,
            "ciphertext_b64": self.ciphertext_b64,
            "nonce_b64": self.nonce_b64,
            "salt_b64": self.salt_b64,
            "signature_b64": self.signature_b64,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EncryptedAgentPack:
        """Inverse of :meth:`to_dict`."""
        return cls(
            manifest=payload["manifest"],
            ciphertext_b64=payload["ciphertext_b64"],
            nonce_b64=payload["nonce_b64"],
            salt_b64=payload["salt_b64"],
            signature_b64=payload["signature_b64"],
        )


class AgentSpecCrypto:
    """Encrypt + sign and verify + decrypt agent specifications.

    An instance owns an Ed25519 key pair (random by default).  Pass in
    your own ``private_key`` to reuse a long-lived identity.
    """

    def __init__(self, private_key: ed25519.Ed25519PrivateKey | None = None) -> None:
        self.private_key: ed25519.Ed25519PrivateKey = (
            private_key or ed25519.Ed25519PrivateKey.generate()
        )
        self.public_key: ed25519.Ed25519PublicKey = self.private_key.public_key()

    # ── Identity helpers ─────────────────────────────────────────────────────

    def public_key_b64(self) -> str:
        """Return the Ed25519 public key encoded as 32 raw bytes in base64."""
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def private_key_b64(self) -> str:
        """Return the Ed25519 private key encoded as 32 raw bytes in base64.

        .. warning::
           Treat this string like a password.  Never commit it; never log it.
        """
        raw = self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return base64.b64encode(raw).decode("ascii")

    @classmethod
    def from_private_key_b64(cls, private_key_b64: str) -> AgentSpecCrypto:
        """Restore a key pair from the 32-byte raw private key in base64."""
        raw = base64.b64decode(private_key_b64)
        return cls(ed25519.Ed25519PrivateKey.from_private_bytes(raw))

    # ── Encrypt + sign ───────────────────────────────────────────────────────

    def encrypt_spec(self, spec: dict[str, Any], passphrase: str) -> EncryptedAgentPack:
        """Produce a signed, encrypted pack from a plain agent ``spec`` dict.

        Parameters
        ----------
        spec:
            Anything JSON-serialisable.  Conventionally conforms to
            :file:`agent_spec_schema.json`.
        passphrase:
            Used as input to scrypt — strong unique passphrases only.
        """
        if not passphrase:
            raise ValueError("passphrase must be non-empty")
        plaintext = _canonical_json(spec)
        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        key = _derive_key(passphrase, salt)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

        manifest: dict[str, Any] = {
            "schema_version": str(spec.get("schema_version", "1.0")),
            "creator": str(spec.get("creator", "unknown")),
            "public_key_b64": self.public_key_b64(),
            "spec_hash_sha256": hashlib.sha256(plaintext).hexdigest(),
            "ciphertext_hash_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "content_type": "agent_spec",
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        }
        manifest_bytes = _canonical_json(manifest)
        signature = self.private_key.sign(manifest_bytes + ciphertext)
        return EncryptedAgentPack(
            manifest=manifest,
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            salt_b64=base64.b64encode(salt).decode("ascii"),
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )

    # ── Verify + decrypt ─────────────────────────────────────────────────────

    @staticmethod
    def verify_and_decrypt(pack: EncryptedAgentPack, passphrase: str) -> dict[str, Any]:
        """Verify the manifest signature and decrypt the spec body.

        Raises
        ------
        ValueError
            If the signature is invalid, the passphrase is wrong, or any
            hash in the manifest does not match the actual bytes.
        """
        public_key_raw = base64.b64decode(pack.manifest["public_key_b64"])
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_raw)
        ciphertext = base64.b64decode(pack.ciphertext_b64)
        nonce = base64.b64decode(pack.nonce_b64)
        salt = base64.b64decode(pack.salt_b64)
        signature = base64.b64decode(pack.signature_b64)

        # 1. Signature must cover canonical_json(manifest) || ciphertext.
        manifest_bytes = _canonical_json(pack.manifest)
        try:
            public_key.verify(signature, manifest_bytes + ciphertext)
        except InvalidSignature as exc:
            raise ValueError("manifest signature is invalid") from exc

        # 2. Manifest hashes must match the raw ciphertext (cheap pre-check).
        expected_ct_hash = pack.manifest.get("ciphertext_hash_sha256")
        if expected_ct_hash and hashlib.sha256(ciphertext).hexdigest() != expected_ct_hash:
            raise ValueError("ciphertext hash mismatch")

        # 3. AES-GCM decrypt — fails fast if the passphrase is wrong or
        #    the ciphertext was tampered with after signing.
        key = _derive_key(passphrase, salt)
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise ValueError("decryption failed (wrong passphrase or tampered ciphertext)") from exc

        # 4. Plaintext hash must match the manifest claim.
        spec = json.loads(plaintext.decode("utf-8"))
        expected_spec_hash = pack.manifest.get("spec_hash_sha256")
        if expected_spec_hash and hashlib.sha256(_canonical_json(spec)).hexdigest() != expected_spec_hash:
            raise ValueError("spec hash mismatch")
        return spec


__all__ = ["AgentSpecCrypto", "EncryptedAgentPack"]
