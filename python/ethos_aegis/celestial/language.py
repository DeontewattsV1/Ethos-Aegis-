"""
Celestial Language — deterministic seed-based glyph cipher
==========================================================

Encodes ASCII into glyphs drawn from the Unicode Private Use Area
(``U+E000 – U+F8FF``).  The glyph alphabet is derived **purely from the
seed** using HMAC-SHA256, so anyone who knows the seed can reproduce the
exact same mapping — and nobody else can.

This module replaces the proof-of-concept ``celestial_language.py`` from
the original Celestial Agent prototype, which mixed ``secrets.token_bytes``
into glyph generation and was therefore non-deterministic despite
claiming the opposite.

Cryptographic notes
-------------------
* The glyph map is a **substitution cipher**.  It is intended for
  obfuscation and demonstration, not for confidentiality.  Use the
  :class:`~ethos_aegis.celestial.pack.AgentSpecCrypto` pack for real
  authenticated encryption.
* The optional :meth:`CelestialLanguage.encrypt_bytes` helper performs a
  one-time-pad XOR.  It is mathematically perfect when the key is
  random, secret, used exactly once, and at least as long as the
  plaintext — but **never reuse a key**.  Reuse defeats the OTP entirely.
* The seed is processed with HMAC-SHA256, so two seeds that differ by
  even one bit produce uncorrelated glyph alphabets.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

# 4 bytes of HMAC output per character → 8 PUA code points per glyph.
_GLYPH_BYTES_PER_CHAR = 4
_PUA_BASE = 0xE000  # Unicode Private Use Area start

# Default character set: ASCII letters, digits, space, and common punctuation.
_DEFAULT_CHARSET = string.ascii_letters + string.digits + " .,!?"


class CelestialLanguage:
    """Deterministic glyph substitution cipher.

    Parameters
    ----------
    seed:
        Any non-empty string.  Acts as the secret key for the glyph map.
        Two different seeds produce uncorrelated alphabets; the same seed
        always reproduces the same alphabet.
    charset:
        Characters to assign glyphs to.  Anything outside this set is
        passed through unchanged during :meth:`encode_message`.

    Raises
    ------
    ValueError
        If ``seed`` is empty, or if ``charset`` contains duplicates.
    """

    def __init__(self, seed: str, charset: str = _DEFAULT_CHARSET) -> None:
        if not seed:
            raise ValueError("seed must be a non-empty string")
        if len(set(charset)) != len(charset):
            raise ValueError("charset must contain unique characters")
        self.seed = seed
        self.charset = charset
        self.glyph_map: dict[str, str] = self._generate_glyphs()
        self._reverse_map: dict[str, str] = {v: k for k, v in self.glyph_map.items()}
        self._glyph_len = _GLYPH_BYTES_PER_CHAR * 2  # two PUA chars per byte

    def _generate_glyphs(self) -> dict[str, str]:
        """Build the seed → glyph table deterministically.

        Uses HMAC-SHA256 keyed by ``SHA256(seed)`` and a domain separator
        ``b"celestial-glyph"`` to derive a fresh per-character byte string.
        """
        master = hashlib.sha256(self.seed.encode("utf-8")).digest()
        glyphs: dict[str, str] = {}
        used_glyphs: set[str] = set()
        for ch in self.charset:
            counter = 0
            while True:
                mac_input = b"celestial-glyph\x00" + ch.encode("utf-8") + counter.to_bytes(4, "big")
                digest = hmac.new(master, mac_input, hashlib.sha256).digest()
                glyph = "".join(
                    chr(_PUA_BASE + (b >> 4)) + chr(_PUA_BASE + (b & 0x0F))
                    for b in digest[:_GLYPH_BYTES_PER_CHAR]
                )
                # Re-roll on the astronomically rare collision so the map stays bijective.
                if glyph not in used_glyphs:
                    used_glyphs.add(glyph)
                    glyphs[ch] = glyph
                    break
                counter += 1
        return glyphs

    def encode_message(self, message: str) -> str:
        """Encode ``message`` by substituting each known character with its glyph.

        Characters absent from the charset are passed through unchanged.
        """
        parts: list[str] = []
        for ch in message:
            parts.append(self.glyph_map.get(ch, ch))
        return "".join(parts)

    def decode_message(self, encoded: str) -> str:
        """Inverse of :meth:`encode_message`.

        Walks the encoded string in fixed-width glyph-sized chunks; any
        chunk that is not a known glyph is treated as a single
        pass-through character, which mirrors how non-charset characters
        were preserved during encoding.
        """
        parts: list[str] = []
        i = 0
        while i < len(encoded):
            chunk = encoded[i : i + self._glyph_len]
            ch = self._reverse_map.get(chunk)
            if ch is not None:
                parts.append(ch)
                i += self._glyph_len
            else:
                parts.append(encoded[i])
                i += 1
        return "".join(parts)

    @staticmethod
    def encrypt_bytes(data: bytes) -> tuple[bytes, bytes]:
        """One-time-pad XOR.  Returns ``(ciphertext, key)``.

        .. warning::
           The OTP is information-theoretically secure **only** when the
           key is random, secret, exactly as long as the plaintext, and
           never reused.  Prefer
           :class:`~ethos_aegis.celestial.pack.AgentSpecCrypto` for
           anything real.
        """
        key = secrets.token_bytes(len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, key, strict=True))
        return ciphertext, key

    @staticmethod
    def decrypt_bytes(ciphertext: bytes, key: bytes) -> bytes:
        """Reverse of :meth:`encrypt_bytes`."""
        if len(ciphertext) != len(key):
            raise ValueError("ciphertext and key must be the same length")
        return bytes(a ^ b for a, b in zip(ciphertext, key, strict=True))


__all__ = ["CelestialLanguage"]
