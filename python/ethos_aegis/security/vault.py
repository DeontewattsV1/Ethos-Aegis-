"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║              ░░░ T H E   S E C U R E   V A U L T ░░░                               ║
║          Cryptographic Integrity, Audit Ledger & Configuration Security             ║
║                                                                                      ║
║  The immune system must protect its own configuration from tampering.               ║
║  A compromised config is the digital equivalent of autoimmune disease —             ║
║  the defense system turned against itself.                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""

import base64
import hashlib
import hmac as _hmac_module
import json
import logging
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_vlog = logging.getLogger("ethos_aegis.security")


# ── Cryptographic Primitives ──────────────────────────────────────────────────

def _derive_key(passphrase: str, salt: bytes, iterations: int = 100_000) -> bytes:
    """PBKDF2-HMAC-SHA256 key derivation — 100k iterations per NIST SP 800-132."""
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations, dklen=32)


def _sign(key: bytes, data: bytes) -> str:
    """HMAC-SHA256 — returns hex digest."""
    return _hmac_module.new(key, data, hashlib.sha256).hexdigest()


def _verify(key: bytes, data: bytes, sig: str) -> bool:
    """Constant-time HMAC verification — prevents timing attacks."""
    return _hmac_module.compare_digest(_sign(key, data), sig)


