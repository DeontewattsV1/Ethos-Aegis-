"""Fail-closed, local turn/token budgeting for opt-in Mythos operations."""
from __future__ import annotations
from dataclasses import dataclass

class BudgetExceeded(RuntimeError):
    """A proposed operation would exceed the configured resource budget."""

@dataclass
class BudgetMeter:
    max_tokens: int = 500_000
    max_turns: int = 25
    warning_threshold: float = 0.8
    tokens_used: int = 0
    turns_used: int = 0

    def __post_init__(self) -> None:
        if self.max_tokens < 1 or self.max_turns < 1 or not 0 < self.warning_threshold <= 1:
            raise ValueError("budgets must be positive and warning threshold within (0, 1]")
        if self.tokens_used < 0 or self.turns_used < 0:
            raise ValueError("usage cannot be negative")

    def consume(self, *, tokens: int = 0, turns: int = 1) -> None:
        if tokens < 0 or turns < 0:
            raise ValueError("resource consumption cannot be negative")
        if self.tokens_used + tokens > self.max_tokens or self.turns_used + turns > self.max_turns:
            raise BudgetExceeded("operation exceeds the delegated resource budget")
        self.tokens_used += tokens
        self.turns_used += turns

    @property
    def warning(self) -> bool:
        return max(self.tokens_used / self.max_tokens, self.turns_used / self.max_turns) >= self.warning_threshold

    @property
    def exhausted(self) -> bool:
        return self.tokens_used >= self.max_tokens or self.turns_used >= self.max_turns
