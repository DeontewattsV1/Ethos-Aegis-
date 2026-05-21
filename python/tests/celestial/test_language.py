"""Tests for the Celestial Language deterministic glyph cipher."""

from __future__ import annotations

import string

import pytest

from ethos_aegis.celestial import CelestialLanguage


class TestCelestialLanguageDeterminism:
    """The seed → glyph alphabet must be a pure function of the seed."""

    def test_same_seed_produces_same_alphabet(self) -> None:
        a = CelestialLanguage("seed-alpha")
        b = CelestialLanguage("seed-alpha")
        assert a.glyph_map == b.glyph_map

    def test_different_seeds_produce_disjoint_alphabets(self) -> None:
        a = CelestialLanguage("seed-alpha")
        b = CelestialLanguage("seed-beta")
        # No character may share a glyph between two different seeds —
        # HMAC-SHA256 gives us 256 bits of separation per character.
        for ch in a.glyph_map:
            assert a.glyph_map[ch] != b.glyph_map[ch]

    def test_alphabet_is_bijective(self) -> None:
        cl = CelestialLanguage("seed-bijection")
        glyphs = list(cl.glyph_map.values())
        assert len(glyphs) == len(set(glyphs)), "glyph map must be one-to-one"

    def test_glyphs_live_in_unicode_private_use_area(self) -> None:
        cl = CelestialLanguage("seed-pua")
        for glyph in cl.glyph_map.values():
            for char in glyph:
                assert 0xE000 <= ord(char) <= 0xF8FF


class TestEncodeDecode:
    def test_round_trip_full_charset(self) -> None:
        cl = CelestialLanguage("round-trip-seed")
        plaintext = string.ascii_letters + string.digits + " .,!?"
        assert cl.decode_message(cl.encode_message(plaintext)) == plaintext

    def test_pass_through_unsupported_characters(self) -> None:
        cl = CelestialLanguage("passthrough-seed")
        plaintext = "hello\nworld\t#1"
        encoded = cl.encode_message(plaintext)
        # The newline, tab and '#' are outside the default charset; they
        # must survive both encode and decode unchanged.
        assert "\n" in encoded
        assert "\t" in encoded
        assert "#" in encoded
        assert cl.decode_message(encoded) == plaintext

    def test_encode_changes_the_text(self) -> None:
        cl = CelestialLanguage("change-text-seed")
        plaintext = "Hello, world!"
        assert cl.encode_message(plaintext) != plaintext

    def test_empty_message_round_trips(self) -> None:
        cl = CelestialLanguage("empty-seed")
        assert cl.encode_message("") == ""
        assert cl.decode_message("") == ""


class TestValidation:
    def test_empty_seed_rejected(self) -> None:
        with pytest.raises(ValueError):
            CelestialLanguage("")

    def test_duplicate_charset_rejected(self) -> None:
        with pytest.raises(ValueError):
            CelestialLanguage("seed", charset="aabc")


class TestOneTimePad:
    def test_round_trip(self) -> None:
        data = b"the quick brown fox"
        ciphertext, key = CelestialLanguage.encrypt_bytes(data)
        assert len(ciphertext) == len(data) == len(key)
        assert ciphertext != data  # almost certainly different
        assert CelestialLanguage.decrypt_bytes(ciphertext, key) == data

    def test_mismatched_key_length_rejected(self) -> None:
        with pytest.raises(ValueError):
            CelestialLanguage.decrypt_bytes(b"abc", b"abcd")

    def test_key_is_fresh_each_call(self) -> None:
        data = b"same input"
        _, key1 = CelestialLanguage.encrypt_bytes(data)
        _, key2 = CelestialLanguage.encrypt_bytes(data)
        assert key1 != key2, "OTP keys must never repeat across calls"
