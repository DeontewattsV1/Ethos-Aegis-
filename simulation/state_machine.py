from __future__ import annotations

from typing import Final

from ethos_core.types import TaskState


VALID_TRANSITIONS: Final = {
    TaskState.QUEUED: [
        TaskState.VALIDATED,
        TaskState.FAILED,
    ],
    TaskState.VALIDATED: [
        TaskState.ETHICAL_CHECK,
        TaskState.FAILED,
    ],
    TaskState.ETHICAL_CHECK: [
        TaskState.PLANNED,
        TaskState.FAILED,
    ],
    TaskState.PLANNED: [
        TaskState.ASSIGNED_AGENT,
        TaskState.FAILED,
    ],
    TaskState.ASSIGNED_AGENT: [
        TaskState.EXECUTING,
        TaskState.FAILED,
    ],
    TaskState.EXECUTING: [
        TaskState.REVIEW,
        TaskState.FAILED,
    ],
    TaskState.REVIEW: [
        TaskState.COMMITTED,
        TaskState.FAILED,
    ],
    TaskState.COMMITTED: [
        TaskState.PUBLISHED,
        TaskState.ARCHIVED,
    ],
    TaskState.PUBLISHED: [
        TaskState.ARCHIVED,
    ],
}


class InvalidStateTransition(Exception):
    pass


class StateMachine:
    def __init__(self, initial_state: TaskState):
        self.current_state = initial_state

    def transition(self, new_state: TaskState) -> None:
        allowed = VALID_TRANSITIONS.get(
            self.current_state,
            [],
        )

        if new_state not in allowed:
            raise InvalidStateTransition(
                f"Cannot transition "
                f"{self.current_state} "
                f"→ {new_state}"
            )

        self.current_state = new_state
