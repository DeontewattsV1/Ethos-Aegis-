"""
SpacetimeMetrics — Scientific measurement suite for the 4D ethical manifold.

Computes:
  • Ethical Curvature Tensor: how sharply the ethical gradient bends per state
  • Phase Transition Detection: identifies ETHICAL_CHECK → EXECUTING inflection
  • Entropy of the task distribution across the manifold
  • Geodesic deviation: how far a task's path deviates from the "ideal" straight line
  • Lyapunov exponent estimate: divergence rate of similar initial conditions
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .spacetime import EthosSpacetime, WorldLine, ETHICAL_WEIGHT, TASK_STATE_ORDINAL


@dataclass
class CurvatureTensor:
    """Second derivative of ethical weight along the state axis."""
    state: str
    curvature: float   # d²Z/dY² — ethical acceleration
    interpretation: str


@dataclass
class PhaseTransition:
    """A detected inflection point in the ethical manifold."""
    from_state: str
    to_state: str
    delta_z: float     # change in ethical weight
    significance: str  # "critical" | "elevated" | "normal"


@dataclass
class GeodesicReport:
    """Deviation of a task's world-line from the ideal geodesic."""
    task_id: str
    geodesic_length: float  # straight-line 4D distance start→end
    actual_length: float    # arc length of the world-line
    deviation_ratio: float  # actual / geodesic (1.0 = perfect)
    verdict: str


class SpacetimeMetrics:
    """Scientific metric suite for ETHOS-AEGIS 4D spacetime."""

    def __init__(self, spacetime: EthosSpacetime) -> None:
        self.st = spacetime

    # ── 1. Ethical Curvature Tensor ───────────────────────────────────────
    def ethical_curvature(self) -> list[CurvatureTensor]:
        """
        Compute d²Z/dY² along the TaskState axis.
        High curvature = abrupt ethical shift between states.
        """
        states = list(TASK_STATE_ORDINAL.keys())
        weights = [ETHICAL_WEIGHT[s] for s in states]
        tensors = []

        for i in range(1, len(states) - 1):
            # Central difference second derivative
            curv = weights[i+1] - 2 * weights[i] + weights[i-1]
            if curv > 0.3:
                interp = "⚠ Sharp ethical SURGE — governance attention required"
            elif curv < -0.3:
                interp = "✓ Sharp ethical RELEASE — system relaxing"
            elif abs(curv) < 0.05:
                interp = "~ Smooth transition — no phase boundary"
            else:
                interp = "→ Moderate curvature — within normal bounds"

            tensors.append(CurvatureTensor(
                state=states[i],
                curvature=round(curv, 4),
                interpretation=interp,
            ))
        return tensors

    # ── 2. Phase Transition Detection ─────────────────────────────────────
    def detect_phase_transitions(self) -> list[PhaseTransition]:
        """Identify state pairs with the largest ethical weight deltas."""
        states = list(TASK_STATE_ORDINAL.keys())
        transitions = []

        for i in range(len(states) - 1):
            s1, s2 = states[i], states[i+1]
            dz = ETHICAL_WEIGHT[s2] - ETHICAL_WEIGHT[s1]
            if abs(dz) >= 0.3:
                sig = "CRITICAL" if abs(dz) >= 0.5 else "ELEVATED"
            else:
                sig = "normal"
            transitions.append(PhaseTransition(
                from_state=s1,
                to_state=s2,
                delta_z=round(dz, 4),
                significance=sig,
            ))
        return transitions

    # ── 3. Manifold Entropy ───────────────────────────────────────────────
    def manifold_entropy(self) -> float:
        """
        Shannon entropy of task distribution across TaskState bins.
        Higher entropy = tasks spread across many states (healthy parallelism).
        Low entropy = all tasks piled in one state (bottleneck).
        """
        lines = self.st.world_lines
        if not lines:
            return 0.0

        state_counts: dict[str, int] = {}
        for wl in lines.values():
            s = wl.final_state
            state_counts[s] = state_counts.get(s, 0) + 1

        total = sum(state_counts.values())
        entropy = 0.0
        for count in state_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        return round(entropy, 4)

    # ── 4. Geodesic Deviation ─────────────────────────────────────────────
    def geodesic_reports(self) -> list[GeodesicReport]:
        """
        For each world-line, compare actual arc length to the straight-line
        geodesic distance from first to last coordinate.
        """
        reports = []
        for task_id, wl in self.st.world_lines.items():
            if len(wl.coordinates) < 2:
                continue
            start = wl.coordinates[0]
            end   = wl.coordinates[-1]
            geo   = start.distance_to(end)
            arc   = wl.arc_length()
            ratio = arc / geo if geo > 0 else float("inf")

            if ratio <= 1.05:
                verdict = "✓ Near-geodesic — highly efficient path"
            elif ratio <= 2.0:
                verdict = "→ Moderate deviation — expected lifecycle overhead"
            else:
                verdict = "⚠ High deviation — task experienced turbulence"

            reports.append(GeodesicReport(
                task_id=task_id,
                geodesic_length=round(geo, 4),
                actual_length=round(arc, 4),
                deviation_ratio=round(ratio, 4),
                verdict=verdict,
            ))
        return reports

    # ── 5. Lyapunov Estimate ─────────────────────────────────────────────
    def lyapunov_estimate(self) -> Optional[float]:
        """
        Estimate the Lyapunov exponent from pairs of world-lines
        that start near each other. λ > 0 = chaotic divergence.
        """
        lines = list(self.st.world_lines.values())
        if len(lines) < 2:
            return None

        exponents = []
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                wl1, wl2 = lines[i], lines[j]
                if not wl1.coordinates or not wl2.coordinates:
                    continue
                d0 = wl1.coordinates[0].distance_to(wl2.coordinates[0])
                df = wl1.coordinates[-1].distance_to(wl2.coordinates[-1])
                if d0 > 0 and df > 0:
                    t = wl1.coordinates[-1].t - wl1.coordinates[0].t
                    if t > 0:
                        lam = math.log(df / d0) / t
                        exponents.append(lam)

        if not exponents:
            return None
        return round(sum(exponents) / len(exponents), 6)

    # ── Full report ───────────────────────────────────────────────────────
    def full_report(self) -> dict:
        return {
            "curvature_tensors": [
                {"state": c.state, "curvature": c.curvature, "interpretation": c.interpretation}
                for c in self.ethical_curvature()
            ],
            "phase_transitions": [
                {"from": p.from_state, "to": p.to_state, "delta_z": p.delta_z, "significance": p.significance}
                for p in self.detect_phase_transitions()
            ],
            "manifold_entropy_bits": self.manifold_entropy(),
            "geodesic_reports": [
                {"task_id": g.task_id, "ratio": g.deviation_ratio, "verdict": g.verdict}
                for g in self.geodesic_reports()
            ],
            "lyapunov_exponent": self.lyapunov_estimate(),
        }
