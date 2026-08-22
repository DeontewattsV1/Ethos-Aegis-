from ethos_core.task import Task
from ethos_core.types import TaskState
from simulation.execution_engine import ExecutionEngine


def test_execution_flow() -> None:
    task = Task(
        name="Sponsor Discovery",
        description=(
            "Find sponsorship leads"
        )
    )

    engine = ExecutionEngine()

    result = engine.run(task)

    assert (
        result.state
        == TaskState.PUBLISHED
    )
