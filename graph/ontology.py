from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ethos_core.types import NodeType


class GraphNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    node_type: NodeType
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GovernanceNode(GraphNode):
    node_type: NodeType = NodeType.GOVERNANCE
    policy_scope: str = "global"


class AgentNode(GraphNode):
    node_type: NodeType = NodeType.AGENT
    autonomy_level: str = "semi-autonomous"
    active: bool = True


class WorkflowNode(GraphNode):
    node_type: NodeType = NodeType.WORKFLOW
    execution_priority: int = 5


class TheoryNode(GraphNode):
    node_type: NodeType = NodeType.THEORY
    domain: str = "general"


class SignalNode(GraphNode):
    node_type: NodeType = NodeType.SIGNAL
    severity: str = "info"


class TaskNode(GraphNode):
    node_type: NodeType = NodeType.TASK
    status: str = "QUEUED"