def _xor_obfuscate(data: bytes, key: bytes) -> bytes:
    """XOR stream obfuscation — prevents plaintext values in memory dumps."""
    stream = (key * ((len(data) // len(key)) + 1))[:len(data)]
    return bytes(a ^ b for a, b in zip(data, stream))


# ── Session Seal ─────────────────────────────────────────────────────────────

@dataclass
class SessionSeal:
    """
    Cryptographic identity for a single EthosAegis runtime session.

    Every session generates a unique 32-byte ID and derives a signing key
    from it. All verdicts produced during the session can be signed and later
    verified — creating a chain of evidence that a verdict was produced by a
    specific session and has not been altered since. Think of it as a magistrate's
    wax seal on a legal document: it doesn't hide the content, but it proves
    the document's authenticity and integrity.
    """
    session_id:      str   = field(default_factory=lambda: secrets.token_hex(32))
    created_at:      str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signing_key:     bytes = field(default_factory=lambda: secrets.token_bytes(32))
    verdicts_signed: int   = 0

    def sign(self, payload_hash: str, depth: str, condemned: bool) -> str:
        """Signs a verdict's key fields. Altering any field invalidates the signature."""
        data = f"{self.session_id}:{payload_hash}:{depth}:{condemned}".encode()
        sig = _sign(self.signing_key, data)
        self.verdicts_signed += 1
        return sig

    def verify(self, payload_hash: str, depth: str, condemned: bool, sig: str) -> bool:
        data = f"{self.session_id}:{payload_hash}:{depth}:{condemned}".encode()
        return _verify(self.signing_key, data, sig)

    def fingerprint(self) -> str:
        """Short human-readable session ID for logging."""
        return self.session_id[:12]


# ── Audit Ledger ─────────────────────────────────────────────────────────────

@dataclass
class LedgerEntry:
    """
    One entry in the append-only audit chain. Each entry includes the hash of
    the previous entry (prev_hash), forming a linked structure where altering
    any entry breaks the chain for all subsequent entries — making tampering
    immediately detectable when verify_chain() is called.

    The payload's SHA-256 hash is stored rather than the raw payload text, which
    is a deliberate privacy-preserving choice: the log proves a payload was
    processed without retaining potentially sensitive content.
    """
    sequence:      int
    timestamp:     str
    event_type:    str
    session_id:    str
    payload_hash:  str
    depth:         str
    maligna_count: int
    condemned:     bool
    verdict_sig:   str
    prev_hash:     str
    entry_hash:    str = ""

    def canonical(self) -> str:
        return (f"{self.sequence}|{self.timestamp}|{self.event_type}|"
                f"{self.session_id}|{self.payload_hash}|{self.depth}|"
                f"{self.maligna_count}|{self.condemned}|{self.verdict_sig}|"
                f"{self.prev_hash}")

    def seal(self) -> str:
        self.entry_hash = hashlib.sha256(self.canonical().encode()).hexdigest()
        return self.entry_hash


class AuditLedger:
    """
    Append-only, tamper-evident operation log for the EthosAegis.

    Each entry's entry_hash covers all its fields including prev_hash, which
    chains every entry to all entries before it. Deleting or modifying any
    entry breaks the hash chain starting at that point — verify_chain() detects
    the exact entry where tampering occurred. Thread-safe via RLock.
    """

    GENESIS = "0" * 64  # Sentinel prev_hash for the first entry

    def __init__(self, seal: SessionSeal, path: Optional[Path] = None):
        self._seal     = seal
        self._entries: List[LedgerEntry] = []
        self._lock     = threading.RLock()
        self._path     = path
        self._seq      = 0
        if path and path.exists():
            self._load()

    def record(self, event: str, payload: str, depth: str,
               maligna: int, condemned: bool) -> LedgerEntry:
        with self._lock:
            ph       = hashlib.sha256(payload.encode()).hexdigest()
            sig      = self._seal.sign(ph, depth, condemned)
            prev     = self._entries[-1].entry_hash if self._entries else self.GENESIS
            self._seq += 1
            e = LedgerEntry(
                sequence=self._seq, timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=event, session_id=self._seal.fingerprint(),
                payload_hash=ph, depth=depth, maligna_count=maligna,
                condemned=condemned, verdict_sig=sig, prev_hash=prev,
            )
            e.seal()
            self._entries.append(e)
            if self._path:
                self._write(e)
            return e

    def verify_chain(self) -> Tuple[bool, int, str]:
        """Walks the chain and verifies hash linkage at every entry."""
        with self._lock:
            if not self._entries:
                return True, 0, "Empty ledger"
            prev = self.GENESIS
            for i, e in enumerate(self._entries):
                if e.prev_hash != prev:
                    return False, i, f"Chain broken at entry {e.sequence}: prev_hash mismatch"
                recomputed = hashlib.sha256(e.canonical().encode()).hexdigest()
                if recomputed != e.entry_hash:
                    return False, i, f"Entry {e.sequence} content tampered"
                prev = e.entry_hash
            return True, len(self._entries), f"Chain intact — {len(self._entries)} entries verified"

    def _write(self, e: LedgerEntry):
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(e)) + "\n")
        except OSError as ex:
            _vlog.error(f"AuditLedger write failed: {ex}")

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(LedgerEntry(**json.loads(line)))
                        self._seq = max(self._seq, self._entries[-1].sequence)
            _vlog.info(f"AuditLedger: loaded {len(self._entries)} entries from {self._path}")
        except (OSError, json.JSONDecodeError, TypeError) as ex:
            _vlog.error(f"AuditLedger load failed: {ex}")

    def summary(self) -> Dict:
        with self._lock:
            if not self._entries:
                return {"total_entries": 0}
            counts: Dict[str, int] = {}
            condemned = 0
            for e in self._entries:
                counts[e.event_type] = counts.get(e.event_type, 0) + 1
                if e.condemned:
                    condemned += 1
            return {
                "total_entries":   len(self._entries),
                "condemnations":   condemned,
                "event_breakdown": counts,
                "first_entry":     self._entries[0].timestamp,
                "last_entry":      self._entries[-1].timestamp,
            }

    @property
    def depth(self) -> int:
        return len(self._entries)


# ── Secure Vault ──────────────────────────────────────────────────────────────

class SecureVault:
    """
    Encrypted runtime configuration store.

    Every stored value is XOR-obfuscated (so it doesn't appear in plaintext in
    memory) and HMAC-tagged (so any modification is detectable). The vault uses
    a two-key architecture: one key for HMAC signing, a second derived key for
    obfuscation, following the principle that the same key should never serve
    two cryptographic purposes.

    Optional TTL support allows secrets (like API keys) to automatically expire
    after a configurable number of seconds, reducing the window of exposure if
    a key is later revoked or rotated.
    """

    def __init__(self, passphrase: Optional[str] = None):
        self._salt       = secrets.token_bytes(16)
        pp               = passphrase or secrets.token_hex(32)
        self._sign_key   = _derive_key(pp, self._salt)
        self._obfusc_key = _derive_key(pp + "_obfusc", self._salt, iterations=50_000)
        self._store: Dict[str, Dict] = {}
        self._lock       = threading.RLock()
        self._accesses   = 0

    def store(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Store an obfuscated, signed value. TTL is seconds until expiry."""
        with self._lock:
            raw      = value.encode()
            obf      = _xor_obfuscate(raw, self._obfusc_key)
            encoded  = base64.b64encode(obf).decode()
            tag      = _sign(self._sign_key, f"{key}:{encoded}".encode())
            self._store[key] = {
                "data": encoded, "tag": tag,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "ttl": ttl,
            }

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve a value. Returns None on missing key, expiry, or integrity failure."""
        with self._lock:
            self._accesses += 1
            rec = self._store.get(key)
            if not rec:
                return None
            # TTL check
            if rec["ttl"] is not None:
                age = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(rec["stored_at"])).total_seconds()
                if age > rec["ttl"]:
                    del self._store[key]
                    _vlog.warning(f"SecureVault: key '{key}' TTL expired")
                    return None
            # Integrity check
            if not _verify(self._sign_key, f"{key}:{rec['data']}".encode(), rec["tag"]):
                _vlog.critical(f"SecureVault: INTEGRITY VIOLATION on key '{key}' — possible tampering")
                return None
            raw = _xor_obfuscate(base64.b64decode(rec["data"]), self._obfusc_key)
            return raw.decode()

    def remove(self, key: str) -> bool:
        with self._lock:
            return bool(self._store.pop(key, None))

    def has(self, key: str) -> bool:
        return self.retrieve(key) is not None

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._store.keys())

    def codex(self) -> Dict:
        with self._lock:
            return {"keys": list(self._store.keys()), "count": len(self._store),
                    "access_count": self._accesses}


