from __future__ import annotations

from agents.base_agent import BaseAgent
from ethos_core.task import Task


class OrchestrationAgent(BaseAgent):
    name = "orchestration-agent"

    def execute(self, task: Task) -> Task:
        task.assigned_agent = self.name
        return task
