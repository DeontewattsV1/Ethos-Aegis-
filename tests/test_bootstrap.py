from ethos_core.types import TaskState


def test_task_state_exists() -> None:
    assert TaskState.QUEUED.value == "QUEUED"