# ── Integrity Verifier ────────────────────────────────────────────────────────

class IntegrityVerifier:
    """
    Verifies SHA-256 fingerprints of EthosAegis source modules.

    If an attacker can modify aegis.py to weaken a detection pattern or remove
    a TaintBeacon cluster, the cells appear functional but silently miss threats.
    The IntegrityVerifier pre-registers reference fingerprints of each source file
    at initialization time. Before deployment, verify() recomputes fingerprints
    and alerts on any mismatch — the defense code itself has been tampered with.
    """

    def __init__(self):
        self._refs: Dict[str, str] = {}

    def register(self, path: Path) -> str:
        """Compute and store the SHA-256 reference fingerprint of a source file."""
        if not path.exists():
            _vlog.warning(f"IntegrityVerifier: not found: {path}")
            return ""
        fp = hashlib.sha256(path.read_bytes()).hexdigest()
        self._refs[str(path)] = fp
        _vlog.info(f"IntegrityVerifier: registered {path.name} [{fp[:16]}...]")
        return fp

    def register_package(self, root: Path) -> int:
        """Register all .py files under a package root. Returns count."""
        count = 0
        for py in sorted(root.rglob("*.py")):
            self.register(py)
            count += 1
        return count

    def verify(self) -> Tuple[bool, List[str]]:
        """
        Recompute fingerprints and compare to reference.
        Returns (all_valid, list_of_violation_descriptions).
        """
        violations = []
        for path_str, ref in self._refs.items():
            p = Path(path_str)
            if not p.exists():
                violations.append(f"MISSING: {p.name}")
                continue
            current = hashlib.sha256(p.read_bytes()).hexdigest()
            if not _hmac_module.compare_digest(current, ref):
                violations.append(f"TAMPERED: {p.name} (expected {ref[:16]}... got {current[:16]}...)")
        if violations:
            for v in violations:
                _vlog.critical(f"IntegrityVerifier: {v}")
        return len(violations) == 0, violations


