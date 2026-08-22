from __future__ import annotations

from ethos_core.task import Task


BANNED_KEYWORDS = {
    "malware",
    "surveillance abuse",
    "harmful exploitation",
}


class EthicsViolation(Exception):
    pass


class PolicyConstraintEngine:
    def validate(self, task: Task) -> bool:
        content = (f"{task.name} {task.description}").lower()

        for keyword in BANNED_KEYWORDS:
            if keyword in content:
                raise EthicsViolation(f"Blocked by ETHOS: {keyword}")

        return True
