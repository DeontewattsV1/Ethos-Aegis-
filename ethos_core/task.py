from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from ethos_core.types import TaskState


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    name: str
    description: str

    created_at: datetime = Field(default_factory=datetime.utcnow)

    state: TaskState = TaskState.QUEUED

    assigned_agent: str | None = None
