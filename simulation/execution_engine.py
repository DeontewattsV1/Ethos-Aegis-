from __future__ import annotations

from ethos_core.governance_engine import GovernanceEngine
from ethos_core.logging import logger
from ethos_core.task import Task
from ethos_core.types import TaskState
from simulation.event_bus import EventBus
from simulation.state_machine import StateMachine


class ExecutionEngine:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.governance = GovernanceEngine()

    def run(
        self,
        task: Task,
    ) -> Task:

        logger.info(
            "execution.started",
            task_id=task.id,
        )

        sm = StateMachine(
            task.state
        )

        sm.transition(
            TaskState.VALIDATED
        )
        task.state = sm.current_state

        self.bus.publish(
            "task.validated",
            {"task_id": task.id}
        )

        self.governance.validate_task(
            task
        )

        sm.transition(
            TaskState.ETHICAL_CHECK
        )
        task.state = sm.current_state

        self.bus.publish(
            "task.ethics_passed",
            {"task_id": task.id}
        )

        sm.transition(
            TaskState.PLANNED
        )
        task.state = sm.current_state

        sm.transition(
            TaskState.ASSIGNED_AGENT
        )
        task.assigned_agent = (
            "orchestration-agent"
        )
        task.state = sm.current_state

        sm.transition(
            TaskState.EXECUTING
        )
        task.state = sm.current_state

        self.bus.publish(
            "task.executing",
            {"task_id": task.id}
        )

        sm.transition(
            TaskState.REVIEW
        )
        task.state = sm.current_state

        sm.transition(
            TaskState.COMMITTED
        )
        task.state = sm.current_state

        sm.transition(
            TaskState.PUBLISHED
        )
        task.state = sm.current_state

        logger.info(
            "execution.completed",
            task_id=task.id,
            final_state=task.state,
        )

        return task
