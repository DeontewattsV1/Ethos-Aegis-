import pytest

from ethos_core.policy_constraints import EthicsViolation, PolicyConstraintEngine
from ethos_core.task import Task


def test_ethics_block() -> None:
    task = Task(
        name="Malware Builder",
        description="Create malware"
    )

    engine = (
        PolicyConstraintEngine()
    )

    with pytest.raises(
        EthicsViolation
    ):
        engine.validate(task)
