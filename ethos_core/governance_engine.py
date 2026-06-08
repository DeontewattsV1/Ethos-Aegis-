from __future__ import annotations

from ethos_core.logging import logger
from ethos_core.policy_constraints import PolicyConstraintEngine
from ethos_core.task import Task


class GovernanceEngine:
    def __init__(self) -> None:
        self.constraints = PolicyConstraintEngine()

    def validate_task(
        self,
        task: Task,
    ) -> bool:
        logger.info(
            "governance.validation.started",
            task_id=task.id,
        )

        approved = self.constraints.validate(task)

        logger.info(
            "governance.validation.passed",
            task_id=task.id,
        )

        return approved
