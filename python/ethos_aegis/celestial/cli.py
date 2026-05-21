"""
celestial CLI — glyph encoding & agent-spec packaging
=====================================================

Invoke via ``python -m ethos_aegis.celestial`` or the installed
``celestial`` console script (added by the ``celestial`` extra).
"""

from __future__ import annotations

import argparse
import binascii
import json
import sys
from pathlib import Path
from typing import Any

from ethos_aegis.celestial.language import CelestialLanguage


def _encode(args: argparse.Namespace) -> int:
    cl = CelestialLanguage(args.seed)
    encoded = cl.encode_message(args.message)
    if args.encrypt:
        ciphertext, key = cl.encrypt_bytes(encoded.encode("utf-8"))
        out = {
            "encoded": encoded,
            "ciphertext_hex": binascii.hexlify(ciphertext).decode(),
            "key_hex": binascii.hexlify(key).decode(),
        }
        print(json.dumps(out, indent=2))
    else:
        print(encoded)
    return 0


def _decode(args: argparse.Namespace) -> int:
    cl = CelestialLanguage(args.seed)
    print(cl.decode_message(args.message))
    return 0


def _pack(args: argparse.Namespace) -> int:
    try:
        from ethos_aegis.celestial.pack import AgentSpecCrypto
    except ImportError:
        print(
            "error: the 'cryptography' package is required for pack/unpack.\n"
            "       install with: pip install 'ethos-aegis[celestial]'",
            file=sys.stderr,
        )
        return 2

    spec_path = Path(args.spec_file)
    spec: dict[str, Any] = json.loads(spec_path.read_text(encoding="utf-8"))
    crypto = AgentSpecCrypto()
    pack = crypto.encrypt_spec(spec, passphrase=args.passphrase)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(pack.to_dict(), indent=2), encoding="utf-8")
    print(f"wrote signed pack: {out_path}")
    if args.print_private_key:
        # Intentionally opt-in; never printed by default.
        print(f"private_key_b64: {crypto.private_key_b64()}")
    return 0


def _unpack(args: argparse.Namespace) -> int:
    try:
        from ethos_aegis.celestial.pack import AgentSpecCrypto, EncryptedAgentPack
    except ImportError:
        print(
            "error: the 'cryptography' package is required for pack/unpack.\n"
            "       install with: pip install 'ethos-aegis[celestial]'",
            file=sys.stderr,
        )
        return 2

    pack_path = Path(args.pack_file)
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    pack = EncryptedAgentPack.from_dict(payload)
    spec = AgentSpecCrypto.verify_and_decrypt(pack, passphrase=args.passphrase)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"verified signature + decrypted spec → {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="celestial",
        description="Celestial Language glyph cipher + Agent Specification Pack tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="encode plaintext into glyphs")
    enc.add_argument("--seed", required=True, help="seed for the glyph alphabet")
    enc.add_argument("--message", required=True, help="plaintext to encode")
    enc.add_argument(
        "--encrypt",
        action="store_true",
        help="also XOR the encoded bytes with a fresh one-time-pad key",
    )
    enc.set_defaults(func=_encode)

    dec = sub.add_parser("decode", help="decode glyphs back to plaintext (same seed)")
    dec.add_argument("--seed", required=True, help="seed used during encode")
    dec.add_argument("--message", required=True, help="encoded glyph string")
    dec.set_defaults(func=_decode)

    pack_p = sub.add_parser("pack", help="encrypt + sign an agent specification JSON")
    pack_p.add_argument("--spec-file", required=True, help="path to the spec JSON")
    pack_p.add_argument("--passphrase", required=True, help="passphrase for AES-GCM key derivation")
    pack_p.add_argument("--output", required=True, help="where to write the signed pack JSON")
    pack_p.add_argument(
        "--print-private-key",
        action="store_true",
        help="print the freshly generated Ed25519 private key (sensitive)",
    )
    pack_p.set_defaults(func=_pack)

    unpack_p = sub.add_parser("unpack", help="verify signature + decrypt an agent spec pack")
    unpack_p.add_argument("--pack-file", required=True, help="path to the signed pack JSON")
    unpack_p.add_argument("--passphrase", required=True, help="passphrase used during pack")
    unpack_p.add_argument("--output", required=True, help="where to write the decrypted spec JSON")
    unpack_p.set_defaults(func=_unpack)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
