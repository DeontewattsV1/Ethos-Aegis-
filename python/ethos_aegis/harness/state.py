"""
harness/state.py — Component 7: State management with checkpointing.

Implements LangGraph-style typed state with checkpoint-on-every-superstep,
enabling resume after interruption and time-travel debugging.

Also implements the "Ralph Loop" two-phase pattern for long-running tasks
spanning multiple context windows: an initialiser writes a progress file;
each subsequent session reads it to orient itself and pick the next task.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import HarnessState, Message, TerminationReason

_log = logging.getLogger("HarnessState")


class CheckpointStore:
    """
    Filesystem-backed checkpoint store.

    Each checkpoint is a JSON file at `{root}/{session_id}/{step:04d}.json`.
    The progress file at `{root}/{session_id}/progress.json` acts as the
    Ralph Loop's orientation anchor.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ── Checkpointing ──────────────────────────────────────────────────────────

    def save(self, state: HarnessState) -> str:
        """Persist the current state as a checkpoint. Returns the checkpoint path."""
        session_dir = self._root / state.session_id
        session_dir.mkdir(exist_ok=True)
        path = session_dir / f"{state.turns:04d}.json"
        with open(path, "w") as f:
            json.dump(self._serialise(state), f, indent=2, default=str)
        _log.debug("Checkpoint saved: %s", path)
        return str(path)

    def load_latest(self, session_id: str) -> Optional[HarnessState]:
        """Load the most recent checkpoint for a session."""
        session_dir = self._root / session_id
        if not session_dir.exists():
            return None
        checkpoints = sorted(session_dir.glob("*.json"))
        if not checkpoints:
            return None
        with open(checkpoints[-1]) as f:
            return self._deserialise(json.load(f))

    def list_sessions(self) -> List[str]:
        return [d.name for d in self._root.iterdir() if d.is_dir()]

    # ── Ralph Loop progress file ───────────────────────────────────────────────

    def write_progress(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        Ralph Loop: write the structured progress file so the next session
        can orient itself without re-reading full history.
        """
        path = self._root / session_id / "progress.json"
        existing: Dict[str, Any] = {}
        if path.exists():
            with open(path) as f:
                existing = json.load(f)
        existing.update(data)
        existing["updated_at"] = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(existing, f, indent=2, default=str)

    def read_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._root / session_id / "progress.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def _serialise(self, state: HarnessState) -> Dict[str, Any]:
        return {
            "session_id":  state.session_id,
            "goal":        state.goal,
            "turns":       state.turns,
            "tokens_used": state.tokens_used,
            "messages":    [{"role": m.role.value, "content": m.content,
                             "tool_name": m.tool_name, "tool_call_id": m.tool_call_id}
                            for m in state.messages],
            "scratchpad":  state.scratchpad,
            "terminated":  state.terminated,
            "term_reason": state.term_reason.value if state.term_reason else None,
        }

    def _deserialise(self, d: Dict[str, Any]) -> HarnessState:
        from .types import Role
        msgs = [Message(role=Role(m["role"]), content=m["content"],
                        tool_name=m.get("tool_name"),
                        tool_call_id=m.get("tool_call_id"))
                for m in d.get("messages", [])]
        return HarnessState(
            session_id=d["session_id"],
            goal=d["goal"],
            turns=d.get("turns", 0),
            tokens_used=d.get("tokens_used", 0),
            messages=msgs,
            scratchpad=d.get("scratchpad", {}),
            terminated=d.get("terminated", False),
            term_reason=TerminationReason(d["term_reason"]) if d.get("term_reason") else None,
        )
