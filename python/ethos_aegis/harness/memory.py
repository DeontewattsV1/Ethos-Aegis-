"""
harness/memory.py — Component 3: Three-tier memory system.

Tier 0 — INDEX   : lightweight key/value hints (~150 chars each), always loaded.
Tier 1 — DETAIL  : full topic files, loaded on demand via tag lookup.
Tier 2 — TRANSCRIPT: raw turn history, accessed only via search.

Design mirrors Anthropic's Claude Code three-tier hierarchy and LangGraph's
namespace-organised JSON Stores.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import MemoryEntry


class MemoryStore:
    """
    In-process memory store with three-tier access pattern.

    All writes are also persisted to `persistence_path` (JSON lines) so the
    harness can reconstruct its memory across sessions — the equivalent of
    Anthropic's MEMORY.md files and OpenAI's SQLite-backed Sessions.
    """

    def __init__(self, persistence_path: Optional[Path] = None) -> None:
        self._index:      Dict[str, MemoryEntry] = {}   # tier: index
        self._detail:     Dict[str, MemoryEntry] = {}   # tier: detail
        self._transcript: List[MemoryEntry]      = []   # tier: transcript (append-only)
        self._path = persistence_path
        if self._path and Path(self._path).exists():
            self._load()

    # ── Write ─────────────────────────────────────────────────────────────────

    def remember(self, key: str, value: str, tier: str = "index",
                 tags: Optional[List[str]] = None) -> None:
        entry = MemoryEntry(key=key, value=value[:200] if tier == "index" else value,
                            tier=tier, tags=tags or [])
        if tier == "index":
            self._index[key] = entry
        elif tier == "detail":
            self._detail[key] = entry
        else:
            self._transcript.append(entry)
        self._persist(entry)

    def forget(self, key: str) -> None:
        self._index.pop(key, None)
        self._detail.pop(key, None)

    # ── Read ──────────────────────────────────────────────────────────────────

    def index_snapshot(self) -> Dict[str, str]:
        """Return the always-loaded index tier — keeps context footprint tiny."""
        return {k: v.value for k, v in self._index.items()}

    def recall(self, key: str) -> Optional[str]:
        """Pull a detail-tier entry on demand."""
        entry = self._detail.get(key) or self._index.get(key)
        return entry.value if entry else None

    def search_transcript(self, query: str, limit: int = 5) -> List[str]:
        """Keyword search over transcript tier — never bulk-loads it."""
        q = query.lower()
        hits = [e.value for e in self._transcript if q in e.value.lower()]
        return hits[-limit:]

    def search_by_tag(self, tag: str) -> List[MemoryEntry]:
        results = []
        for entry in list(self._index.values()) + list(self._detail.values()):
            if tag in entry.tags:
                results.append(entry)
        return results

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist(self, entry: MemoryEntry) -> None:
        if not self._path:
            return
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps({
                "key": entry.key, "value": entry.value,
                "tier": entry.tier, "tags": entry.tags,
                "ts": entry.timestamp,
            }) + "\n")

    def _load(self) -> None:
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                entry = MemoryEntry(key=d["key"], value=d["value"],
                                    tier=d["tier"], tags=d.get("tags", []),
                                    timestamp=d.get("ts", time.time()))
                if entry.tier == "index":
                    self._index[entry.key] = entry
                elif entry.tier == "detail":
                    self._detail[entry.key] = entry
                else:
                    self._transcript.append(entry)

    def __len__(self) -> int:
        return len(self._index) + len(self._detail) + len(self._transcript)
