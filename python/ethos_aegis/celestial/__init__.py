"""
ethos_aegis.celestial — Celestial Language & Agent Specification Pack
=====================================================================

A two-part cyber-security primitive bundled inside Ethos Aegis:

1. **Celestial Language** (:class:`CelestialLanguage`) — a proof-of-concept
   constructed language that encodes plaintext into non-human glyphs drawn
   from the Unicode Private Use Area.  The glyph alphabet is derived
   **deterministically** from a user-supplied seed via HMAC-SHA256, so the
   same seed always reproduces the same alphabet — no hidden backdoor and
   no hard-coded mapping.  Different seeds yield completely disjoint
   alphabets.

2. **Agent Specification Pack** (:class:`AgentSpecCrypto`,
   :class:`EncryptedAgentPack`) — a tamper-evident container for agent
   blueprints.  Specifications are canonicalised, encrypted with AES-GCM
   using a scrypt-derived key, and the manifest is signed with Ed25519.

The full CLI is reachable via ``python -m ethos_aegis.celestial`` and the
``celestial`` console script installed by ``pip install ethos-aegis[celestial]``.

Optional dependency
-------------------
The Agent Specification Pack requires the ``cryptography`` package.  Install
it with ``pip install 'ethos-aegis[celestial]'``.  The glyph language has
zero runtime dependencies and works with the Python stdlib alone.
"""

from __future__ import annotations

from ethos_aegis.celestial.language import CelestialLanguage

__all__ = ["CelestialLanguage"]

try:
    from ethos_aegis.celestial.pack import AgentSpecCrypto, EncryptedAgentPack
except ImportError:  # pragma: no cover — only when `cryptography` is missing
    # Pack support requires the `cryptography` extra. Without it, only the
    # glyph cipher is exposed; importing the missing names raises a clear
    # ImportError at use time rather than silently substituting None.
    pass
else:
    __all__ += ["AgentSpecCrypto", "EncryptedAgentPack"]
