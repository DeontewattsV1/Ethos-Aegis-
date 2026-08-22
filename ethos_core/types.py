from enum import Enum


class NodeType(str, Enum):
    GOVERNANCE = "Governance"
    SYSTEM = "System"
    AGENT = "Agent"
    WORKFLOW = "Workflow"
    THEORY = "Theory"
    TASK = "Task"
    SIGNAL = "Signal"
    INTERFACE = "Interface"
    COMPUTE_LAYER = "ComputeLayer"
    SECURITY_LAYER = "SecurityLayer"


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    VALIDATED = "VALIDATED"
    ETHICAL_CHECK = "ETHICAL_CHECK"
    PLANNED = "PLANNED"
    ASSIGNED_AGENT = "ASSIGNED_AGENT"
    EXECUTING = "EXECUTING"
    REVIEW = "REVIEW"
    COMMITTED = "COMMITTED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"
