"""
harness/types.py — Shared dataclasses and enums for the Ethos-Aegis agent harness.

Implements the typed vocabulary used by all 12 harness components.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence


# ── Turn & Message model ──────────────────────────────────────────────────────

class Role(str, Enum):
    SYSTEM    = "system"
    USER      = "user"
    ASSISTANT = "assistant"
    TOOL      = "tool"


@dataclass
class Message:
    role:       Role
    content:    str
    tool_name:  Optional[str]  = None   # populated for Role.TOOL messages
    tool_call_id: Optional[str] = None


# ── Tool model ────────────────────────────────────────────────────────────────

@dataclass
class ToolSchema:
    """JSON-schema-style descriptor injected into the LLM context."""
    name:        str
    description: str
    parameters:  Dict[str, Any]          # JSON Schema object
    readonly:    bool = True              # read-only ops may run concurrently
    risk_level:  str  = "low"            # low | medium | high


@dataclass
class ToolCall:
    id:        str
    tool_name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    tool_name:    str
    output:       str
    is_error:     bool = False


# ── Memory ────────────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    key:       str
    value:     str
    tier:      str      = "index"    # index | detail | transcript
    timestamp: float    = field(default_factory=time.time)
    tags:      List[str] = field(default_factory=list)


# ── Harness state ─────────────────────────────────────────────────────────────

class TerminationReason(str, Enum):
    FINAL_ANSWER   = "final_answer"
    MAX_TURNS      = "max_turns"
    TOKEN_BUDGET   = "token_budget"
    GUARDRAIL      = "guardrail"
    USER_INTERRUPT = "user_interrupt"
    SAFETY_REFUSAL = "safety_refusal"
    ERROR          = "error"


@dataclass
class HarnessState:
    session_id:   str
    goal:         str
    turns:        int  = 0
    tokens_used:  int  = 0
    messages:     List[Message]     = field(default_factory=list)
    tool_results: List[ToolResult]  = field(default_factory=list)
    scratchpad:   Dict[str, Any]    = field(default_factory=dict)
    terminated:   bool              = False
    term_reason:  Optional[TerminationReason] = None


@dataclass
class HarnessConfig:
    max_turns:          int   = 30
    token_budget:       int   = 100_000
    context_limit:      int   = 80_000     # trigger compaction at this size
    max_tool_retries:   int   = 2
    verify_outputs:     bool  = True
    parallel_readonly:  bool  = True
    require_approval_for: List[str] = field(default_factory=lambda: ["high"])


# ── Verification ──────────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    passed:   bool
    score:    float        # 0.0–1.0
    feedback: str
    source:   str          # "rules" | "llm_judge" | "visual"
