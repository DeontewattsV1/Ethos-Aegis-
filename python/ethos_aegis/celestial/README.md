# ethos_aegis.celestial — Celestial Agent

> **Encrypted intelligence, permissioned by design.**
>
> A two-part cyber-security primitive bundled inside Ethos Aegis: a
> deterministic glyph cipher (the *Celestial Language*) and a signed,
> AES-GCM-encrypted bundle format for agent blueprints (the
> *Agent Specification Pack*).

## What's in this package

| Component | Purpose |
|---|---|
| [`language.py`](./language.py) | `CelestialLanguage` — deterministic, seed-based glyph mapping (HMAC-SHA256 → Unicode PUA). Same seed → same alphabet, anywhere, forever. |
| [`pack.py`](./pack.py) | `AgentSpecCrypto` + `EncryptedAgentPack` — AES-GCM encryption (scrypt-derived key) with an Ed25519-signed manifest. |
| [`cli.py`](./cli.py) | `celestial` console script with `encode` / `decode` / `pack` / `unpack` subcommands. |
| [`agent_spec_schema.json`](./agent_spec_schema.json) | JSON-Schema for the agent specification body. |

## Install

```bash
pip install 'ethos-aegis[celestial]'   # adds the `cryptography` dependency
```

The glyph cipher alone works without `cryptography`; pack/unpack require it.

## CLI

```bash
# Substitute plaintext for non-human glyphs (deterministic for a given seed)
celestial encode --seed "my-secret-seed" --message "Hello, Aegis!"

# Reverse the substitution
celestial decode --seed "my-secret-seed" --message "<glyph string>"

# Sign + encrypt an agent specification
celestial pack \
  --spec-file agent_spec.json \
  --passphrase "strong-passphrase" \
  --output agent_pack.json

# Verify the manifest signature + decrypt the spec body
celestial unpack \
  --pack-file agent_pack.json \
  --passphrase "strong-passphrase" \
  --output restored_spec.json
```

## Library use

```python
from ethos_aegis.celestial import CelestialLanguage, AgentSpecCrypto

# Glyph cipher: pure-stdlib, deterministic substitution
cl = CelestialLanguage(seed="my-secret-seed")
encoded = cl.encode_message("Hello, Aegis!")
assert cl.decode_message(encoded) == "Hello, Aegis!"

# Agent Specification Pack: AES-GCM + Ed25519
crypto = AgentSpecCrypto()
pack   = crypto.encrypt_spec(spec_dict, passphrase="strong-pass")
spec   = AgentSpecCrypto.verify_and_decrypt(pack, passphrase="strong-pass")
```

## Cryptographic design

* **Glyph map** is derived from `HMAC-SHA256(SHA256(seed), b"celestial-glyph\0" || char)`.
  No randomness, no salt — pure pure function of the seed. Two seeds that
  differ by one bit produce uncorrelated alphabets.
* **Spec encryption** is AES-256-GCM, key = `scrypt(passphrase, salt,
  N=2¹⁴, r=8, p=1, len=32)`. 12-byte nonce, 16-byte salt, both per-pack.
* **Manifest** carries SHA-256 of plaintext + ciphertext and the
  signer's Ed25519 public key (raw, 32 bytes, base64).
* **Signature** is Ed25519 over `canonical_json(manifest) || ciphertext`,
  so tampering with *either* half is detected.

## Security caveats

* `CelestialLanguage` is a **substitution cipher**. It is not
  confidentiality on its own — frequency analysis defeats it. Use the
  pack for any real secret.
* The OTP helper (`encrypt_bytes` / `decrypt_bytes`) is information-
  theoretically secure only if the key is random, secret, exactly the
  plaintext length, and **never reused**. Reuse it and you give away
  the XOR of two plaintexts.
* Pack passphrases feed scrypt — choose strong, unique passphrases. A
  weak passphrase makes the whole pack offline-bruteforceable.

## Veracode coverage

The [`celestial-veracode.yml`](../../.github/workflows/celestial-veracode.yml)
workflow runs Pipeline Scan against `ethos_aegis.celestial` on every PR
that touches the package, plus a weekly cron rescan. The job fails on
Very High / High severity findings; the full JSON report is uploaded as
a workflow artifact for triage.

## Paid release pipeline

Tag a release as `celestial-v<semver>` and
[`celestial-release.yml`](../../.github/workflows/celestial-release.yml)
will build the wheel + sdist, attach them to a GitHub Release, and
optionally publish to PyPI when `PYPI_API_TOKEN` is configured.
