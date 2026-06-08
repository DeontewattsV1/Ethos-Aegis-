from __future__ import annotations

from abc import ABC, abstractmethod

from ethos_core.task import Task


class BaseAgent(ABC):
    name: str

    @abstractmethod
    def execute(self, task: Task) -> Task:
        raise NotImplementedError
