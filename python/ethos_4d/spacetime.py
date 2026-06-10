"""
EthosSpacetime — 4D coordinate system for ETHOS-AEGIS task graph.

Maps the ETHOS state machine into a scientific 4D manifold:
  - Dimension 0 (X): NodeType ordinal (0=GOVERNANCE → 9=SECURITY_LAYER)
  - Dimension 1 (Y): TaskState ordinal (0=QUEUED → 10=FAILED)
  - Dimension 2 (Z): Ethical risk score [0.0 → 1.0]
  - Dimension 3 (T): Simulation tick (continuous time)

Each Task becomes a world-line — a trajectory through this manifold.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

# Mirror ETHOS enums without importing the package (standalone module)
NODE_TYPE_ORDINAL: dict[str, int] = {
    "Governance":    0,
    "System":        1,
    "Agent":         2,
    "Workflow":      3,
    "Theory":        4,
    "Task":          5,
    "Signal":        6,
    "Interface":     7,
    "ComputeLayer":  8,
    "SecurityLayer": 9,
}

TASK_STATE_ORDINAL: dict[str, int] = {
    "QUEUED":          0,
    "VALIDATED":       1,
    "ETHICAL_CHECK":   2,
    "PLANNED":         3,
    "ASSIGNED_AGENT":  4,
    "EXECUTING":       5,
    "REVIEW":          6,
    "COMMITTED":       7,
    "PUBLISHED":       8,
    "ARCHIVED":        9,
    "FAILED":          10,
}

# Ethical weight per state — higher = more scrutiny required
ETHICAL_WEIGHT: dict[str, float] = {
    "QUEUED":          0.10,
    "VALIDATED":       0.20,
    "ETHICAL_CHECK":   0.90,  # peak ethical tension
    "PLANNED":         0.40,
    "ASSIGNED_AGENT":  0.55,
    "EXECUTING":       0.70,
    "REVIEW":          0.65,
    "COMMITTED":       0.30,
    "PUBLISHED":       0.15,
    "ARCHIVED":        0.05,
    "FAILED":          1.00,  # maximum — failure is a full ethical event
}


@dataclass
class SpacetimeCoordinate:
    """A single 4D point for a task at a given moment."""
    x: float          # node type axis
    y: float          # task state axis
    z: float          # ethical weight axis
    t: float          # time axis (unix epoch or tick)
    task_id: str = ""
    state: str = ""
    node_type: str = ""
    label: str = ""

    def distance_to(self, other: "SpacetimeCoordinate") -> float:
        """Minkowski-inspired 4D distance (equal weight all dims)."""
        return math.sqrt(
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
            + (self.t - other.t) ** 2
        )

    def to_dict(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
            "t": round(self.t, 4),
            "task_id": self.task_id,
            "state": self.state,
            "node_type": self.node_type,
            "label": self.label,
        }


@dataclass
class WorldLine:
    """The 4D trajectory of a single task through ethical spacetime."""
    task_id: str
    coordinates: list[SpacetimeCoordinate] = field(default_factory=list)

    def add_point(self, coord: SpacetimeCoordinate) -> None:
        self.coordinates.append(coord)

    def arc_length(self) -> float:
        """Total path length through 4D spacetime."""
        if len(self.coordinates) < 2:
            return 0.0
        return sum(
            self.coordinates[i].distance_to(self.coordinates[i + 1])
            for i in range(len(self.coordinates) - 1)
        )

    def ethical_integral(self) -> float:
        """Area under the Z(ethical weight) curve — total ethical load."""
        if len(self.coordinates) < 2:
            return self.coordinates[0].z if self.coordinates else 0.0
        total = 0.0
        for i in range(len(self.coordinates) - 1):
            dt = abs(self.coordinates[i + 1].t - self.coordinates[i].t)
            avg_z = (self.coordinates[i].z + self.coordinates[i + 1].z) / 2
            total += avg_z * dt
        return round(total, 6)

    @property
    def final_state(self) -> str:
        return self.coordinates[-1].state if self.coordinates else "UNKNOWN"


class EthosSpacetime:
    """
    The 4D spacetime manifold for the ETHOS-AEGIS system.
    Tracks all task world-lines and provides geometric analysis.
    """

    def __init__(self) -> None:
        self.world_lines: dict[str, WorldLine] = {}
        self.origin_tick: float = time.time()

    def tick(self) -> float:
        """Normalized time tick from simulation start."""
        return round(time.time() - self.origin_tick, 4)

    def record_task_event(
        self,
        task_id: str,
        state: str,
        node_type: str = "Task",
        label: str = "",
        tick: Optional[float] = None,
    ) -> SpacetimeCoordinate:
        """Record a task state transition as a 4D coordinate."""
        coord = SpacetimeCoordinate(
            x=float(NODE_TYPE_ORDINAL.get(node_type, 5)),
            y=float(TASK_STATE_ORDINAL.get(state, 0)),
            z=ETHICAL_WEIGHT.get(state, 0.5),
            t=tick if tick is not None else self.tick(),
            task_id=task_id,
            state=state,
            node_type=node_type,
            label=label or f"{task_id}::{state}",
        )
        if task_id not in self.world_lines:
            self.world_lines[task_id] = WorldLine(task_id=task_id)
        self.world_lines[task_id].add_point(coord)
        return coord

    def manifold_summary(self) -> dict:
        """Scientific summary of the entire spacetime manifold."""
        lines = list(self.world_lines.values())
        if not lines:
            return {"error": "No world-lines recorded yet"}

        arc_lengths = [wl.arc_length() for wl in lines]
        ethical_loads = [wl.ethical_integral() for wl in lines]

        return {
            "total_world_lines": len(lines),
            "total_events": sum(len(wl.coordinates) for wl in lines),
            "mean_arc_length": round(sum(arc_lengths) / len(arc_lengths), 4),
            "max_arc_length": round(max(arc_lengths), 4),
            "mean_ethical_load": round(sum(ethical_loads) / len(ethical_loads), 6),
            "max_ethical_load": round(max(ethical_loads), 6),
            "simulation_duration_ticks": self.tick(),
        }