# ── Threat Archive ────────────────────────────────────────────────────────────

class ThreatArchive:
    """
    Persistent, integrity-protected storage for confirmed Maligna records.

    Complements the in-memory MnemosyneCache: where the Cache optimizes for
    fast real-time lookup, the Archive is a permanent historical record
    in newline-delimited JSON format, supporting cross-session analysis,
    compliance evidence, and pre-seeding new sessions with known threats.
    Every archived record is HMAC-tagged with the session's signing key.
    """

    def __init__(self, path: Path, seal: SessionSeal):
        self._path  = path
        self._seal  = seal
        self._lock  = threading.RLock()
        self._count = 0
        path.parent.mkdir(parents=True, exist_ok=True)

    def archive(self, malignum_data: Dict) -> str:
        """Archive one Malignum. Returns the integrity tag."""
        with self._lock:
            record = {
                "session":     self._seal.fingerprint(),
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "sequence":    self._count,
                "malignum":    malignum_data,
            }
            canon = json.dumps(record, sort_keys=True).encode()
            record["integrity_tag"] = _sign(self._seal.signing_key, canon)
            self._count += 1
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except OSError as ex:
                _vlog.error(f"ThreatArchive write failed: {ex}")
                return ""
            return record["integrity_tag"]

    def load_seeds(self, min_depth: int = 3) -> List[Dict]:
        """Load archived Maligna at or above min_depth for MnemosyneCache seeding."""
        seeds = []
        if not self._path.exists():
            return seeds
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                        m = rec.get("malignum", {})
                        if m.get("depth_value", 0) >= min_depth:
                            seeds.append(m)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return seeds

    def statistics(self) -> Dict:
        sigils: Dict[str, int] = {}
        classes: Dict[str, int] = {}
        total = 0
        if not self._path.exists():
            return {"total": 0}
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                        m = rec.get("malignum", {})
                        sigils[m.get("sigil", "?")] = sigils.get(m.get("sigil", "?"), 0) + 1
                        classes[m.get("maligna_class", "?")] = classes.get(m.get("maligna_class", "?"), 0) + 1
                        total += 1
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return {
            "total": total,
            "top_sigils": sorted(sigils.items(), key=lambda x: x[1], reverse=True)[:10],
            "class_distribution": classes,
        }


# ── VaultKeeper facade ────────────────────────────────────────────────────────

class VaultKeeper:
    """
    Unified façade for all EthosAegis security subsystems.

    Owns a SessionSeal, SecureVault, AuditLedger, IntegrityVerifier, and
    ThreatArchive, wiring them together at initialization so the rest of the
    system accesses security through a single cohesive interface.

    Usage:
        keeper = VaultKeeper(passphrase="strong-secret",
                             archive_path=Path("./archive.ndjson"),
                             ledger_path=Path("./ledger.ndjson"))
        keeper.vault.store("API_KEY", "sk-...")
        keeper.ledger.record("adjudication", payload, "VOID", 0, False)
        valid, issues = keeper.verifier.verify()
        print(keeper.status())
    """

    def __init__(self, passphrase: Optional[str] = None,
                 archive_path: Optional[Path] = None,
                 ledger_path:  Optional[Path] = None):
        self.seal     = SessionSeal()
        self.vault    = SecureVault(passphrase)
        self.ledger   = AuditLedger(self.seal, path=ledger_path)
        self.verifier = IntegrityVerifier()
        self.archive  = ThreatArchive(
            archive_path or Path("./aegis_archive.ndjson"), self.seal
        )
        _vlog.info(f"VaultKeeper: online — session [{self.seal.fingerprint()}]")

    def status(self) -> Dict:
        valid, count, msg = self.ledger.verify_chain()
        return {
            "session":         self.seal.fingerprint(),
            "created_at":      self.seal.created_at,
            "verdicts_signed": self.seal.verdicts_signed,
            "vault":           self.vault.codex(),
            "ledger": {
                "depth": self.ledger.depth,
                "chain_valid": valid,
                "chain_detail": msg,
            },
            "archive": self.archive.statistics(),
        }
