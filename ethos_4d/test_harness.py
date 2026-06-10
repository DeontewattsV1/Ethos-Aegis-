"""
FourDTestHarness — Automated 4D visual package test runner for ETHOS-AEGIS.

Simulates the full TaskState lifecycle for multiple synthetic tasks,
records their 4D world-lines, runs the SpacetimeMetrics suite,
and renders the full immersive visualization.

Run directly:
    python -m ethos_4d.test_harness
"""

from __future__ import annotations

import time
import sys
from typing import Optional

from .spacetime import EthosSpacetime, TASK_STATE_ORDINAL, NODE_TYPE_ORDINAL
from .renderer import FourDRenderer, fg, BOLD, RESET, ethical_color
from .metrics import SpacetimeMetrics

# Test task profiles — each has a node type and a path through states
TEST_TASKS = [
    {
        "id": "task::ethos-bootstrap",
        "node_type": "Governance",
        "states": ["QUEUED", "VALIDATED", "ETHICAL_CHECK", "PLANNED",
                   "ASSIGNED_AGENT", "EXECUTING", "REVIEW", "COMMITTED", "PUBLISHED"],
    },
    {
        "id": "task::graph-signal",
        "node_type": "Signal",
        "states": ["QUEUED", "VALIDATED", "ETHICAL_CHECK", "EXECUTING", "COMMITTED"],
    },
    {
        "id": "task::security-audit",
        "node_type": "SecurityLayer",
        "states": ["QUEUED", "VALIDATED", "ETHICAL_CHECK", "PLANNED", "FAILED"],
    },
    {
        "id": "task::workflow-deploy",
        "node_type": "Workflow",
        "states": ["QUEUED", "VALIDATED", "PLANNED", "ASSIGNED_AGENT",
                   "EXECUTING", "REVIEW", "COMMITTED", "ARCHIVED"],
    },
    {
        "id": "task::agent-reasoning",
        "node_type": "Agent",
        "states": ["QUEUED", "VALIDATED", "ETHICAL_CHECK", "PLANNED",
                   "ASSIGNED_AGENT", "EXECUTING", "REVIEW", "COMMITTED"],
    },
]


class FourDTestHarness:
    """Run the 4D visual test suite for ETHOS-AEGIS."""

    def __init__(self, animate: bool = False, tick_speed: float = 0.05) -> None:
        self.spacetime = EthosSpacetime()
        self.renderer  = FourDRenderer(self.spacetime, width=90)
        self.metrics   = SpacetimeMetrics(self.spacetime)
        self.animate   = animate
        self.tick_speed = tick_speed

    def simulate_tasks(self) -> None:
        """Simulate task lifecycle events and record 4D coordinates."""
        print(f"\n{BOLD}{fg(200,255,200)}  ▶ Simulating ETHOS task lifecycle...{RESET}")
        base_tick = 0.0

        for task in TEST_TASKS:
            print(f"  {fg(180,180,255)}→{RESET} {task['id']}")
            for state in task["states"]:
                self.spacetime.record_task_event(
                    task_id=task["id"],
                    state=state,
                    node_type=task["node_type"],
                    tick=base_tick,
                )
                base_tick += self.tick_speed
                if self.animate:
                    time.sleep(0.02)

        print(f"  {fg(100,255,100)}✓ {sum(len(t['states']) for t in TEST_TASKS)} events recorded across {len(TEST_TASKS)} world-lines{RESET}")

    def run_metrics(self) -> None:
        """Print the scientific metrics report."""
        print(f"\n{BOLD}{fg(255,220,100)}  ∇ SCIENTIFIC METRICS SUITE{RESET}")
        print(fg(60,60,60) + "  " + "─" * 70 + RESET)

        # Curvature tensors
        print(f"\n  {fg(180,255,180)}ETHICAL CURVATURE TENSOR (d²Z/dY²):{RESET}")
        for c in self.metrics.ethical_curvature():
            col = fg(255,80,80) if abs(c.curvature) > 0.3 else fg(200,200,200)
            print(f"  {fg(200,200,255)}{c.state:<18}{RESET} κ={col}{c.curvature:+.4f}{RESET}  {fg(160,160,160)}{c.interpretation}{RESET}")

        # Phase transitions
        print(f"\n  {fg(255,200,100)}PHASE TRANSITIONS (ΔZ ≥ threshold):{RESET}")
        for p in self.metrics.detect_phase_transitions():
            if p.significance != "normal":
                col = fg(255,60,60) if p.significance == "CRITICAL" else fg(255,165,0)
                print(f"  {fg(200,200,200)}{p.from_state:<18}{RESET}→ {fg(200,200,200)}{p.to_state:<18}{RESET}"
                      f" ΔZ={ethical_color(abs(p.delta_z))}{p.delta_z:+.4f}{RESET}"
                      f"  {col}[{p.significance}]{RESET}")

        # Entropy
        H = self.metrics.manifold_entropy()
        H_color = fg(100,255,100) if H > 1.5 else (fg(255,165,0) if H > 0.5 else fg(255,60,60))
        print(f"\n  {fg(180,255,255)}MANIFOLD ENTROPY:{RESET} {H_color}{H:.4f} bits{RESET}"
              f"  {fg(160,160,160)}({'distributed' if H > 1.5 else 'bottlenecked' if H < 0.5 else 'moderate'}){RESET}")

        # Geodesic reports
        print(f"\n  {fg(200,180,255)}GEODESIC DEVIATION ANALYSIS:{RESET}")
        for g in self.metrics.geodesic_reports():
            col = fg(100,255,100) if g.deviation_ratio <= 1.05 else (
                  fg(255,165,0) if g.deviation_ratio <= 2.0 else fg(255,60,60))
            print(f"  {fg(200,200,200)}{g.task_id[:30]:<30}{RESET}"
                  f" ratio={col}{g.deviation_ratio:.4f}{RESET}  {fg(160,160,160)}{g.verdict}{RESET}")

        # Lyapunov
        lam = self.metrics.lyapunov_estimate()
        if lam is not None:
            l_col = fg(255,60,60) if lam > 0 else fg(100,255,100)
            print(f"\n  {fg(255,180,255)}LYAPUNOV EXPONENT:{RESET} {l_col}λ = {lam:+.6f}{RESET}"
                  f"  {fg(160,160,160)}({'chaotic divergence' if lam > 0 else 'stable convergence'}){RESET}")

    def run(self) -> None:
        """Full 4D immersive test suite."""
        print("\033[2J\033[H", end="")  # clear screen
        self.simulate_tasks()
        self.renderer.render(tick=time.time() % (2 * 3.14159))
        self.run_metrics()
        print(f"\n{BOLD}{fg(80,255,200)}  ✦ ETHOS-AEGIS 4D VISUAL TEST COMPLETE{RESET}\n")


def main() -> None:
    harness = FourDTestHarness(animate="--animate" in sys.argv)
    harness.run()


if __name__ == "__main__":
    main()
